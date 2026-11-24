"""
Testes do captura/relogio.py: a hora de Brasilia, e a conta de dias ate o
prazo que o painel usa. O relogio de verdade nunca e consultado: cada teste
troca _agora_em_utc por uma hora fixa, pra o resultado ser sempre o mesmo.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_relogio.py -v
"""

from datetime import date, datetime, timezone

from captura import relogio


def _fixar_agora_em_utc(monkeypatch, ano, mes, dia, hora, minuto=0):
    """Faz o relogio do Radar achar que agora e essa hora em UTC."""
    momento = datetime(ano, mes, dia, hora, minuto, tzinfo=timezone.utc)
    monkeypatch.setattr(relogio, "_agora_em_utc", lambda: momento)


def test_agora_em_brasilia_e_tres_horas_antes_de_utc(monkeypatch):
    _fixar_agora_em_utc(monkeypatch, 2026, 11, 23, 22, 0)

    assert relogio.agora_em_brasilia() == datetime(2026, 11, 23, 19, 0)


def test_agora_em_brasilia_nao_tem_marca_de_fuso(monkeypatch):
    # precisa ser "naive" pra poder comparar com o prazo do PNCP
    _fixar_agora_em_utc(monkeypatch, 2026, 11, 23, 22, 0)

    assert relogio.agora_em_brasilia().tzinfo is None


def test_virada_do_dia_em_utc_ainda_e_o_dia_anterior_em_brasilia(monkeypatch):
    # 01h UTC do dia 24 ainda e 22h do dia 23 em Brasilia
    _fixar_agora_em_utc(monkeypatch, 2026, 11, 24, 1, 0)

    assert relogio.hoje_em_brasilia() == date(2026, 11, 23)


def test_virada_do_dia_em_brasilia_acontece_as_03h_utc(monkeypatch):
    _fixar_agora_em_utc(monkeypatch, 2026, 11, 24, 3, 0)

    assert relogio.hoje_em_brasilia() == date(2026, 11, 24)


def test_dias_ate_o_prazo_prazo_de_hoje_a_noite_conta_zero_entre_21h_e_24h(monkeypatch):
    # 22h30 de Brasilia (01h30 UTC do dia seguinte): o painel antigo, com
    # o relogio em UTC, achava que ja era dia 24 e contava -1.
    _fixar_agora_em_utc(monkeypatch, 2026, 11, 24, 1, 30)
    prazo_hoje_as_23h59 = datetime(2026, 11, 23, 23, 59)

    assert relogio.dias_ate_o_prazo(prazo_hoje_as_23h59) == 0


def test_dias_ate_o_prazo_de_amanha_conta_um_as_23h_de_brasilia(monkeypatch):
    _fixar_agora_em_utc(monkeypatch, 2026, 11, 24, 2, 0)  # 23h em Brasilia, dia 23

    assert relogio.dias_ate_o_prazo(datetime(2026, 11, 24, 9, 0)) == 1


def test_dias_ate_o_prazo_ja_vencido_conta_negativo(monkeypatch):
    _fixar_agora_em_utc(monkeypatch, 2026, 11, 23, 15, 0)

    assert relogio.dias_ate_o_prazo(datetime(2026, 11, 22, 9, 0)) == -1


def test_dias_ate_o_prazo_ignora_a_hora_do_prazo(monkeypatch):
    _fixar_agora_em_utc(monkeypatch, 2026, 11, 23, 15, 0)

    assert relogio.dias_ate_o_prazo(datetime(2026, 11, 25, 0, 1)) == 2
    assert relogio.dias_ate_o_prazo(datetime(2026, 11, 25, 23, 59)) == 2
