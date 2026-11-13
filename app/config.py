"""Configuração lida do arquivo .env (equivale às credenciais do n8n)."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _bool(nome: str, padrao: bool = False) -> bool:
    return os.getenv(nome, str(padrao)).strip().lower() in ("1", "true", "sim", "yes")


class Config:
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "6050"))
    TZ_LOCAL = os.getenv("TZ_LOCAL", "America/Sao_Paulo")
    MODO_TESTE = _bool("MODO_TESTE", True)
    AGENDADOR_ATIVO = _bool("AGENDADOR_ATIVO", False)

    SQLITE_PATH = str(RAIZ / os.getenv("SQLITE_PATH", "dados/central_lider.db"))
    LOG_DIR = RAIZ / "logs"

    INTRANET_URL = os.getenv("INTRANET_URL", "http://192.168.0.6").rstrip("/")
    INTRANET_USUARIO = os.getenv("INTRANET_USUARIO", "")
    INTRANET_SENHA = os.getenv("INTRANET_SENHA", "")

    DIGISAC_URL = os.getenv("DIGISAC_URL", "").rstrip("/")
    DIGISAC_TOKEN = os.getenv("DIGISAC_TOKEN", "")
    DIGISAC_SERVICE_ID_1 = os.getenv("DIGISAC_SERVICE_ID_1", "")
    DIGISAC_SERVICE_ID_2 = os.getenv("DIGISAC_SERVICE_ID_2", "")
    DIGISAC_USUARIO_TRANSFERENCIA = os.getenv("DIGISAC_USUARIO_TRANSFERENCIA", "")

    GOOGLE_CREDENCIAIS_JSON = str(RAIZ / os.getenv("GOOGLE_CREDENCIAIS_JSON", "credenciais/google_service_account.json"))
    PLANILHA_ID = os.getenv("PLANILHA_ID", "")
    PLANILHA_ABA = os.getenv("PLANILHA_ABA", "").strip()

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORTA = int(os.getenv("SMTP_PORTA", "587"))
    SMTP_USUARIO = os.getenv("SMTP_USUARIO", "")
    SMTP_SENHA = os.getenv("SMTP_SENHA", "")
    SMTP_REMETENTE = os.getenv("SMTP_REMETENTE", "")
    SMTP_TLS = _bool("SMTP_TLS", True)
    EMAIL_ALERTA_ERRO = os.getenv("EMAIL_ALERTA_ERRO", "")

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODELO = os.getenv("GEMINI_MODELO", "gemini-2.5-flash-lite")

    OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
    NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")


def abrir_smtp():
    """Porta 465 = SSL direto (SMTP_SSL). Outras portas: SMTP com STARTTLS se SMTP_TLS=true."""
    import smtplib
    import ssl
    if Config.SMTP_PORTA == 465:
        return smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORTA, timeout=60,
                                context=ssl.create_default_context())
    s = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORTA, timeout=60)
    if Config.SMTP_TLS:
        s.starttls()
    return s
