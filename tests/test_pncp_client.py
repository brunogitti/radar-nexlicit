"""
Testes do captura/pncp_client.py: itens de uma compra
(buscar_itens_da_compra), documentos/anexos (buscar_arquivos_da_compra) e
a extracao de cnpj/ano/sequencial do link_pncp. Nao bate na API de
verdade: troca requests.get por uma versao falsa, do mesmo jeito que
test_email_sender.py troca o smtplib.SMTP.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_pncp_client.py -v
"""

import requests

from captura import pncp_client


class _RespostaFalsa:
    """Imita o pedaco de requests.Response que buscar_itens_da_compra usa."""

    def __init__(self, status_code=200, corpo=None):
        self.status_code = status_code
        self._corpo = corpo or []

    def json(self):
        # uma resposta 204 de verdade nao tem corpo, entao .json() nela
        # quebra. Imitar isso aqui faz o teste pegar quem esquecer de
        # tratar o 204 antes de chamar .json().
        if self.status_code == 204:
            raise ValueError("204 nao tem corpo")
        return self._corpo

    def raise_for_status(self):
        raise requests.exceptions.HTTPError(f"status {self.status_code}")


def _itens_de_teste(primeiro_numero, quantidade):
    """Monta `quantidade` itens crus (no formato da API) com numeroItem
    seguidos, comecando em `primeiro_numero`."""
    return [
        {"numeroItem": numero, "descricao": f"ITEM {numero}"}
        for numero in range(primeiro_numero, primeiro_numero + quantidade)
    ]


def _get_que_serve_paginas(paginas, chamadas_feitas):
    """Devolve uma versao falsa de requests.get que age como o endpoint de
    itens: devolve a pagina pedida em params["pagina"] (1 = primeira da
    lista `paginas`) e, depois da ultima, devolve pagina vazia. Cada
    chamada fica registrada em `chamadas_feitas` pro teste conferir o que
    foi pedido."""

    def get_falso(url, params, timeout):
        chamadas_feitas.append(params)
        indice = params["pagina"] - 1
        corpo = paginas[indice] if indice < len(paginas) else []
        return _RespostaFalsa(200, corpo)

    return get_falso


def test_devolve_itens_no_formato_esperado_pelo_banco(monkeypatch):
    itens_crus_da_api = [
        {
            "numeroItem": 1,
            "descricao": "LOCAÇÃO DE VEICULOS.",
            "materialOuServico": "S",
            "materialOuServicoNome": "Serviço",
            "valorUnitarioEstimado": 4219.0,
            "valorTotal": 151884.0,
            "quantidade": 36.0,
            "tipoBeneficio": 4,
            "tipoBeneficioNome": "Sem benefício",
        },
    ]
    monkeypatch.setattr(
        pncp_client.requests, "get",
        _get_que_serve_paginas([itens_crus_da_api], []),
    )

    itens = pncp_client.buscar_itens_da_compra("46599809000182", 2026, 206)

    assert itens == [{
        "numero_item": 1,
        "descricao": "LOCAÇÃO DE VEICULOS.",
        "material_ou_servico": "Serviço",
        "quantidade": 36.0,
        "valor_unitario_estimado": 4219.0,
        "valor_total": 151884.0,
        "tipo_beneficio": "Sem benefício",
    }]


def test_pede_a_pagina_com_itens_por_pagina_em_toda_chamada(monkeypatch):
    # Este e o teste que pega o bug original: sem "pagina" e "tamanhoPagina",
    # a API devolve so 10 itens e o resto some sem erro nenhum.
    chamadas = []
    monkeypatch.setattr(
        pncp_client.requests, "get",
        _get_que_serve_paginas([_itens_de_teste(1, 5)], chamadas),
    )

    pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1)

    assert chamadas == [
        {"pagina": 1, "tamanhoPagina": pncp_client.ITENS_POR_PAGINA},
        {"pagina": 2, "tamanhoPagina": pncp_client.ITENS_POR_PAGINA},
    ]


def test_junta_varias_paginas_ate_a_pagina_vazia(monkeypatch):
    chamadas = []
    paginas = [_itens_de_teste(1, 500), _itens_de_teste(501, 120)]
    monkeypatch.setattr(
        pncp_client.requests, "get", _get_que_serve_paginas(paginas, chamadas),
    )

    itens = pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1)
    assert itens is not None

    assert len(itens) == 620
    assert [item["numero_item"] for item in itens] == list(range(1, 621))
    assert len(chamadas) == 3  # pagina 1, pagina 2 e a pagina 3 vazia que faz parar


def test_continua_quando_a_pagina_vem_menor_que_o_pedido_mas_ainda_ha_itens(monkeypatch):
    # Caso que a regra "parar se a pagina vier menor que o pedido" erraria:
    # a API corta cada pagina em 100 itens mesmo com ITENS_POR_PAGINA = 500.
    # O laco tem que seguir pedindo ate vir pagina vazia, senao a lista
    # voltaria a ficar incompleta (so 100 de 359 itens).
    assert pncp_client.ITENS_POR_PAGINA > 100

    chamadas = []
    paginas = [
        _itens_de_teste(1, 100),
        _itens_de_teste(101, 100),
        _itens_de_teste(201, 100),
        _itens_de_teste(301, 59),
    ]
    monkeypatch.setattr(
        pncp_client.requests, "get", _get_que_serve_paginas(paginas, chamadas),
    )

    itens = pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1)
    assert itens is not None

    assert len(itens) == 359
    assert len(chamadas) == 5  # as 4 paginas com item e a 5a, vazia, que faz parar


def test_pagina_cheia_seguida_de_pagina_vazia_nao_trava(monkeypatch):
    # Compra com exatamente ITENS_POR_PAGINA itens: a pagina 1 vem cheia e a
    # 2 vem vazia. Tem que devolver os itens e parar, sem laco infinito.
    chamadas = []
    paginas = [_itens_de_teste(1, pncp_client.ITENS_POR_PAGINA)]
    monkeypatch.setattr(
        pncp_client.requests, "get", _get_que_serve_paginas(paginas, chamadas),
    )

    itens = pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1)
    assert itens is not None

    assert len(itens) == pncp_client.ITENS_POR_PAGINA
    assert len(chamadas) == 2


def test_compra_sem_itens_devolve_lista_vazia(monkeypatch):
    monkeypatch.setattr(
        pncp_client.requests, "get",
        lambda url, params, timeout: _RespostaFalsa(200, []),
    )

    assert pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1) == []


def test_resposta_204_na_primeira_pagina_devolve_lista_vazia(monkeypatch):
    monkeypatch.setattr(
        pncp_client.requests, "get",
        lambda url, params, timeout: _RespostaFalsa(204),
    )

    assert pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1) == []


def test_resposta_204_depois_de_itens_para_e_devolve_o_que_ja_tinha(monkeypatch):
    def get_falso(url, params, timeout):
        if params["pagina"] == 1:
            return _RespostaFalsa(200, _itens_de_teste(1, 3))
        return _RespostaFalsa(204)

    monkeypatch.setattr(pncp_client.requests, "get", get_falso)

    itens = pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1)
    assert itens is not None

    assert [item["numero_item"] for item in itens] == [1, 2, 3]


def test_falha_de_rede_devolve_none_sem_travar(monkeypatch):
    # sem isso, os 3 tentativas do _fazer_requisicao esperariam 2s+4s de
    # verdade entre uma tentativa e outra, deixando o teste lento a toa.
    monkeypatch.setattr(pncp_client.time, "sleep", lambda segundos: None)

    def get_que_sempre_falha(url, params, timeout):
        raise requests.exceptions.ConnectionError("sem rede, de proposito")

    monkeypatch.setattr(pncp_client.requests, "get", get_que_sempre_falha)

    resultado = pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1)

    assert resultado is None


def test_falha_na_segunda_pagina_devolve_none_e_nunca_lista_parcial(monkeypatch):
    monkeypatch.setattr(pncp_client.time, "sleep", lambda segundos: None)

    def get_que_falha_na_pagina_2(url, params, timeout):
        if params["pagina"] == 1:
            return _RespostaFalsa(200, _itens_de_teste(1, 500))
        raise requests.exceptions.ConnectionError("caiu na pagina 2, de proposito")

    monkeypatch.setattr(pncp_client.requests, "get", get_que_falha_na_pagina_2)

    resultado = pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1)

    assert resultado is None


def test_trava_de_seguranca_devolve_none(monkeypatch):
    # Reduz a trava pra 3 paginas so pro teste ser rapido. A API falsa
    # sempre tem item novo, entao sem a trava o laco nunca acabaria.
    monkeypatch.setattr(pncp_client, "MAX_PAGINAS_ITENS", 3)

    def get_sem_fim(url, params, timeout):
        primeiro = (params["pagina"] - 1) * 10 + 1
        return _RespostaFalsa(200, _itens_de_teste(primeiro, 10))

    monkeypatch.setattr(pncp_client.requests, "get", get_sem_fim)

    assert pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1) is None


def test_pagina_repetida_devolve_none(monkeypatch):
    # API que ignora o parametro "pagina" e devolve sempre os mesmos itens:
    # sem a checagem de repeticao, o laco giraria ate a trava de seguranca.
    chamadas = []
    monkeypatch.setattr(
        pncp_client.requests, "get",
        lambda url, params, timeout: (
            chamadas.append(params) or _RespostaFalsa(200, _itens_de_teste(1, 10))
        ),
    )

    assert pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1) is None
    assert len(chamadas) == 2  # pagina 1 normal, pagina 2 igual a 1: desiste


def test_extrai_cnpj_ano_sequencial_do_link_pncp():
    link = "https://pncp.gov.br/app/editais/47842836000105/2026/118"

    cnpj, ano, sequencial = pncp_client.extrair_cnpj_ano_sequencial(link)

    assert cnpj == "47842836000105"
    assert ano == 2026
    assert sequencial == 118


def test_extrai_cnpj_ano_sequencial_ignora_barra_no_final():
    link = "https://pncp.gov.br/app/editais/47842836000105/2026/118/"

    cnpj, ano, sequencial = pncp_client.extrair_cnpj_ano_sequencial(link)

    assert (cnpj, ano, sequencial) == ("47842836000105", 2026, 118)


def test_devolve_documentos_no_formato_esperado_pelo_painel(monkeypatch):
    documentos_crus_da_api = [
        {
            "titulo": "EDITAL E ANEXOS - PREGAO 36.2026.pdf",
            "tipoDocumentoNome": "Edital",
            "url": "https://pncp.gov.br/pncp-api/v1/orgaos/47842836000105/compras/2026/118/arquivos/2",
        },
    ]
    monkeypatch.setattr(
        pncp_client.requests, "get",
        lambda url, params, timeout: _RespostaFalsa(200, documentos_crus_da_api),
    )

    documentos = pncp_client.buscar_arquivos_da_compra("47842836000105", 2026, 118)

    assert documentos == [{
        "titulo": "EDITAL E ANEXOS - PREGAO 36.2026.pdf",
        "tipo_documento": "Edital",
        "url": "https://pncp.gov.br/pncp-api/v1/orgaos/47842836000105/compras/2026/118/arquivos/2",
    }]


def test_compra_sem_documentos_devolve_lista_vazia(monkeypatch):
    monkeypatch.setattr(
        pncp_client.requests, "get",
        lambda url, params, timeout: _RespostaFalsa(200, []),
    )

    assert pncp_client.buscar_arquivos_da_compra("00000000000000", 2026, 1) == []


def test_falha_de_rede_ao_buscar_documentos_devolve_none_sem_travar(monkeypatch):
    monkeypatch.setattr(pncp_client.time, "sleep", lambda segundos: None)

    def get_que_sempre_falha(url, params, timeout):
        raise requests.exceptions.ConnectionError("sem rede, de proposito")

    monkeypatch.setattr(pncp_client.requests, "get", get_que_sempre_falha)

    resultado = pncp_client.buscar_arquivos_da_compra("00000000000000", 2026, 1)

    assert resultado is None
