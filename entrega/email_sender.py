"""
Este modulo so sabe mandar e-mail via SMTP do Gmail. Nao sabe nada sobre
editais nem sobre o Radar: recebe destinatario, assunto e corpo em HTML
prontos, e manda. Se um dia trocarmos de Gmail pra um provedor tipo
SendGrid (por causa de dominio proprio), so este arquivo muda, o resto do
programa nem percebe.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

SERVIDOR_SMTP = "smtp.gmail.com"
PORTA_SMTP = 587
TIMEOUT_SEGUNDOS = 30

load_dotenv()


def enviar_email(destinatario, assunto, corpo_html):
    """Envia um e-mail HTML via SMTP do Gmail.

    Devolve True se enviou, False se falhou. Nunca deixa o erro subir: um
    problema de e-mail (senha errada no .env, Gmail fora do ar) nao pode
    travar a captura inteira, entao aqui a gente so registra um ERROR no
    log e devolve False, pro main.py seguir rodando.
    """
    usuario = os.getenv("GMAIL_USER")
    senha = os.getenv("GMAIL_APP_PASSWORD")

    if not usuario or not senha:
        logger.error(
            "GMAIL_USER e/ou GMAIL_APP_PASSWORD nao estao configurados no .env, nao da pra enviar e-mail"
        )
        return False

    mensagem = EmailMessage()
    mensagem["From"] = usuario
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content("Este e-mail precisa de um cliente que exiba HTML para ser lido corretamente.")
    mensagem.add_alternative(corpo_html, subtype="html")

    try:
        with smtplib.SMTP(SERVIDOR_SMTP, PORTA_SMTP, timeout=TIMEOUT_SEGUNDOS) as conexao:
            conexao.starttls()
            conexao.login(usuario, senha)
            conexao.send_message(mensagem)
    except smtplib.SMTPAuthenticationError as erro:
        logger.error("Falha de autenticacao no Gmail (confira o .env): %s", erro)
        return False
    except (smtplib.SMTPException, OSError) as erro:
        logger.error("Falha ao enviar e-mail: %s", erro)
        return False

    logger.info("E-mail enviado para %s", destinatario)
    return True
