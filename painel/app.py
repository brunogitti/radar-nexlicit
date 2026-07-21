"""
Painel do Radar NexLicit. So LE o que a Camada 1/2 ja capturaram e
salvaram em dados/radar.db, nao bate na API do PNCP.

Como rodar (com o venv ativado, na pasta do projeto):
    streamlit run painel/app.py
"""

import html
import re
import sys
from datetime import date, datetime, time, timedelta
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

# A partir de quantos dias pra encerrar a proposta um edital e marcado
# como "vencimento proximo" no card (ver _eh_urgente).
DIAS_LIMIAR_URGENTE = 3


def _formatar_valor_reais(valor):
    """Formata no padrao brasileiro (R$ 5.610,00), diferente do
    formatar_valor de captura/apresentacao.py (que usa R$ 5610.00, pro
    e-mail e terminal). Fica local ao painel de proposito, pra nao mudar
    a formatacao que ja existe e ja tem teste em outro lugar.
    """
    if not valor:
        return "valor não informado"
    # .2f com virgula de milhar da o formato americano (5,610.00). Troca
    # virgula<->ponto (usando "_" como marcador temporario) pra chegar no
    # formato brasileiro (5.610,00).
    texto_americano = f"{valor:,.2f}"
    texto_brasileiro = texto_americano.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto_brasileiro}"


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
def carregar_itens(numero_controle_pncp):
    """Le os itens de UM edital especifico (Tarefa A.4). So e chamada
    quando o usuario abre de verdade o "ver mais detalhes" daquele card
    (ver on_change="rerun" e .open em _renderizar_card), nunca para todos
    os editais de uma vez, por isso não está junto de carregar_editais.
    """
    conexao = banco.conectar()
    itens = banco.buscar_itens_do_edital(conexao, numero_controle_pncp)
    conexao.close()
    return itens


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

    Faixa de fundo navy (pedido explicito: mais presenca dessa cor no
    painel). O simbolo ganha um "selo" claro atras dele (fundo papel,
    cantos arredondados) porque o proprio simbolo tem fundo navy: sem
    esse selo, o quadrado do simbolo desaparece dentro da faixa navy do
    cabecalho, sobrando so o check dourado boiando sem contorno.
    """
    st.markdown(
        f"""
        <div style="background-color:{COR_INK}; border-radius:8px; padding:18px 24px; margin-bottom:20px;">
            <div style="display:flex; align-items:center; gap:12px;">
                <div style="background-color:{COR_PAPER}; border-radius:10px; padding:4px; display:flex;">
                    {_logo_svg(32)}
                </div>
                <div style="font-family:'Newsreader',serif; font-size:2.2rem; line-height:1.1; color:{COR_PAPER};">
                    <span style="font-weight:400;">Radar</span>
                    <span style="font-weight:700;">NexLicit</span>
                </div>
            </div>
            <div style="font-family:'IBM Plex Mono',monospace; font-size:0.72rem; letter-spacing:0.14em;
                        color:{COR_BRASS}; margin:4px 0 0 52px;">
                CONSULTORIA EM LICITAÇÕES
            </div>
        </div>
        """,
        # margin-left:52px = 40px do selo do simbolo + 12px do espaco ate
        # o texto, pra tagline ficar alinhada embaixo de "Radar NexLicit".
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

    st.sidebar.subheader("Leva de captação")

    # Igual ao slider de valor: o padrao cobre do mais antigo ao mais
    # novo que existe no banco, entao esse filtro comeca sem esconder
    # nada. So passa a restringir de verdade quando o usuario mexer.
    datas_captacao = [datetime.fromisoformat(e["visto_em"]).date() for e in editais]
    captacao_min_padrao = min(datas_captacao, default=hoje)
    intervalo_captacao_padrao = (captacao_min_padrao, hoje)
    intervalo_captacao_escolhido = st.sidebar.date_input(
        "Captado entre (data)", value=intervalo_captacao_padrao
    )
    if len(intervalo_captacao_escolhido) == 2:
        captacao_data_inicial, captacao_data_final = intervalo_captacao_escolhido
    else:
        captacao_data_inicial, captacao_data_final = intervalo_captacao_padrao

    col_hora_inicial, col_hora_final = st.sidebar.columns(2)
    with col_hora_inicial:
        captacao_hora_inicial = st.time_input("Das", value=time(0, 0))
    with col_hora_final:
        captacao_hora_final = st.time_input("Até", value=time(23, 59))

    return {
        "municipios": municipios_selecionados,
        "segmentos": segmentos_selecionados,
        "modalidades": modalidades_selecionadas,
        "data_inicial": data_inicial,
        "data_final": data_final,
        "me_epp": me_epp,
        "valor_min": valor_min,
        "valor_max": valor_max,
        "captacao_inicio": datetime.combine(captacao_data_inicial, captacao_hora_inicial),
        "captacao_fim": datetime.combine(captacao_data_final, captacao_hora_final),
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

        visto_em = datetime.fromisoformat(edital["visto_em"])
        if not (filtros["captacao_inicio"] <= visto_em <= filtros["captacao_fim"]):
            continue

        resultado.append(edital)

    return resultado


def _ordenar(editais, criterio):
    """criterio e um dos textos do seletor em main(): ordena por captacao
    (mais recente primeiro) ou por prazo de encerramento (mais proximo
    de fechar primeiro, que e o mais urgente).
    """
    if criterio == "Captação (mais recente)":
        return sorted(editais, key=lambda e: datetime.fromisoformat(e["visto_em"]), reverse=True)
    return sorted(editais, key=lambda e: datetime.fromisoformat(e["data_encerramento_proposta"]))


def _eh_urgente(prazo):
    """True se faltam de 0 a DIAS_LIMIAR_URGENTE dias pro encerramento da
    proposta (prazos ja vencidos nao contam aqui, isso e um estado
    diferente de "urgente", fora do escopo desta entrega).
    """
    dias_restantes = (prazo.date() - date.today()).days
    return 0 <= dias_restantes <= DIAS_LIMIAR_URGENTE


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


def _renderizar_badges(edital, urgente):
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
            f'border-radius:999px; font-size:0.75rem; font-weight:600; margin-right:6px;">ME/EPP</span>'
        )
    if urgente:
        # Mesma cor navy do selo ME/EPP acima, de proposito: o dourado
        # fica reservado pro significado "achei a palavra-chave", navy
        # aqui sinaliza "preste atencao", sao duas linguagens visuais
        # separadas.
        pedacos.append(
            f'<span style="background:{COR_INK}; color:{COR_PAPER}; padding:2px 10px; '
            f'border-radius:999px; font-size:0.75rem; font-weight:600;">Encerra em breve</span>'
        )
    return "".join(pedacos)


def _formatar_quantidade(valor):
    if valor is None:
        return "—"
    return f"{valor:g}"


def _remover_duplicacao_exata(texto):
    """So pra EXIBICAO: alguns editais no PNCP tem a descricao do item
    colada duas vezes por engano na hora do cadastro (confirmado direto
    na API, nao e bug nosso, ver o caso do edital de Fernandopolis).
    Nunca altera o que fica salvo no banco, so o que aparece na tela.

    Se o texto, cortado bem no meio, tiver as duas metades identicas
    (com ou sem um espaco separando elas), mostra so a primeira metade.
    E um teste bem especifico de proposito: um texto normal ter a
    primeira metade igual, caractere por caractere, a segunda metade
    inteira e praticamente impossivel por acaso, entao isso nunca deve
    cortar uma descricao legitima.
    """
    metade = len(texto) // 2

    if len(texto) % 2 == 1 and texto[metade] == " ":
        primeira, segunda = texto[:metade], texto[metade + 1:]
    else:
        primeira, segunda = texto[:metade], texto[metade:]

    return primeira if primeira and primeira == segunda else texto


def _renderizar_itens(itens, termos, min_radical):
    """Tabela com os itens do edital, com a descricao destacada pelas
    mesmas palavras-chave que fizeram esse edital bater no segmento.
    Tem que ser HTML nosso (nao st.dataframe/st.table): essas duas
    escapam qualquer tag dentro da celula, entao o <mark> do destaque
    apareceria como texto cru em vez de destacar de verdade.
    """
    if not itens:
        st.caption("Nenhum item detalhado disponível para este edital ainda.")
        return

    linhas_html = []
    for item in itens:
        descricao = _remover_duplicacao_exata((item["descricao"] or "").strip())
        descricao_destacada = _destacar_termos(descricao, termos, min_radical)
        linhas_html.append(
            f'<tr>'
            f'<td style="padding:6px 10px; border-bottom:1px solid {COR_BRASS}33;">{descricao_destacada}</td>'
            f'<td style="padding:6px 10px; border-bottom:1px solid {COR_BRASS}33; text-align:right; '
            f'white-space:nowrap;">{_formatar_quantidade(item["quantidade"])}</td>'
            f'<td style="padding:6px 10px; border-bottom:1px solid {COR_BRASS}33; text-align:right; '
            f'white-space:nowrap;">{_formatar_valor_reais(item["valor_unitario_estimado"])}</td>'
            f'<td style="padding:6px 10px; border-bottom:1px solid {COR_BRASS}33; text-align:right; '
            f'white-space:nowrap;">{_formatar_valor_reais(item["valor_total"])}</td>'
            f'</tr>'
        )

    st.markdown(
        f"""
        <table style="width:100%; border-collapse:collapse; font-family:'IBM Plex Sans',sans-serif;
                       font-size:0.85rem; margin-top:12px;">
            <thead>
                <tr style="color:{COR_INK}; opacity:0.6; font-family:'IBM Plex Mono',monospace;
                           font-size:0.65rem; letter-spacing:0.06em; text-transform:uppercase;">
                    <th style="text-align:left; padding:4px 10px;">Descrição</th>
                    <th style="text-align:right; padding:4px 10px;">Qtd.</th>
                    <th style="text-align:right; padding:4px 10px;">Valor unit.</th>
                    <th style="text-align:right; padding:4px 10px;">Valor total</th>
                </tr>
            </thead>
            <tbody>
                {"".join(linhas_html)}
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )


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
    # prazo e urgente precisam existir ANTES de abrir o container, porque
    # a chave do container muda de nome quando o edital e urgente (e o
    # que aciona a borda de destaque em _aplicar_estilo_dos_cards).
    prazo = datetime.fromisoformat(edital["data_encerramento_proposta"])
    urgente = _eh_urgente(prazo)
    sufixo_chave = "_urgente" if urgente else ""

    with st.container(border=True, key=f"card_{edital['numero_controle_pncp']}{sufixo_chave}", gap=None):
        st.markdown(
            f'<div style="font-family:\'Newsreader\',serif; font-size:1.15rem; '
            f'font-weight:600; color:{COR_INK};">{edital["orgao"]}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div style="margin-top:12px;">{_renderizar_badges(edital, urgente)}</div>',
            unsafe_allow_html=True,
        )

        visto_em = datetime.fromisoformat(edital["visto_em"])
        st.markdown(
            f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:0.7rem; '
            f'letter-spacing:0.06em; text-transform:uppercase; color:{COR_INK}; opacity:0.7; '
            f'margin-top:14px;">{edital["modalidade"]} · {edital["municipio"]}/{edital["uf"]} · '
            f'encerra {prazo:%d/%m/%Y} · {_formatar_valor_reais(edital["valor_estimado"])}</div>'
            f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:0.65rem; '
            f'color:{COR_INK}; opacity:0.5; margin-top:4px;">'
            f'Captado em {visto_em:%d/%m/%Y às %H:%M}</div>',
            unsafe_allow_html=True,
        )

        todos_os_termos = [termo for match in edital["segmentos"] for termo in match["termos"]]
        objeto_resumido = edital["objeto"][:220] + ("…" if len(edital["objeto"]) > 220 else "")
        st.markdown(
            f'<div style="margin:12px 0 16px 0;">{_destacar_termos(objeto_resumido, todos_os_termos, min_radical)}</div>',
            unsafe_allow_html=True,
        )

        # on_change="rerun" + .open e o que permite pular a consulta ao
        # banco (carregar_itens) enquanto o expander estiver fechado. Sem
        # isso, por padrao o Streamlit executa o conteudo do expander
        # mesmo fechado, e a gente ia buscar item de TODO card da pagina
        # toda vez, nao so do que o usuario realmente abriu.
        detalhes = st.expander(
            "Ver mais detalhes", on_change="rerun", key=f"detalhes_{edital['numero_controle_pncp']}"
        )
        with detalhes:
            st.markdown(_destacar_termos(edital["objeto"], todos_os_termos, min_radical), unsafe_allow_html=True)
            st.markdown(f"[Ver no PNCP]({edital['link_pncp']})")

            if detalhes.open:
                itens = carregar_itens(edital["numero_controle_pncp"])
                _renderizar_itens(itens, todos_os_termos, min_radical)


def _paginar(lista, itens_por_pagina):
    if "pagina_atual" not in st.session_state:
        st.session_state.pagina_atual = 1

    total_paginas = max(1, -(-len(lista) // itens_por_pagina))
    pagina_atual = min(st.session_state.pagina_atual, total_paginas)

    inicio = (pagina_atual - 1) * itens_por_pagina
    return lista[inicio:inicio + itens_por_pagina], pagina_atual, total_paginas


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
        /* "urgente" so aparece na classe de cards com vencimento
        proximo (ver sufixo_chave em _renderizar_card), nunca em
        numero_controle_pncp, entao esse seletor nunca pega card errado. */
        [class*="st-key-card_"][class*="urgente"] {{
            border-left: 4px solid {COR_INK};
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

    col_ordenacao, col_itens_por_pagina = st.columns([3, 1])
    with col_ordenacao:
        ordenacao = st.selectbox(
            "Ordenar por", ["Captação (mais recente)", "Encerramento (mais próximo)"]
        )
    with col_itens_por_pagina:
        itens_por_pagina = st.selectbox("Itens por página", [10, 25, 50])

    editais_filtrados = _ordenar(editais_filtrados, ordenacao)

    # se o filtro, a ordenacao ou o tamanho da pagina mudou desde a
    # ultima vez, volta pra pagina 1: senao o usuario podia ficar
    # "preso" numa pagina 4 que nao existe mais depois de estreitar o
    # filtro ou pedir mais itens por pagina.
    assinatura_filtros = (tuple(filtros.items()), ordenacao, itens_por_pagina)
    if st.session_state.get("assinatura_filtros_anterior") != assinatura_filtros:
        st.session_state.pagina_atual = 1
        st.session_state["assinatura_filtros_anterior"] = assinatura_filtros

    # gap="xsmall" (8px) aproxima a contagem de resultados do primeiro
    # card: o padrao do Streamlit aqui e 16px, o que ficava largo demais
    # logo antes de um bloco tao denso quanto a lista de cards.
    with st.container(gap="xsmall"):
        st.write(f"**{len(editais_filtrados)}** de {len(editais)} edital(is) no banco batem com o filtro atual.")

        editais_da_pagina, pagina_atual, total_paginas = _paginar(editais_filtrados, itens_por_pagina)

        for edital in editais_da_pagina:
            _renderizar_card(edital, min_radical)

        if editais_filtrados:
            _controles_paginacao(pagina_atual, total_paginas)

    _renderizar_rodape()


if __name__ == "__main__":
    main()
