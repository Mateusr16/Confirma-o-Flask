"""Operações das Data Tables do n8n, com a mesma semântica:
get · insert · update · upsert · delete_rows.

Filtro (where): dict coluna -> valor (igualdade) ou coluna -> (operador, valor).
Operadores: eq, neq, like, ilike, gt, gte, lt, lte, isEmpty, isNotEmpty, in.
Todas as condições são combinadas com AND (padrão do nó Data Table).
"""
from typing import Any

from . import db

TABELAS = {
    "AGUARDANDO_ENTREGA", "FLUXO_STATUS", "HISTORICO_PEDIDOS",
    "MENSAGENS_CLIENTE", "SEM_CONFIRMACAO_DIARIO", "BASE_CONHECIMENTO",
}
_colunas_cache: dict[str, set[str]] = {}

_OPS = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
        "like": "LIKE", "ilike": "LIKE"}


def _colunas(tabela: str) -> set[str]:
    if tabela not in TABELAS:
        raise ValueError(f"Tabela desconhecida: {tabela}")
    if tabela not in _colunas_cache:
        _colunas_cache[tabela] = {r["name"] for r in db.conexao().execute(f"PRAGMA table_info({tabela})")}
    return _colunas_cache[tabela]


def _checar(tabela: str, cols) -> None:
    validas = _colunas(tabela)
    ruins = [c for c in cols if c not in validas]
    if ruins:
        raise ValueError(f"Colunas inexistentes em {tabela}: {ruins}")


def _where(tabela: str, where: dict | None) -> tuple[str, list]:
    if not where:
        return "", []
    _checar(tabela, where.keys())
    partes, params = [], []
    for col, cond in where.items():
        op, val = cond if isinstance(cond, tuple) else ("eq", cond)
        if op == "isEmpty":
            partes.append(f"({col} IS NULL OR {col} = '')")
        elif op == "isNotEmpty":
            partes.append(f"({col} IS NOT NULL AND {col} != '')")
        elif op == "in":
            vals = list(val)
            if not vals:
                partes.append("0")
            else:
                partes.append(f"{col} IN ({','.join('?' * len(vals))})")
                params.extend(vals)
        elif op in _OPS:
            col_sql = f"LOWER({col})" if op == "ilike" else col
            partes.append(f"{col_sql} {_OPS[op]} ?")
            params.append(val.lower() if op == "ilike" and isinstance(val, str) else val)
        else:
            raise ValueError(f"Operador não suportado: {op}")
    return " WHERE " + " AND ".join(partes), params


def get(tabela: str, where: dict | None = None, ordem: str = "id",
        limite: int | None = None) -> list[dict]:
    w, p = _where(tabela, where)
    col_ordem = ordem.lstrip("-")
    _checar(tabela, [col_ordem])
    sql = f"SELECT * FROM {tabela}{w} ORDER BY {col_ordem} {'DESC' if ordem.startswith('-') else 'ASC'}"
    if limite:
        sql += f" LIMIT {int(limite)}"
    return db.consultar(sql, p)


def get_um(tabela: str, where: dict) -> dict | None:
    r = get(tabela, where, limite=1)
    return r[0] if r else None


def insert(tabela: str, valores: dict) -> dict:
    _checar(tabela, valores.keys())
    agora = db.agora_iso()
    dados = {**valores, "createdAt": agora, "updatedAt": agora}
    cols = list(dados)
    novo_id = db.executar(
        f"INSERT INTO {tabela} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [dados[c] for c in cols],
    )
    return get_um(tabela, {"id": novo_id})


def update(tabela: str, where: dict, valores: dict) -> list[dict]:
    """Atualiza as linhas que batem com o filtro e devolve as linhas atualizadas."""
    if not where:
        raise ValueError("update sem filtro não é permitido")
    _checar(tabela, valores.keys())
    w, p = _where(tabela, where)
    dados = {**valores, "updatedAt": db.agora_iso()}
    sets = ", ".join(f"{c} = ?" for c in dados)
    with db.transacao() as con:
        ids = [r["id"] for r in con.execute(f"SELECT id FROM {tabela}{w}", p)]
        if ids:
            con.execute(f"UPDATE {tabela} SET {sets} WHERE id IN ({','.join('?' * len(ids))})",
                        [*dados.values(), *ids])
    return get(tabela, {"id": ("in", ids)}) if ids else []


def upsert(tabela: str, where: dict, valores: dict) -> list[dict]:
    """Igual ao upsert do n8n: atualiza se achar pelo filtro, senão insere (filtro + valores)."""
    atualizadas = update(tabela, where, valores)
    if atualizadas:
        return atualizadas
    base = {k: v for k, v in where.items() if not isinstance(v, tuple)}
    return [insert(tabela, {**base, **valores})]


def delete_rows(tabela: str, where: dict) -> int:
    if not where:
        raise ValueError("delete sem filtro não é permitido")
    w, p = _where(tabela, where)
    with db.transacao() as con:
        return con.execute(f"DELETE FROM {tabela}{w}", p).rowcount


def json_campo(valor: Any, padrao=None):
    """Lê colunas que guardam JSON em texto (dadosPedido, chatConsultor, dados)."""
    import json
    if valor in (None, ""):
        return padrao
    if isinstance(valor, (dict, list)):
        return valor
    try:
        return json.loads(valor)
    except (TypeError, ValueError):
        return padrao
