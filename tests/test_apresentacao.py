"""
Testes do captura/apresentacao.py.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_apresentacao.py -v
"""

from datetime import datetime

from captura.apresentacao import formatar_selo_me_epp, formatar_status, formatar_valor
from captura.modelos import Edital


def _edital_de_teste(prazo=None, situacao="Divulgada no PNCP", valor_estimado=1000.0):
    return Edital(
        numero_controle_pncp="00000000000000-1-000001/2026",
        cnpj_orgao="00000000000000",
        ano_compra=2026,
        sequencial_compra=1,
        orgao="Prefeitura de Teste",
        municipio="Votuporanga",
        uf="SP",
        codigo_ibge="3557105",
        modalidade="Pregão - Eletrônico",
        objeto="Aquisição de material de limpeza",
        situacao=situacao,
        data_encerramento_proposta=prazo or datetime(2026, 12, 31, 8, 0),
        valor_estimado=valor_estimado,
    )


def _linha_anterior_de_teste(prazo=None, situacao="Divulgada no PNCP", valor_estimado=1000.0):
    return {
        "data_encerramento_proposta": (prazo or datetime(2026, 12, 31, 8, 0)).isoformat(),
        "situacao": situacao,
        "valor_estimado": valor_estimado,
    }


def test_formatar_valor_none_devolve_nao_informado():
    assert formatar_valor(None) == "não informado"


def test_formatar_valor_numero():
    assert formatar_valor(1000.0) == "R$ 1000.00"


def test_formatar_selo_none_devolve_nao_verificado():
    assert formatar_selo_me_epp(None) == "não verificado"


def test_formatar_selo_lista_vazia_devolve_none():
    assert formatar_selo_me_epp([]) is None


def test_formatar_selo_so_sem_beneficio_devolve_none():
    assert formatar_selo_me_epp(["Sem benefício"]) is None


def test_formatar_selo_com_beneficio_relevante():
    beneficios = ["Sem benefício", "Participação exclusiva para ME/EPP"]
    assert formatar_selo_me_epp(beneficios) == "Participação exclusiva para ME/EPP"


def test_formatar_selo_dois_beneficios_relevantes_ordenados_e_juntos():
    beneficios = ["Subcontratação para ME/EPP", "Participação exclusiva para ME/EPP"]
    resultado = formatar_selo_me_epp(beneficios)
    assert resultado == "Participação exclusiva para ME/EPP / Subcontratação para ME/EPP"


def test_formatar_status_novo():
    edital = _edital_de_teste()
    assert formatar_status(edital, "novo", None) == "NOVO"


def test_formatar_status_sem_mudanca():
    edital = _edital_de_teste()
    linha_anterior = _linha_anterior_de_teste()
    assert formatar_status(edital, "sem_mudanca", linha_anterior) == "já visto, sem mudança"


def test_formatar_status_atualizado_so_prazo_mudou():
    edital = _edital_de_teste(prazo=datetime(2027, 1, 15, 8, 0))
    linha_anterior = _linha_anterior_de_teste(prazo=datetime(2026, 12, 31, 8, 0))

    resultado = formatar_status(edital, "atualizado", linha_anterior)

    assert "prazo mudou de 31/12/2026 08h00 para 15/01/2027 08h00" in resultado
    assert resultado.startswith("ATUALIZADO (")


def test_formatar_status_atualizado_so_situacao_mudou():
    edital = _edital_de_teste(situacao="Encerrada")
    linha_anterior = _linha_anterior_de_teste(situacao="Divulgada no PNCP")

    resultado = formatar_status(edital, "atualizado", linha_anterior)

    assert "situação mudou de 'Divulgada no PNCP' para 'Encerrada'" in resultado


def test_formatar_status_atualizado_so_valor_mudou():
    edital = _edital_de_teste(valor_estimado=2000.0)
    linha_anterior = _linha_anterior_de_teste(valor_estimado=1000.0)

    resultado = formatar_status(edital, "atualizado", linha_anterior)

    assert "valor estimado mudou" in resultado


def test_formatar_status_atualizado_varias_coisas_mudam_juntas():
    edital = _edital_de_teste(situacao="Encerrada", valor_estimado=2000.0)
    linha_anterior = _linha_anterior_de_teste(situacao="Divulgada no PNCP", valor_estimado=1000.0)

    resultado = formatar_status(edital, "atualizado", linha_anterior)

    assert "situação mudou" in resultado
    assert "valor estimado mudou" in resultado
    assert "; " in resultado


def test_formatar_status_atualizado_sem_diferenca_detectavel():
    # status "atualizado" mas nada nos tres campos que formatar_status
    # compara mudou (pode acontecer se banco.classificar usar outro
    # criterio no futuro): sem detalhe nenhum pra listar, so o rotulo.
    edital = _edital_de_teste()
    linha_anterior = _linha_anterior_de_teste()

    assert formatar_status(edital, "atualizado", linha_anterior) == "ATUALIZADO"
