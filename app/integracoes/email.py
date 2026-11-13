"""E-mail (SMTP) — nós emailSend da v28 (todos com onError=continueRegularOutput + retry)."""
import logging
import smtplib
import time
from email.message import EmailMessage

from ..config import Config, abrir_smtp
from .. import saida

log = logging.getLogger("central")
REMETENTE_PADRAO = "mateus.oliveira@lider.design"


def _enviar(para: str, assunto: str, html: str) -> dict:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = Config.SMTP_REMETENTE or REMETENTE_PADRAO
    msg["To"] = para
    msg.set_content("Este e-mail precisa de um leitor com suporte a HTML.")
    msg.add_alternative(html, subtype="html")
    ultimo = None
    for _ in range(3):
        try:
            with abrir_smtp() as s:
                if Config.SMTP_USUARIO:
                    s.login(Config.SMTP_USUARIO, Config.SMTP_SENHA)
                s.send_message(msg)
            return {"enviado": True, "para": para}
        except Exception as exc:  # noqa: BLE001
            ultimo = exc
            time.sleep(1)
    log.error("E-mail não enviado para %s (%s): %s", para, assunto, ultimo)
    return {"error": str(ultimo)}


def enviar(para: str, assunto: str, html: str) -> dict:
    return saida.externo("email", "enviar", {"para": para, "assunto": assunto, "html": html},
                         lambda: _enviar(para, assunto, html), retorno_teste={"enviado": "teste"})
