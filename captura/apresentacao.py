"""
Este modulo so transforma dado de Edital em texto pronto pra um humano
ler. Nao sabe nada de HTTP, banco ou e-mail: tanto o resumo impresso no
terminal (main.py) quanto o corpo do e-mail (entrega/resumo.py) usam
essas mesmas funcoes, pra nao repetir a mesma logica de formatacao em
dois lugares e correr o risco dos dois textos ficarem diferentes com o
tempo.
"""

from datetime import datetime


def formatar_valor(valor_estimado):
    if valor_estimado is None:
        return "não informado"
    return f"R$ {valor_estimado:.2f}"


def formatar_selo_me_epp(beneficios_itens):
    """Transforma a lista crua de beneficios num texto pra tela/e-mail, ou
    None se nao ha nada relevante pra mostrar (nenhum item verificado
    tinha beneficio diferente de "Sem beneficio").
    """
    if beneficios_itens is None:
        return "não verificado"

    beneficios_relevantes = sorted({b for b in beneficios_itens if b != "Sem benefício"})
    if not beneficios_relevantes:
        return None

    return " / ".join(beneficios_relevantes)


def formatar_status(edital, status, linha_anterior):
    """Transforma o status que o banco.classificar devolveu num texto pra
    tela/e-mail, incluindo o que mudou especificamente, quando der pra
    saber.
    """
    if status == "novo":
        return "NOVO"
    if status == "sem_mudanca":
        return "já visto, sem mudança"

    detalhes = []

    prazo_novo_iso = edital.data_encerramento_proposta.isoformat()
    if linha_anterior["data_encerramento_proposta"] != prazo_novo_iso:
        prazo_antigo = datetime.fromisoformat(linha_anterior["data_encerramento_proposta"])
        detalhes.append(
            f"prazo mudou de {prazo_antigo:%d/%m/%Y %Hh%M} para "
            f"{edital.data_encerramento_proposta:%d/%m/%Y %Hh%M}"
        )

    if linha_anterior["situacao"] != edital.situacao:
        detalhes.append(f"situação mudou de '{linha_anterior['situacao']}' para '{edital.situacao}'")

    if linha_anterior["valor_estimado"] != edital.valor_estimado:
        detalhes.append("valor estimado mudou")

    if not detalhes:
        return "ATUALIZADO"
    return "ATUALIZADO (" + "; ".join(detalhes) + ")"
