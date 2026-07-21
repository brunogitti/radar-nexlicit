"""
Testes do captura/pncp_client.py, so da parte que busca os itens de uma
compra (buscar_itens_da_compra). Nao bate na API de verdade: troca
requests.get por uma versao falsa, do mesmo jeito que test_email_sender.py
troca o smtplib.SMTP.

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
        return self._corpo

    def raise_for_status(self):
        raise requests.exceptions.HTTPError(f"status {self.status_code}")


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
        lambda url, params, timeout: _RespostaFalsa(200, itens_crus_da_api),
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


def test_compra_sem_itens_devolve_lista_vazia(monkeypatch):
    monkeypatch.setattr(
        pncp_client.requests, "get",
        lambda url, params, timeout: _RespostaFalsa(200, []),
    )

    assert pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1) == []


def test_falha_de_rede_devolve_none_sem_travar(monkeypatch):
    # sem isso, os 3 tentativas do _fazer_requisicao esperariam 2s+4s de
    # verdade entre uma tentativa e outra, deixando o teste lento a toa.
    monkeypatch.setattr(pncp_client.time, "sleep", lambda segundos: None)

    def get_que_sempre_falha(url, params, timeout):
        raise requests.exceptions.ConnectionError("sem rede, de proposito")

    monkeypatch.setattr(pncp_client.requests, "get", get_que_sempre_falha)

    resultado = pncp_client.buscar_itens_da_compra("00000000000000", 2026, 1)

    assert resultado is None
