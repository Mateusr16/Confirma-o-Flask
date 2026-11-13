"""Banco SQLite (substitui as Data Tables do n8n).

- Uma conexão por thread (Flask + agendador rodam em threads diferentes).
- WAL ligado: leituras do painel não travam enquanto o fluxo grava.
- Migrações: arquivos app/migracoes/NNN_nome.sql aplicados em ordem, uma vez só.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import Config

_local = threading.local()
_lock_escrita = threading.RLock()
MIGRACOES = Path(__file__).resolve().parent / "migracoes"


def conexao() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is None:
        Path(Config.SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(Config.SQLITE_PATH, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        _local.con = con
    return con


@contextmanager
def transacao():
    """Bloco de escrita atômico: ou grava tudo, ou nada."""
    con = conexao()
    with _lock_escrita:
        con.execute("BEGIN IMMEDIATE")
        try:
            yield con
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise


def consultar(sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conexao().execute(sql, params).fetchall()]


def consultar_um(sql: str, params=()) -> dict | None:
    r = conexao().execute(sql, params).fetchone()
    return dict(r) if r else None


def executar(sql: str, params=()) -> int:
    with transacao() as con:
        cur = con.execute(sql, params)
        return cur.lastrowid


def agora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def migrar() -> list[str]:
    con = conexao()
    con.execute(
        "CREATE TABLE IF NOT EXISTS _migracoes (nome TEXT PRIMARY KEY, aplicada_em TEXT NOT NULL)"
    )
    feitas = {r["nome"] for r in con.execute("SELECT nome FROM _migracoes")}
    aplicadas = []
    for arq in sorted(MIGRACOES.glob("*.sql")):
        if arq.name in feitas:
            continue
        with _lock_escrita:
            con.executescript(arq.read_text(encoding="utf-8"))
            con.execute("INSERT INTO _migracoes VALUES (?, ?)", (arq.name, agora_iso()))
            con.commit()
        aplicadas.append(arq.name)
    return aplicadas


def registrar_execucao(gatilho: str, status: str, detalhe: dict | None = None,
                       inicio: str | None = None, erro: str | None = None) -> int:
    """Equivale à lista de Executions do n8n."""
    return executar(
        "INSERT INTO execucoes (gatilho, status, inicio, fim, detalhe, erro) VALUES (?,?,?,?,?,?)",
        (gatilho, status, inicio or agora_iso(), agora_iso(),
         json.dumps(detalhe or {}, ensure_ascii=False, default=str), erro),
    )
