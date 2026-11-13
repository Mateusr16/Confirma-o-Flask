"""Porta única para tudo que sai do servidor e altera algo lá fora.

Em MODO_TESTE nada é enviado: a ação fica gravada em `envios_simulados`
para comparar com o que o n8n fez de verdade.
"""
import json
import logging
from typing import Any, Callable

from . import db
from .config import Config

log = logging.getLogger("central")


def externo(destino: str, acao: str, payload: Any, funcao: Callable[[], Any],
            retorno_teste: Any = None) -> Any:
    """Executa `funcao` de verdade, ou só registra quando MODO_TESTE=true.

    destino: digisac | email | intranet | planilha
    retorno_teste: o que devolver no modo teste (ex.: um id falso de mensagem)
    """
    if Config.MODO_TESTE:
        db.executar(
            "INSERT INTO envios_simulados (criado_em, destino, acao, payload) VALUES (?,?,?,?)",
            (db.agora_iso(), destino, acao, json.dumps(payload, ensure_ascii=False, default=str)),
        )
        log.info("[MODO_TESTE] %s/%s não enviado", destino, acao)
        return retorno_teste
    return funcao()
