"""
E-mail semanal de batimento ("Radar ativo"): um resumo curto, sem lista de
editais, que prova que a captura esta rodando. Se o e-mail de segunda-feira
nao chegar, alguma coisa quebrou (token vencido, captura travada).

Regras de quando enviar (funcao deve_enviar):
  - so em segunda-feira, no horario de Brasilia;
  - so a partir das 05h (uma captura de madrugada de segunda nao conta, a
    primeira a partir das 05h conta);
  - no maximo uma vez por dia (guardamos o dia do ultimo envio no banco).

Este modulo NAO manda o e-mail nem mexe no controle de envio: so decide,
calcula os numeros e monta o texto. Quem junta tudo e o main.py.

Limite honesto: o e-mail so prova que a captura rodou. Nao prova, sozinho,
que o disparo externo do cron-job.org esta ativo.
"""

import html
from datetime import datetime, timedelta

from captura import banco

# Chave da tabela metadados onde fica o horario do ultimo envio.
CHAVE_ULTIMO_ENVIO = "batimento_enviado_em"

SEGUNDA_FEIRA = 0  # datetime.weekday(): segunda = 0, terca = 1, ...
HORA_MINIMA_EM_BRASILIA = 5
DIAS_DO_RESUMO = 7


def deve_enviar(agora, ultimo_envio_iso):
    """True se hoje e dia de mandar o batimento.

    `agora` e um datetime em horario de Brasilia (captura/relogio.py).
    `ultimo_envio_iso` e o texto guardado no banco, ou None se nunca enviou.
    Texto que nao da pra ler como data conta como "nunca enviou": melhor um
    e-mail a mais do que ficar sem o aviso.
    """
    if agora.weekday() != SEGUNDA_FEIRA:
        return False
    if agora.hour < HORA_MINIMA_EM_BRASILIA:
        return False

    if ultimo_envio_iso:
        try:
            ultimo_envio = datetime.fromisoformat(ultimo_envio_iso)
        except ValueError:
            return True
        if ultimo_envio.date() == agora.date():
            return False

    return True


def montar_resumo(conexao, agora):
    """Junta os numeros do e-mail. Devolve um dicionario com:
    editais_abertos, editais_novos_na_semana, capturas_na_semana,
    capturas_com_falhas_na_semana, ultima_execucao (dicionario da linha
    mais recente da tabela execucoes, ou None se nao houver nenhuma) e
    maior_intervalo_em_horas (o maior tempo entre duas capturas seguidas na
    semana, ou None se houver menos de duas).

    O maior intervalo existe porque a "ultima captura" de um e-mail de
    segunda e sempre a que acabou de rodar, entao sozinha nao mostra se o
    Radar ficou parado no meio da semana. Um intervalo de 30 horas, por
    exemplo, mostra."""
    desde = agora - timedelta(days=DIAS_DO_RESUMO)
    execucoes = banco.consultar_execucoes_desde(conexao, desde)

    return {
        "maior_intervalo_em_horas": _maior_intervalo_em_horas(execucoes),
        "editais_abertos": banco.contar_editais_abertos(conexao, agora),
        "editais_novos_na_semana": banco.contar_editais_vistos_desde(conexao, desde),
        "capturas_na_semana": len(execucoes),
        "capturas_com_falhas_na_semana": sum(1 for e in execucoes if e["resultado"] != "completa"),
        "ultima_execucao": execucoes[0] if execucoes else None,
    }


def _maior_intervalo_em_horas(execucoes):
    """Maior tempo, em horas, entre duas capturas consecutivas. Recebe a
    lista como banco.consultar_execucoes_desde devolve (da mais recente pra
    mais antiga). None se houver menos de duas capturas."""
    momentos = sorted(datetime.fromisoformat(e["executada_em"]) for e in execucoes)
    if len(momentos) < 2:
        return None
    intervalos = [depois - antes for antes, depois in zip(momentos, momentos[1:])]
    return max(intervalos).total_seconds() / 3600


def montar_assunto(agora):
    return f"Radar ativo: resumo da semana - {agora:%d/%m/%Y}"


def _texto_da_ultima_execucao(ultima_execucao):
    if ultima_execucao is None:
        return "nenhuma registrada"

    quando = datetime.fromisoformat(ultima_execucao["executada_em"])
    texto = f"{quando:%d/%m/%Y %Hh%M} (horário de Brasília), "
    if ultima_execucao["resultado"] == "completa":
        texto += f"completa, {ultima_execucao['municipios_consultados']} municípios consultados"
    else:
        texto += (
            f"com falhas: {ultima_execucao['municipios_com_falha']} de "
            f"{ultima_execucao['municipios_consultados']} municípios ficaram de fora"
        )
    return texto


def montar_corpo_html(resumo):
    """Corpo do e-mail em HTML simples (mesma ideia do entrega/resumo.py)."""
    ultima = _texto_da_ultima_execucao(resumo["ultima_execucao"])
    maior_intervalo = resumo["maior_intervalo_em_horas"]
    texto_intervalo = "sem dados suficientes" if maior_intervalo is None else f"{maior_intervalo:.0f} h"
    # Primeiro o que diz se o Radar esta vivo, depois o que ele encontrou.
    linhas = [
        ("Última captura bem-sucedida", ultima),
        (f"Execuções nos últimos {DIAS_DO_RESUMO} dias", resumo["capturas_na_semana"]),
        ("Dessas, com municípios de fora", resumo["capturas_com_falhas_na_semana"]),
        ("Maior intervalo entre duas capturas na semana", texto_intervalo),
        ("Editais abertos no banco", resumo["editais_abertos"]),
        (f"Editais novos nos últimos {DIAS_DO_RESUMO} dias", resumo["editais_novos_na_semana"]),
    ]
    itens = "".join(
        f'<p style="margin:4px 0;">{html.escape(str(rotulo))}: <strong>{html.escape(str(valor))}</strong></p>'
        for rotulo, valor in linhas
    )
    return f"""
    <html><body style="font-family:Arial,sans-serif; color:#12233D;">
        <h2 style="margin-bottom:8px;">Radar ativo</h2>
        <p style="margin:4px 0 12px 0;">O Radar NexLicit está rodando. Resumo da semana:</p>
        {itens}
        <p style="margin:16px 0 0 0; font-size:12px; color:#666;">
            Este aviso sai na primeira captura de segunda-feira, a partir das 05h de Brasília.
            Se ele não chegar, algo na captura precisa de atenção.
        </p>
    </body></html>
    """
