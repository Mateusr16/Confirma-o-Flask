"""Confere o .env e testa cada conexão SEM enviar nada (só leitura / login).

    python verificar_config.py
"""
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from app.config import Config, abrir_smtp  # noqa: E402

OK, FALHA, AVISO = "OK   ", "FALHA", "AVISO"
resultados = []


def teste(nome, fn):
    try:
        r = fn()
        resultados.append((OK, nome, r or ""))
    except Exception as exc:  # noqa: BLE001
        resultados.append((FALHA, nome, f"{type(exc).__name__}: {str(exc)[:200]}"))


def intranet():
    from app.integracoes.intranet import Intranet
    i = Intranet()
    i.login()
    html = i.lista_emails().get("data") or ""
    if 'name="senha"' in html or "name=senha" in html:
        raise RuntimeError("login não aceito (voltou a tela de login): confira INTRANET_USUARIO/INTRANET_SENHA")
    return f"login OK, página de e-mails com {html.count('@')} e-mails"


def digisac():
    from app.integracoes import digisac as d
    r = d.listar_usuarios()
    if r.get("error"):
        raise RuntimeError(r["error"])
    return f"token OK, {len(r.get('data') or [])} usuários"


def planilha():
    p = Path(Config.GOOGLE_CREDENCIAIS_JSON)
    if not p.exists():
        raise FileNotFoundError(f"arquivo da conta de serviço não existe: {p}")
    email = json.loads(p.read_text(encoding="utf-8")).get("client_email")
    from app.integracoes import planilha as pl
    try:
        linhas = pl.ler_linhas()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{exc} — compartilhe a planilha com {email} (Editor)") from exc
    cab = sorted({k for l in linhas for k in l} - {"row_number"})
    faltam = [c for c in ("Pedido", "Cliente", "RESPONSÁVEL", "CONFIRMADO", "MOTIVO", "DATA ENVIO CONF.") if c not in cab]
    aba = Config.PLANILHA_ABA or "gid=0"
    return f"aba '{aba}': {len(linhas)} linhas lidas" + (f"; colunas não encontradas: {faltam}" if faltam else "; colunas OK")


def smtp():
    with abrir_smtp() as s:
        s.login(Config.SMTP_USUARIO, Config.SMTP_SENHA)
    return f"login OK em {Config.SMTP_HOST}:{Config.SMTP_PORTA} (nenhum e-mail enviado)"


def gemini():
    import requests
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     params={"key": Config.GEMINI_API_KEY, "pageSize": 1000}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
    nomes = [m["name"] for m in r.json().get("models", [])]
    alvo = f"models/{Config.GEMINI_MODELO}"
    return f"chave OK; modelo {Config.GEMINI_MODELO} {'disponível' if alvo in nomes else 'NÃO ENCONTRADO na lista'}"


def rotas():
    from app.integracoes import rotas_geo
    r = rotas_geo.rota({"lat": -19.9167, "lon": -43.9345}, {"lat": -19.9856, "lon": -43.8466})
    if r.get("code") != "Ok":
        raise RuntimeError(str(r)[:150])
    return f"OSRM OK ({r['routes'][0]['distance'] / 1000:.1f} km BH→Nova Lima)"


def checar_env():
    avisos = []
    if not Path(RAIZ / ".env").exists():
        raise FileNotFoundError(".env não encontrado")
    obrig = ["INTRANET_USUARIO", "INTRANET_SENHA", "DIGISAC_URL", "DIGISAC_TOKEN", "PLANILHA_ID",
             "SMTP_HOST", "SMTP_USUARIO", "SMTP_SENHA", "GEMINI_API_KEY"]
    vazios = [k for k in obrig if not getattr(Config, k)]
    if vazios:
        raise ValueError(f"vazios: {vazios}")
    if "-" in Config.PLANILHA_ID and len(Config.PLANILHA_ID) == 36:
        avisos.append("PLANILHA_ID parece um ID do DigiSac, não da planilha")
    if not Config.MODO_TESTE:
        avisos.append("MODO_TESTE=false: o servidor vai ENVIAR de verdade")
    return "; ".join(avisos) or "todas as chaves preenchidas"


if __name__ == "__main__":
    teste(".env", checar_env)
    teste("Intranet", intranet)
    teste("DigiSac", digisac)
    teste("Planilha Google", planilha)
    teste("E-mail SMTP", smtp)
    teste("Gemini", gemini)
    teste("Rotas (OSRM)", rotas)
    print()
    for st, nome, det in resultados:
        print(f"[{st}] {nome:16} {det}")
    print()
    print("Tudo certo!" if all(r[0] == OK for r in resultados) else "Corrija os itens com FALHA e rode de novo.")
