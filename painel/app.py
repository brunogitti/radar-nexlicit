"""
Painel do Radar NexLicit. So LE o que a Camada 1/2 ja capturaram e
salvaram em dados/radar.db, nao bate na API do PNCP.

Como rodar (com o venv ativado, na pasta do projeto):
    streamlit run painel/app.py
"""

import html
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Streamlit roda este arquivo como um script solto, nao como parte de um
# pacote Python. Isso significa que o Python nao acha o pacote "captura"
# sozinho (captura/ fica um nivel acima de painel/, na raiz do projeto).
# Essas duas linhas colocam a raiz do projeto no caminho de busca do
# Python antes de qualquer import nosso, resolvendo isso.
RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_DO_PROJETO))

import streamlit as st

from captura import banco, filtro
from captura.normalizacao import normalizar_texto

st.set_page_config(page_title="Radar NexLicit", layout="wide")

COR_INK = "#12233D"
COR_PAPER = "#F1ECE0"
COR_BRASS = "#A2782A"
COR_CARD = "#FBF9F3"

ITENS_POR_PAGINA = 10


@st.cache_data(ttl=60)
def carregar_editais():
    """Le todo o historico do banco (sem filtro de dias).

    ttl=60 (segundos) evita que o painel fique preso pra sempre num dado
    antigo: se voce rodar uma captura nova (python main.py) enquanto o
    painel esta aberto, em ate 60 segundos os dados novos aparecem
    sozinhos, sem precisar reiniciar o painel.
    """
    conexao = banco.conectar()
    linhas = banco.consultar_historico(conexao)
    conexao.close()
    return linhas


@st.cache_data(ttl=60)
def carregar_min_radical():
    """Le o min_radical do keywords.yaml, pra o destaque das palavras no
    objeto usar a MESMA regra de prefixo/palavra-inteira que o filtro.py
    usou de verdade na captura. Sem isso, o destaque podia mostrar uma
    palavra como "batendo" quando na real ela nao bateu (ou o contrario).
    """
    config = filtro.carregar_keywords()
    return config["config"]["min_radical"]


def _tem_selo_me_epp(beneficios_itens):
    """True se algum item verificado tem beneficio diferente de "Sem
    beneficio". beneficios_itens vazio ou None (nao verificado) conta
    como False: nao afirmamos ME/EPP sem ter certeza.
    """
    if not beneficios_itens:
        return False
    return any(beneficio != "Sem benefício" for beneficio in beneficios_itens)


def montar_filtros(editais):
    """Desenha a barra de filtros na sidebar e devolve um dicionario com
    o que o usuario escolheu.
    """
    st.sidebar.header("Filtros")

    municipios = sorted({e["municipio"] for e in editais})
    segmentos = sorted({match["segmento"] for e in editais for match in e["segmentos"]})
    modalidades = sorted({e["modalidade"] for e in editais})
    maior_valor = max((e["valor_estimado"] or 0 for e in editais), default=0)

    municipios_selecionados = st.sidebar.multiselect("Município", municipios)
    segmentos_selecionados = st.sidebar.multiselect("Segmento", segmentos)
    modalidades_selecionadas = st.sidebar.multiselect("Modalidade", modalidades)

    hoje = date.today()
    intervalo_padrao = (hoje, hoje + timedelta(days=90))
    intervalo_escolhido = st.sidebar.date_input("Encerramento da proposta entre", value=intervalo_padrao)

    # st.date_input em modo intervalo devolve so 1 data enquanto o
    # usuario ainda nao clicou na segunda. Sem essa checagem, tentar
    # desempacotar em duas variaveis quebraria bem nesse meio-tempo.
    if len(intervalo_escolhido) == 2:
        data_inicial, data_final = intervalo_escolhido
    else:
        data_inicial, data_final = intervalo_padrao

    me_epp = st.sidebar.radio("Selo ME/EPP", ["Todos", "Sim", "Não"], horizontal=True)

    valor_min, valor_max = st.sidebar.slider(
        "Faixa de valor estimado (R$)",
        min_value=0.0,
        max_value=float(maior_valor) if maior_valor else 1.0,
        value=(0.0, float(maior_valor) if maior_valor else 1.0),
    )

    return {
        "municipios": municipios_selecionados,
        "segmentos": segmentos_selecionados,
        "modalidades": modalidades_selecionadas,
        "data_inicial": data_inicial,
        "data_final": data_final,
        "me_epp": me_epp,
        "valor_min": valor_min,
        "valor_max": valor_max,
    }


def aplicar_filtros(editais, filtros):
    """Filtro combinado: um edital so passa se bater em TODOS os campos
    preenchidos ao mesmo tempo.
    """
    resultado = []

    for edital in editais:
        if filtros["municipios"] and edital["municipio"] not in filtros["municipios"]:
            continue

        if filtros["segmentos"]:
            segmentos_do_edital = {match["segmento"] for match in edital["segmentos"]}
            if not segmentos_do_edital & set(filtros["segmentos"]):
                continue

        if filtros["modalidades"] and edital["modalidade"] not in filtros["modalidades"]:
            continue

        prazo = datetime.fromisoformat(edital["data_encerramento_proposta"]).date()
        if not (filtros["data_inicial"] <= prazo <= filtros["data_final"]):
            continue

        if filtros["me_epp"] != "Todos":
            tem_selo = _tem_selo_me_epp(edital["beneficios_itens"])
            if filtros["me_epp"] == "Sim" and not tem_selo:
                continue
            if filtros["me_epp"] == "Não" and tem_selo:
                continue

        valor = edital["valor_estimado"] or 0
        if not (filtros["valor_min"] <= valor <= filtros["valor_max"]):
            continue

        resultado.append(edital)

    return resultado


def _destacar_termos(texto, termos, min_radical):
    """Envolve em destaque cada palavra do texto original que bate com
    algum dos termos que fizeram esse edital entrar no segmento. Usa a
    mesma regra de match do filtro.py (prefixo pra termo longo, palavra
    inteira pra termo curto), reaproveitando normalizar_texto, pra nunca
    destacar uma palavra que na pratica nao bateu.

    Termos de mais de uma palavra (ex.: "agua sanitaria") nao sao
    destacados por essa funcao, ela so trabalha palavra a palavra.
    """
    texto_escapado = html.escape(texto)
    termos_normalizados = [t for t in (normalizar_texto(termo) for termo in termos) if " " not in t]

    def repor(match):
        palavra_original = match.group(0)
        palavra_normalizada = normalizar_texto(palavra_original)
        for termo in termos_normalizados:
            bate = (
                palavra_normalizada.startswith(termo)
                if len(termo) >= min_radical
                else palavra_normalizada == termo
            )
            if bate:
                return (
                    f'<mark style="background:{COR_BRASS}; color:{COR_PAPER}; '
                    f'padding:0 3px; border-radius:2px;">{palavra_original}</mark>'
                )
        return palavra_original

    return re.sub(r"\w+", repor, texto_escapado)


def _renderizar_badges(edital):
    pedacos = []
    for match in edital["segmentos"]:
        pedacos.append(
            f'<span style="background:{COR_BRASS}; color:{COR_PAPER}; padding:2px 10px; '
            f'border-radius:999px; font-size:0.75rem; font-weight:600; margin-right:6px;">'
            f'{match["segmento"]}</span>'
        )
    if _tem_selo_me_epp(edital["beneficios_itens"]):
        pedacos.append(
            f'<span style="background:{COR_INK}; color:{COR_PAPER}; padding:2px 10px; '
            f'border-radius:999px; font-size:0.75rem; font-weight:600;">ME/EPP</span>'
        )
    return "".join(pedacos)


def _renderizar_card(edital, min_radical):
    with st.container(border=True, key=f"card_{edital['numero_controle_pncp']}"):
        prazo = datetime.fromisoformat(edital["data_encerramento_proposta"])

        st.markdown(
            f'<div style="font-family:\'Newsreader\',serif; font-size:1.15rem; '
            f'font-weight:600; color:{COR_INK};">{edital["orgao"]}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(_renderizar_badges(edital), unsafe_allow_html=True)

        st.markdown(
            f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:0.7rem; '
            f'letter-spacing:0.06em; text-transform:uppercase; color:{COR_INK}; opacity:0.7; '
            f'margin-top:6px;">{edital["modalidade"]} · {edital["municipio"]}/{edital["uf"]} · '
            f'encerra {prazo:%d/%m/%Y}</div>',
            unsafe_allow_html=True,
        )

        todos_os_termos = [termo for match in edital["segmentos"] for termo in match["termos"]]
        objeto_resumido = edital["objeto"][:220] + ("…" if len(edital["objeto"]) > 220 else "")
        st.markdown(
            f'<div style="margin-top:8px;">{_destacar_termos(objeto_resumido, todos_os_termos, min_radical)}</div>',
            unsafe_allow_html=True,
        )

        with st.expander("Ver mais detalhes"):
            st.markdown(_destacar_termos(edital["objeto"], todos_os_termos, min_radical), unsafe_allow_html=True)
            st.markdown(f"[Ver no PNCP]({edital['link_pncp']})")


def _paginar(lista):
    if "pagina_atual" not in st.session_state:
        st.session_state.pagina_atual = 1

    total_paginas = max(1, -(-len(lista) // ITENS_POR_PAGINA))
    pagina_atual = min(st.session_state.pagina_atual, total_paginas)

    inicio = (pagina_atual - 1) * ITENS_POR_PAGINA
    return lista[inicio:inicio + ITENS_POR_PAGINA], pagina_atual, total_paginas


def _controles_paginacao(pagina_atual, total_paginas):
    """Botoes de pagina no rodape. st.session_state e a forma do
    Streamlit lembrar um valor entre uma reexecucao do script e outra
    (sem isso, a pagina "esqueceria" toda vez que qualquer coisa mudasse
    na tela). st.rerun() forca o script a rodar de novo na hora, porque
    esses botoes ficam embaixo da lista, e precisamos atualizar a lista
    la em cima assim que o botao for clicado.
    """
    col_anterior, col_meio, col_proxima = st.columns([1, 2, 1])

    with col_anterior:
        if st.button("← Anterior", disabled=pagina_atual <= 1):
            st.session_state.pagina_atual = pagina_atual - 1
            st.rerun()

    with col_meio:
        st.markdown(
            f'<div style="text-align:center;">Página {pagina_atual} de {total_paginas}</div>',
            unsafe_allow_html=True,
        )

    with col_proxima:
        if st.button("Próxima →", disabled=pagina_atual >= total_paginas):
            st.session_state.pagina_atual = pagina_atual + 1
            st.rerun()


def _aplicar_estilo_dos_cards():
    # [class*="..."] e um seletor CSS de "contem esse texto", isso pega
    # TODOS os containers cuja classe contenha "st-key-card_", nao
    # importa o numero de controle PNCP que vem depois. A classe
    # "st-key-NOME" e gerada pelo proprio Streamlit a partir do
    # parametro key= do st.container, e e estavel entre versoes,
    # diferente das classes internas automaticas (essas sim, frageis).
    st.markdown(
        f"""
        <style>
        [class*="st-key-card_"] {{
            background-color: {COR_CARD};
            padding: 16px;
            margin-bottom: 4px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.title("Radar NexLicit")
    _aplicar_estilo_dos_cards()
    editais = carregar_editais()
    min_radical = carregar_min_radical()

    filtros = montar_filtros(editais)
    editais_filtrados = aplicar_filtros(editais, filtros)

    # se o filtro mudou desde a ultima vez, volta pra pagina 1: senao o
    # usuario podia ficar "preso" numa pagina 4 que nao existe mais
    # depois de estreitar o filtro.
    assinatura_filtros = tuple(filtros.items())
    if st.session_state.get("assinatura_filtros_anterior") != assinatura_filtros:
        st.session_state.pagina_atual = 1
        st.session_state["assinatura_filtros_anterior"] = assinatura_filtros

    st.write(f"**{len(editais_filtrados)}** de {len(editais)} edital(is) no banco batem com o filtro atual.")

    editais_da_pagina, pagina_atual, total_paginas = _paginar(editais_filtrados)

    for edital in editais_da_pagina:
        _renderizar_card(edital, min_radical)

    if editais_filtrados:
        _controles_paginacao(pagina_atual, total_paginas)


if __name__ == "__main__":
    main()
