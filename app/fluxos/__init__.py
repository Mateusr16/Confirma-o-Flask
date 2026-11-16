"""Cada gatilho do n8n vira uma função aqui.

Assinatura: handler(dados: dict, req_info: dict) -> (corpo, status_http)
Enquanto uma etapa não foi migrada, o gatilho responde 501 e fica registrado.
"""
from typing import Callable

Handler = Callable[[dict, dict], tuple]

HANDLERS: dict[str, Handler] = {}
JOBS: dict[str, Callable[[], None]] = {}


def gatilho(nome: str):
    def deco(fn):
        HANDLERS[nome] = fn
        return fn
    return deco


def agendamento(nome: str):
    def deco(fn):
        JOBS[nome] = fn
        return fn
    return deco


# Os módulos de cada etapa se registram ao serem importados.
from . import (status, painel, f1_disparo, f1_resolver, f1_revisao, ag_chamados_ocupados, f2_resposta,  # noqa: E402,F401
               consultor, recomecar, ag_rotinas)
