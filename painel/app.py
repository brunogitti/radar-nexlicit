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

COR_INK = "#12233D"
COR_PAPER = "#F1ECE0"
COR_BRASS = "#A2782A"
COR_CARD = "#FBF9F3"

# Simbolo oficial da NexLicit (quadrado navy com check dourado), o mesmo
# usado como favicon do site institucional (nexlicit-landing.html). Nao
# e um desenho novo, so reaproveitamos o SVG que ja existe la, num tamanho
# configuravel pra poder usar tanto no cabecalho (grande) quanto no
# rodape e no favicon (pequenos).
_LOGO_SVG_MODELO = """<svg viewBox="0 0 30 30" width="{tamanho}" height="{tamanho}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <rect x="1" y="1" width="28" height="28" rx="8" fill="{cor_fundo}"/>
  <path d="M8 16 12.5 20.5 22 9.5" stroke="{cor_check}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>"""


def _logo_svg(tamanho=30):
    return _LOGO_SVG_MODELO.format(tamanho=tamanho, cor_fundo=COR_INK, cor_check=COR_BRASS)


# page_icon aceita string SVG direto (confirmado na documentacao do
# st.image, que e o que o st.set_page_config reaproveita por baixo).
st.set_page_config(page_title="Radar NexLicit", page_icon=_logo_svg(), layout="wide")

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


def _renderizar_cabecalho():
    """Simbolo da NexLicit ao lado do nome do produto (Radar mais leve,
    NexLicit em negrito, mesma linha), com a tagline institucional
    embaixo no estilo eyebrow (monoespacado, versalete, letter-spacing
    largo), igual a landing page usa.
    """
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:12px;">
            {_logo_svg(40)}
            <div style="font-family:'Newsreader',serif; font-size:2.2rem; line-height:1.1; color:{COR_INK};">
                <span style="font-weight:400;">Radar</span>
                <span style="font-weight:700;">NexLicit</span>
            </div>
        </div>
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.72rem; letter-spacing:0.14em;
                    color:{COR_BRASS}; margin:4px 0 20px 52px;">
            CONSULTORIA EM LICITAÇÕES
        </div>
        """,
        # margin-left:52px = 40px do simbolo + 12px do espaco entre ele e o
        # texto, pra tagline ficar alinhada embaixo de "Radar NexLicit",
        # nao embaixo do simbolo.
        unsafe_allow_html=True,
    )


def _renderizar_rodape():
    """Rodape com o simbolo pequeno e o mesmo texto institucional do
    rodape do site, com link pra la. Uma linha bem fina e clara (nao um
    st.divider(), que fica pesado demais) so pra separar do conteudo.
    """
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:8px; margin-top:32px; padding-top:16px;
                    border-top:1px solid {COR_BRASS}33;">
            {_logo_svg(18)}
            <a href="https://nexlicit.netlify.app" target="_blank"
               style="font-family:'IBM Plex Sans',sans-serif; font-size:0.8rem; color:{COR_INK};
                      opacity:0.75; text-decoration:none;">
                NEXLICIT: Consultoria em Licitações Públicas
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
    # gap=None tira o espacamento automatico que o Streamlit poe entre
    # cada st.markdown aqui dentro. Sem isso, o respiro real de cada
    # bloco era o espacamento automatico (sempre o mesmo, 16px) mais a
    # margem que a gente escrevia por cima, dai ficava inconsistente:
    # uns blocos pareciam colados, outros soltos, sem motivo claro. Com
    # gap=None, a margem que a gente escreve em cada div e a unica coisa
    # que decide o espaco, entao da pra ajustar o ritmo visual de
    # verdade (orgao+badges mais proximos, porque sao a mesma "familia"
    # de informacao; metadados um pouco mais separados, porque mudam de
    # assunto; respiro maior antes do "Ver mais detalhes", pra ele nao
    # parecer colado no texto acima).
    with st.container(border=True, key=f"card_{edital['numero_controle_pncp']}", gap=None):
        prazo = datetime.fromisoformat(edital["data_encerramento_proposta"])

        st.markdown(
            f'<div style="font-family:\'Newsreader\',serif; font-size:1.15rem; '
            f'font-weight:600; color:{COR_INK};">{edital["orgao"]}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div style="margin-top:12px;">{_renderizar_badges(edital)}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:0.7rem; '
            f'letter-spacing:0.06em; text-transform:uppercase; color:{COR_INK}; opacity:0.7; '
            f'margin-top:14px;">{edital["modalidade"]} · {edital["municipio"]}/{edital["uf"]} · '
            f'encerra {prazo:%d/%m/%Y}</div>',
            unsafe_allow_html=True,
        )

        todos_os_termos = [termo for match in edital["segmentos"] for termo in match["termos"]]
        objeto_resumido = edital["objeto"][:220] + ("…" if len(edital["objeto"]) > 220 else "")
        st.markdown(
            f'<div style="margin:12px 0 16px 0;">{_destacar_termos(objeto_resumido, todos_os_termos, min_radical)}</div>',
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
    _renderizar_cabecalho()
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

    # gap="xsmall" (8px) aproxima a contagem de resultados do primeiro
    # card: o padrao do Streamlit aqui e 16px, o que ficava largo demais
    # logo antes de um bloco tao denso quanto a lista de cards.
    with st.container(gap="xsmall"):
        st.write(f"**{len(editais_filtrados)}** de {len(editais)} edital(is) no banco batem com o filtro atual.")

        editais_da_pagina, pagina_atual, total_paginas = _paginar(editais_filtrados)

        for edital in editais_da_pagina:
            _renderizar_card(edital, min_radical)

        if editais_filtrados:
            _controles_paginacao(pagina_atual, total_paginas)

    _renderizar_rodape()


if __name__ == "__main__":
    main()
