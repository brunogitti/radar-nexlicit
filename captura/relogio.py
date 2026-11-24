"""
Relogio do Radar: um lugar so que responde "que horas sao em Brasilia?".

Por que existe: o PNCP devolve dataEncerramentoProposta em horario de
Brasilia, mas SEM marcar fuso (ex.: "2026-12-01T09:00:00"). Confirmado no
portal em 23/11/2026 (edital 49576416000141/2026/359: API 09:00, portal
09:00 de Brasilia). Ja o relogio do computador muda conforme onde o codigo
roda: no GitHub Actions e no Streamlit Cloud e UTC (3 horas na frente de
Brasilia), na maquina do Bruno e Brasilia. Comparar o prazo com
datetime.now() dava resultado diferente em cada lugar.

Regra: tudo que COMPARA com o prazo da proposta, ou conta dias ate ele,
usa agora_em_brasilia(). Os carimbos de registro (visto_em, atualizado_em)
NAO usam: ficam como sempre foram, pra nao criar um salto de 3 horas no
historico ja gravado.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# O Brasil nao tem horario de verao desde 2019, mas usar o nome do fuso
# (e nao "menos 3 horas") deixa o codigo certo se isso um dia mudar.
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


def _agora_em_utc():
    """Hora atual em UTC, com fuso marcado. Separada so pra o teste poder
    trocar o relogio por uma hora fixa."""
    return datetime.now(timezone.utc)


def agora_em_brasilia():
    """Hora atual em Brasilia, SEM marca de fuso (naive).

    Sem marca de proposito: o prazo vindo do PNCP tambem e naive, e o
    Python nao deixa comparar um datetime com fuso com um sem fuso.
    """
    return _agora_em_utc().astimezone(FUSO_BRASILIA).replace(tzinfo=None)


def hoje_em_brasilia():
    """Data de hoje em Brasilia."""
    return agora_em_brasilia().date()


def dias_ate_o_prazo(prazo):
    """Quantos dias faltam do dia de hoje (Brasilia) ate o dia do prazo.
    Conta dias de calendario: prazo hoje as 23h59 = 0, amanha = 1, ontem = -1.
    """
    return (prazo.date() - hoje_em_brasilia()).days
