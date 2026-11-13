"""Log em arquivo (um por dia) + console, e o alerta de erro por e-mail (equivale ao Error Trigger)."""
import logging
import smtplib
import traceback
from email.message import EmailMessage
from logging.handlers import TimedRotatingFileHandler

from .config import Config, abrir_smtp

_configurado = False


def configurar_log() -> logging.Logger:
    global _configurado
    log = logging.getLogger("central")
    if _configurado:
        return log
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s")
    arq = TimedRotatingFileHandler(Config.LOG_DIR / "central.log", when="midnight",
                                   backupCount=60, encoding="utf-8")
    arq.setFormatter(fmt)
    con = logging.StreamHandler()
    con.setFormatter(fmt)
    log.setLevel(logging.INFO)
    log.addHandler(arq)
    log.addHandler(con)
    _configurado = True
    return log


def alertar_erro(onde: str, exc: BaseException, contexto: dict | None = None) -> None:
    """Manda e-mail de erro. Nunca levanta exceção (não pode derrubar o fluxo)."""
    log = logging.getLogger("central")
    texto = (f"Erro em: {onde}\n\nContexto: {contexto or {}}\n\n"
             + "".join(traceback.format_exception(exc)))
    log.error(texto)
    if not (Config.EMAIL_ALERTA_ERRO and Config.SMTP_HOST) or Config.MODO_TESTE:
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[Central Líder] Erro em {onde}"
        msg["From"] = Config.SMTP_REMETENTE or Config.SMTP_USUARIO
        msg["To"] = Config.EMAIL_ALERTA_ERRO
        msg.set_content(texto)
        with abrir_smtp() as s:
            if Config.SMTP_USUARIO:
                s.login(Config.SMTP_USUARIO, Config.SMTP_SENHA)
            s.send_message(msg)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao enviar o e-mail de alerta de erro")
