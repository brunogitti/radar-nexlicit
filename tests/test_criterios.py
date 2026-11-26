"""
Testes do captura/criterios.py: o critério único de "edital aberto", usado
pelo painel e pelo e-mail semanal "Radar ativo".

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_criterios.py -v
"""

from datetime import datetime

from captura import criterios

AGORA = datetime(2026, 11, 24, 17, 0)


def _edital_de_teste(prazo="2026-12-10T09:00:00", situacao="Divulgada no PNCP", excluido_em=None):
    """Edital como banco.consultar_historico devolve (dicionario)."""
    return {
        "numero_controle_pncp": "00000000000000-1-000001/2026",
        "situacao": situacao,
        "data_encerramento_proposta": prazo,
        "excluido_em": excluido_em,
    }


def test_edital_divulgado_com_prazo_futuro_esta_aberto():
    assert criterios.edital_esta_aberto(_edital_de_teste(), AGORA) is True


def test_edital_excluido_nao_esta_aberto_mesmo_com_prazo_futuro():
    edital = _edital_de_teste(excluido_em="2026-11-24T10:00:00")

    assert criterios.edital_esta_aberto(edital, AGORA) is False


def test_edital_suspenso_nao_esta_aberto_mesmo_com_prazo_futuro():
    assert criterios.edital_esta_aberto(_edital_de_teste(situacao="Suspensa"), AGORA) is False


def test_edital_revogado_ou_anulado_nao_esta_aberto():
    assert criterios.edital_esta_aberto(_edital_de_teste(situacao="Revogada"), AGORA) is False
    assert criterios.edital_esta_aberto(_edital_de_teste(situacao="Anulada"), AGORA) is False


def test_prazo_de_hoje_que_ja_passou_nao_esta_aberto():
    # 08h de hoje, agora sao 17h: a data e hoje, mas a hora ja passou
    assert criterios.edital_esta_aberto(_edital_de_teste(prazo="2026-11-24T08:00:00"), AGORA) is False


def test_prazo_de_hoje_que_ainda_nao_chegou_esta_aberto():
    assert criterios.edital_esta_aberto(_edital_de_teste(prazo="2026-11-24T23:59:00"), AGORA) is True


def test_prazo_no_instante_exato_de_agora_nao_esta_aberto():
    assert criterios.edital_esta_aberto(_edital_de_teste(prazo="2026-11-24T17:00:00"), AGORA) is False


def test_excluido_em_vazio_ou_ausente_conta_como_nao_excluido():
    sem_a_chave = _edital_de_teste()
    del sem_a_chave["excluido_em"]

    assert criterios.edital_esta_aberto(sem_a_chave, AGORA) is True
    assert criterios.edital_esta_aberto(_edital_de_teste(excluido_em=""), AGORA) is True


def test_contar_editais_abertos_conta_so_os_abertos():
    editais = [
        _edital_de_teste(),
        _edital_de_teste(),
        _edital_de_teste(situacao="Suspensa"),
        _edital_de_teste(excluido_em="2026-11-24T10:00:00"),
        _edital_de_teste(prazo="2026-11-20T09:00:00"),
    ]

    assert criterios.contar_editais_abertos(editais, AGORA) == 2


def test_contar_editais_abertos_de_lista_vazia_e_zero():
    assert criterios.contar_editais_abertos([], AGORA) == 0
