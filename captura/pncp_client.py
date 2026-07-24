"""
Este modulo so fala com a API do PNCP: monta a requisicao, pagina os
resultados, trata erro de rede, decide quando vale a pena tentar de novo.
Nao sabe nada sobre palavra-chave, segmento ou keywords.yaml, so devolve
objetos Edital (ver modelos.py) com o que a API respondeu.
"""

import logging
import time
from datetime import datetime, timedelta

import requests

from .modelos import Edital

logger = logging.getLogger(__name__)

URL_CONTRATACOES_PROPOSTA = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
URL_ITENS_DA_COMPRA = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
URL_ARQUIVOS_DA_COMPRA = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos"

TAMANHO_PAGINA = 50  # confirmado no Swagger: esse e o maximo permitido pela API

# 40s (nao 30s): testando de verdade contra o PNCP instavel (24/07), uma
# resposta legitima (200) demorou 28.8s. 30s cortava essa resposta em cima
# da hora; 40s da uma margem sem esperar demais quando o PNCP realmente
# esta fora do ar (o proprio backend dele parece desistir por volta dos 30s
# e devolver 500, entao esperar muito mais que isso nao ajudaria).
TIMEOUT_SEGUNDOS = 40

# 5 (nao 3): na mesma sondagem de 24/07, das 5 tentativas seguidas contra o
# mesmo municipio, so as 2 ultimas (4a e 5a) responderam rapido e normal.
# 3 tentativas nao teriam sido suficientes pra atravessar aquela janela ruim.
MAX_TENTATIVAS = 5

# Pausa entre uma chamada e outra pra API do PNCP (entre municipios em
# main.py, entre editais em scripts/backfill_itens.py). Descobrimos
# rodando de verdade que bater a API em sequencia, sem pausa nenhuma,
# gera bastante erro 429 (limite de requisicoes), mesmo o limite nao
# sendo documentado em lugar nenhum. Essa pausa e uma prevencao, nao uma
# garantia. Fica aqui (nao em cada script separado) pra quem muda esse
# numero mudar um lugar so.
PAUSA_ENTRE_CHAMADAS_SEGUNDOS = 1.5

# Confirmado em chamada real (Tarefa 1.0): 1 e o codigo de situacao que
# corresponde a "Divulgada no PNCP", ou seja, um edital de verdade em aberto.
# Nao confiamos so no fato de o endpoint se chamar "proposta em aberto":
# ele pode devolver editais anulados dentro da mesma janela de datas.
#
# Importante: apesar do Swagger do PNCP dizer que esse campo e texto
# (type: string), a resposta real da API manda um numero sem aspas (ex.: 3,
# nao "3"). Comparar com o numero errado (bug corrigido nesta tarefa) faz
# TODO edital ser descartado, sem erro nenhum aparecer, silenciosamente.
SITUACAO_DIVULGADA_NO_PNCP = 1


def _fazer_requisicao(url, params, max_tentativas=MAX_TENTATIVAS):
    """Faz um GET com retry: tenta de novo em erro de rede, 429 (limite de
    requisicoes), 5xx (erro do servidor do PNCP) ou 422. Nao tenta de novo em
    outros erros (400, 404...), porque nesses casos o problema e no que a
    gente mandou, tentar de novo nao vai mudar o resultado.

    422 entrou na lista depois de um caso real (Rubinéia, 24/07): o mesmo
    parametro (sempre valido, vem do nosso municipios.csv) devolveu 422 uma
    vez e 200 normalmente logo em seguida, no meio de uma janela de varios
    500 e timeout do PNCP ("Failed to obtain JDBC Connection... HikariPool-1
    - Connection is not available"). Ou seja, nao e erro de parametro nosso,
    e mais um sintoma do banco de dados do PNCP sobrecarregado.
    """
    for tentativa in range(1, max_tentativas + 1):
        try:
            resposta = requests.get(url, params=params, timeout=TIMEOUT_SEGUNDOS)
        except requests.exceptions.RequestException as erro:
            logger.warning(
                "Erro de rede na tentativa %s/%s para %s: %s",
                tentativa, max_tentativas, url, erro,
            )
        else:
            # 204 "No Content" e uma resposta de SUCESSO: o PNCP usa esse
            # codigo quando a busca deu certo mas nao encontrou nenhum
            # edital (municipio pequeno, sem nada em aberto no periodo).
            # Nao e erro, entao nao tenta de novo.
            if resposta.status_code in (200, 204):
                return resposta

            if resposta.status_code not in (422, 429, 500, 502, 503, 504):
                # erro nosso (parametro errado, etc), tentar de novo nao ajuda
                resposta.raise_for_status()

            logger.warning(
                "PNCP respondeu %s na tentativa %s/%s para %s",
                resposta.status_code, tentativa, max_tentativas, url,
            )

        if tentativa < max_tentativas:
            espera_em_segundos = 2 ** tentativa  # 2s, depois 4s, depois 8s...
            logger.info("Esperando %ss antes de tentar de novo", espera_em_segundos)
            time.sleep(espera_em_segundos)

    raise RuntimeError(f"Falhou depois de {max_tentativas} tentativas: {url}")


def _montar_edital(item):
    """Transforma um item cru da resposta da API num objeto Edital."""
    orgao_entidade = item["orgaoEntidade"]
    unidade_orgao = item["unidadeOrgao"]

    link_pncp = "https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}".format(
        cnpj=orgao_entidade["cnpj"],
        ano=item["anoCompra"],
        sequencial=item["sequencialCompra"],
    )

    return Edital(
        numero_controle_pncp=item["numeroControlePNCP"],
        cnpj_orgao=orgao_entidade["cnpj"],
        ano_compra=item["anoCompra"],
        sequencial_compra=item["sequencialCompra"],
        orgao=orgao_entidade["razaoSocial"],
        municipio=unidade_orgao["municipioNome"],
        uf=unidade_orgao["ufSigla"],
        codigo_ibge=unidade_orgao["codigoIbge"],
        modalidade=item["modalidadeNome"],
        objeto=item["objetoCompra"],
        situacao=item["situacaoCompraNome"],
        data_encerramento_proposta=datetime.fromisoformat(item["dataEncerramentoProposta"]),
        informacao_complementar=item.get("informacaoComplementar"),
        valor_estimado=item.get("valorTotalEstimado"),
        link_sistema_origem=item.get("linkSistemaOrigem"),
        link_pncp=link_pncp,
    )


def extrair_cnpj_ano_sequencial(link_pncp):
    """Tira cnpj, ano e sequencial de dentro de um link_pncp ja montado por
    _montar_edital (formato .../editais/{cnpj}/{ano}/{sequencial}).

    Existe porque cnpj/ano/sequencial nao ficam guardados como colunas
    separadas no banco (so dentro do objeto Edital em memoria, durante a
    captura), entao qualquer coisa que precise deles depois de salvo
    recupera assim: primeiro o scripts/backfill_itens.py (Tarefa A.3),
    agora o painel tambem, pra buscar os documentos/anexos ao vivo
    (Tarefa B.1).
    """
    cnpj, ano, sequencial = link_pncp.rstrip("/").split("/")[-3:]
    return cnpj, int(ano), int(sequencial)


def buscar_contratacoes_com_proposta_aberta(codigo_municipio_ibge, dias_janela=90):
    """Busca, para um municipio, todos os editais com proposta em aberto
    dentro dos proximos `dias_janela` dias.

    Pagina automaticamente ate acabarem as paginas. Descarta, no proprio
    cliente, qualquer item que nao esteja com situacao "Divulgada no PNCP"
    ou que ja tenha passado do prazo de encerramento (a API pode devolver
    editais anulados dentro da janela pedida, confirmado na Tarefa 1.0).
    """
    data_final = (datetime.now() + timedelta(days=dias_janela)).strftime("%Y%m%d")
    agora = datetime.now()

    editais = []
    pagina = 1
    total_paginas = 1  # so sabemos o valor real depois da primeira resposta

    while pagina <= total_paginas:
        params = {
            "dataFinal": data_final,
            "codigoMunicipioIbge": codigo_municipio_ibge,
            "pagina": pagina,
            "tamanhoPagina": TAMANHO_PAGINA,
        }
        resposta = _fazer_requisicao(URL_CONTRATACOES_PROPOSTA, params)

        if resposta.status_code == 204:
            # sucesso, mas sem nenhum edital pra esse municipio no periodo
            logger.info("Municipio %s: nenhum edital em aberto no periodo", codigo_municipio_ibge)
            break

        corpo = resposta.json()

        total_paginas = corpo.get("totalPaginas", 1)
        logger.info(
            "Municipio %s: pagina %s/%s (%s registros no total)",
            codigo_municipio_ibge, pagina, total_paginas, corpo.get("totalRegistros", 0),
        )

        for item in corpo.get("data", []):
            if item.get("situacaoCompraId") != SITUACAO_DIVULGADA_NO_PNCP:
                continue

            edital = _montar_edital(item)
            if edital.data_encerramento_proposta <= agora:
                continue

            editais.append(edital)

        pagina += 1

    return editais


def buscar_itens_da_compra(cnpj, ano, sequencial):
    """Busca os itens de uma compra especifica e devolve a lista deles, um
    dicionario por item ja no formato que captura/banco.salvar_itens espera
    (numero_item, descricao, material_ou_servico, quantidade,
    valor_unitario_estimado, valor_total, tipo_beneficio).

    Essa chamada e feita edital por edital (nao existe outro jeito, o dado
    so mora aqui), entao so vale a pena chamar depois que o edital ja passou
    pelo filtro de palavra-chave.

    Tratamento de erro proprio: se essa chamada falhar (rede, timeout,
    servidor fora do ar), NAO derruba a execucao inteira. So registra um
    aviso no log e devolve None, e quem chamou entende None como "nao foi
    possivel buscar os itens deste edital" (usado tanto pro selo ME/EPP
    quanto pra lista completa de itens, Tarefa A.2).
    """
    identificador = f"{cnpj}/{ano}/{sequencial}"
    url = URL_ITENS_DA_COMPRA.format(cnpj=cnpj, ano=ano, sequencial=sequencial)

    try:
        resposta = _fazer_requisicao(url, params=None)
    except (RuntimeError, requests.exceptions.HTTPError) as erro:
        logger.warning(
            "Nao consegui buscar os itens do edital %s, vai ficar sem itens salvos: %s",
            identificador, erro,
        )
        return None

    itens_crus = resposta.json()
    return [
        {
            "numero_item": item["numeroItem"],
            "descricao": item.get("descricao"),
            "material_ou_servico": item.get("materialOuServicoNome"),
            "quantidade": item.get("quantidade"),
            "valor_unitario_estimado": item.get("valorUnitarioEstimado"),
            "valor_total": item.get("valorTotal"),
            "tipo_beneficio": item.get("tipoBeneficioNome"),
        }
        for item in itens_crus
    ]


def buscar_arquivos_da_compra(cnpj, ano, sequencial):
    """Busca a lista de documentos/anexos de uma compra especifica
    (edital, termo de referencia, etc.), cada um ja com a URL de download
    direto do PNCP (Tarefa B.1, Parte B da entrega 2).

    Endpoint nao documentado no Swagger oficial (mesma situacao do
    endpoint de itens), confirmado testando de verdade contra dois
    editais reais antes de codar isso (ver sondagem).

    Diferente dos itens, isso NUNCA e salvo no banco: o painel busca
    isso ao vivo, so quando o usuario abre o card (decisao explicita,
    pra nao criar tabela nova so pra um link de download).

    Tratamento de erro proprio: se a chamada falhar, devolve None (nao
    derruba a execucao). None e diferente de lista vazia: None significa
    "nao consegui buscar agora", lista vazia significa "esse edital
    realmente nao tem nenhum documento anexado".
    """
    identificador = f"{cnpj}/{ano}/{sequencial}"
    url = URL_ARQUIVOS_DA_COMPRA.format(cnpj=cnpj, ano=ano, sequencial=sequencial)

    try:
        resposta = _fazer_requisicao(url, params=None)
    except (RuntimeError, requests.exceptions.HTTPError) as erro:
        logger.warning(
            "Nao consegui buscar os documentos do edital %s: %s",
            identificador, erro,
        )
        return None

    documentos_crus = resposta.json()
    return [
        {
            "titulo": documento.get("titulo"),
            "tipo_documento": documento.get("tipoDocumentoNome"),
            "url": documento.get("url"),
        }
        for documento in documentos_crus
    ]
