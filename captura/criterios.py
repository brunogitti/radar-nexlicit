"""
Critérios que o painel e o e-mail semanal "Radar ativo" precisam repetir do
mesmo jeito. Fica num módulo próprio, e não em banco.py, para que o painel
e o e-mail contem "editais abertos" com UMA função só: se cada um tivesse a
sua, os dois números podiam divergir sem ninguém perceber.

Um edital está ABERTO quando:
  1. não foi excluído pelo PNCP (coluna excluido_em vazia);
  2. a situação é "Divulgada no PNCP" (suspenso, revogado e anulado não
     aceitam proposta, mesmo com prazo no futuro);
  3. o prazo da proposta ainda não chegou, comparado com a HORA de Brasília
     (não só a data: um prazo de hoje às 08h já passou às 17h).

Recebe os editais como dicionários, do jeito que
banco.consultar_historico devolve.
"""

from datetime import datetime

SITUACAO_DIVULGADA = "Divulgada no PNCP"


def edital_esta_aberto(edital, agora):
    """True se o edital (dicionário de banco.consultar_historico) está
    aberto em `agora`, um datetime em horário de Brasília."""
    if edital.get("excluido_em"):
        return False
    if edital["situacao"] != SITUACAO_DIVULGADA:
        return False
    return datetime.fromisoformat(edital["data_encerramento_proposta"]) > agora


def contar_editais_abertos(editais, agora):
    """Quantos dos editais da lista estão abertos em `agora`."""
    return sum(1 for edital in editais if edital_esta_aberto(edital, agora))
