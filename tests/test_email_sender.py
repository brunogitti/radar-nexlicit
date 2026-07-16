"""
Testes do entrega/email_sender.py. Nao mandam e-mail de verdade: usam um
SMTP "de mentira" (mock) no lugar do smtplib.SMTP real.

Como rodar (com o venv ativado, na pasta do projeto):
    python -m pytest tests/test_email_sender.py -v
"""

import smtplib

from entrega import email_sender


class _SmtpFalso:
    """Um SMTP de mentira: implementa so o que o email_sender.py usa
    (starttls, login, send_message, e o "with" pra abrir/fechar), sem
    conectar em lugar nenhum de verdade.
    """

    def __init__(self, *args, **kwargs):
        self.mensagens_enviadas = []

    def starttls(self):
        pass

    def login(self, usuario, senha):
        pass

    def send_message(self, mensagem):
        self.mensagens_enviadas.append(mensagem)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_sem_credenciais_no_env_nao_tenta_enviar(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)

    resultado = email_sender.enviar_email("destino@teste.com", "Assunto", "<p>Corpo</p>")

    assert resultado is False


def test_envio_com_sucesso_devolve_true(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "radar@teste.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "senha-de-teste")
    monkeypatch.setattr(smtplib, "SMTP", _SmtpFalso)

    resultado = email_sender.enviar_email("destino@teste.com", "Assunto", "<p>Corpo</p>")

    assert resultado is True


def test_falha_de_autenticacao_devolve_false_sem_travar(monkeypatch):
    class _SmtpQueFalhaNoLogin(_SmtpFalso):
        def login(self, usuario, senha):
            raise smtplib.SMTPAuthenticationError(535, b"credenciais invalidas")

    monkeypatch.setenv("GMAIL_USER", "radar@teste.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "senha-errada")
    monkeypatch.setattr(smtplib, "SMTP", _SmtpQueFalhaNoLogin)

    resultado = email_sender.enviar_email("destino@teste.com", "Assunto", "<p>Corpo</p>")

    assert resultado is False
