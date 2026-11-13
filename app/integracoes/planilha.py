"""Planilha de confirmações (Google Sheets). Aba definida em PLANILHA_ABA (a v28 usava 'Página1' / gid=0).

Leitura igual ao nó 'Get row(s) in sheet': uma linha por registro, chaves = cabeçalho da linha 1,
valores como texto formatado, mais row_number (número real da linha na planilha).
Atualização igual ao nó Sheets 'update': procura a coluna de busca (Pedido ou row_number)
e altera SÓ a primeira linha que bate.
"""
import logging
import threading
import time

from ..config import Config
from .. import saida

log = logging.getLogger("central")
PLANILHA_ID_PADRAO = "1N0J3trZdbdDX4I1HMpsVGRrPG5j5v4fMxpI7kivvCo4"
_lock = threading.Lock()
_aba = None


def _worksheet():
    global _aba
    if _aba is None:
        import gspread
        gc = gspread.service_account(filename=Config.GOOGLE_CREDENCIAIS_JSON)
        livro = gc.open_by_key(Config.PLANILHA_ID or PLANILHA_ID_PADRAO)
        # PLANILHA_ABA no .env (nome da aba). Vazio = aba gid=0, como na v28.
        _aba = livro.worksheet(Config.PLANILHA_ABA) if Config.PLANILHA_ABA else livro.get_worksheet_by_id(0)
    return _aba


def _com_retry(fn, tentativas=3):
    ultimo = None
    for _ in range(tentativas):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            ultimo = exc
            time.sleep(1.5)
    raise ultimo


def ler_linhas() -> list[dict]:
    with _lock:
        valores = _com_retry(lambda: _worksheet().get_all_values())
    if not valores:
        return []
    cab = valores[0]
    linhas = []
    for i, row in enumerate(valores[1:], start=2):
        if not any(str(c).strip() for c in row):
            continue
        reg = {"row_number": i}
        for j, nome in enumerate(cab):
            if nome == "":
                continue
            reg[nome] = row[j] if j < len(row) else ""
        linhas.append(reg)
    return linhas


def _atualizar(coluna_busca: str, valor_busca, valores: dict) -> dict:
    aba = _worksheet()
    tudo = aba.get_all_values()
    cab = tudo[0] if tudo else []
    if coluna_busca == "row_number":
        linha = int(valor_busca)
    else:
        if coluna_busca not in cab:
            raise ValueError(f"Coluna '{coluna_busca}' não existe na planilha")
        idx = cab.index(coluna_busca)
        linha = None
        for i, row in enumerate(tudo[1:], start=2):
            if idx < len(row) and str(row[idx]) == str(valor_busca):
                linha = i
                break
        if linha is None:
            return {"atualizado": False, "motivo": "linha não encontrada"}
    import gspread.utils as gu
    celulas = []
    for col, val in valores.items():
        if col in (coluna_busca, "row_number") or col not in cab:
            continue
        celulas.append({"range": gu.rowcol_to_a1(linha, cab.index(col) + 1), "values": [[val]]})
    if celulas:
        aba.batch_update(celulas, value_input_option="USER_ENTERED")
    return {"atualizado": True, "row_number": linha}


def atualizar(coluna_busca: str, valor_busca, valores: dict) -> dict:
    """Ex.: atualizar('Pedido', '11-207476', {'CONFIRMADO': 'NÃO', 'MOTIVO': ...})
    Erros não derrubam o fluxo (onError=continueRegularOutput nos nós da v28)."""
    payload = {"busca": {coluna_busca: valor_busca}, "valores": valores}

    def real():
        try:
            with _lock:
                return _com_retry(lambda: _atualizar(coluna_busca, valor_busca, valores))
        except Exception as exc:  # noqa: BLE001
            log.error("Planilha: falha ao atualizar %s=%s: %s", coluna_busca, valor_busca, exc)
            return {"error": str(exc)}
    return saida.externo("planilha", "atualizar", payload, real, retorno_teste={"atualizado": "teste"})
