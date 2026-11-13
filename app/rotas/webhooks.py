"""Mesmos caminhos do n8n (/webhook/<path>), para o painel e o DigiSac não mudarem nada."""
import logging
import threading
import time

from flask import Blueprint, jsonify, request

from .. import db
from ..fluxos import HANDLERS
from ..registro import alertar_erro

log = logging.getLogger("central")
bp = Blueprint("webhooks", __name__)

# path -> métodos aceitos (copiado da v28)
WEBHOOKS = {
    "central-lider": ["GET"],                 # Frontend (painel)
    "central-lider-pendencias": ["GET"],      # API Pendências
    "status-fluxo-lider": ["GET"],            # Status do disparo
    "disparar-fluxo-lider": ["POST"],         # Disparo pelo painel
    "central-lider-revisao": ["POST"],        # Decisão de Envio
    "central-lider-resolver": ["POST"],       # Resolver Pendência
    "central-lider-consultor": ["POST"],      # Consultor (Chat)
    "central-lider-recomecar": ["POST"],      # Recomeçar Pedido
    "digisac-resposta": ["POST"],             # Resposta do cliente (DigiSac)
}

# Estes respondem 200 na hora e processam em segundo plano
# (o DigiSac não pode ficar esperando a IA e a intranet).
ASSINCRONOS = {"digisac-resposta"}


def _dados_requisicao() -> dict:
    """Mesmo formato do item que o nó Webhook do n8n entrega: {headers, params, query, body}."""
    if request.is_json:
        corpo = request.get_json(silent=True)
    elif request.form:
        corpo = request.form.to_dict()
    else:
        corpo = {}
    return {
        "headers": {k.lower(): v for k, v in request.headers.items()},
        "params": {},
        "query": request.args.to_dict(),
        "body": corpo if corpo is not None else {},
        "webhookUrl": request.url,
    }


def _rodar(path: str, dados: dict, req_info: dict):
    inicio = db.agora_iso()
    resumo = {"query": dados.get("query"), "body": dados.get("body")}
    handler = HANDLERS.get(path)
    if handler is None:
        db.registrar_execucao(path, "nao_migrado", resumo, inicio)
        return {"erro": f"Gatilho '{path}' ainda não migrado para o Flask"}, 501
    try:
        resp, codigo = handler(dados, req_info)
        db.registrar_execucao(path, "ok", resumo, inicio)
        return resp, codigo
    except Exception as exc:  # noqa: BLE001
        try:
            db.registrar_execucao(path, "erro", resumo, inicio, erro=repr(exc))
        except Exception:  # noqa: BLE001
            log.exception("Falha ao registrar a execução com erro")
        alertar_erro(f"webhook {path}", exc, resumo)
        return {"erro": "Falha interna", "detalhe": str(exc)}, 500


def _criar_rota(path: str, metodos: list[str]):
    def view():
        dados = _dados_requisicao()
        req_info = {"metodo": request.method, "recebido_em": time.time()}
        if path in ASSINCRONOS:
            threading.Thread(target=_rodar, args=(path, dados, req_info),
                             name=f"wh-{path}", daemon=True).start()
            return jsonify({"recebido": True}), 200
        resp, codigo = _rodar(path, dados, req_info)
        if isinstance(resp, (dict, list)):
            return jsonify(resp), codigo
        return resp, codigo

    view.__name__ = "wh_" + path.replace("-", "_")
    bp.add_url_rule(f"/webhook/{path}", view_func=view, methods=metodos + ["OPTIONS"])


for _p, _m in WEBHOOKS.items():
    _criar_rota(_p, _m)


@bp.after_app_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@bp.get("/api/saude")
def saude():
    from ..config import Config
    pendentes = [p for p in WEBHOOKS if p not in HANDLERS]
    return jsonify({
        "ok": True,
        "modo_teste": Config.MODO_TESTE,
        "agendador_ativo": Config.AGENDADOR_ATIVO,
        "gatilhos_migrados": sorted(p for p in WEBHOOKS if p in HANDLERS),
        "gatilhos_pendentes": pendentes,
    })


@bp.post("/api/rodar/<nome>")
def rodar_agendamento(nome):
    """Roda um agendamento na hora (para testes). Ex.: POST /api/rodar/chamados_ocupados
    ?forcar=1 ignora a trava de horário comercial (só onde existir)."""
    from ..fluxos import JOBS
    fn = JOBS.get(nome)
    if fn is None:
        return jsonify({"erro": f"agendamento '{nome}' não existe ou ainda não foi migrado",
                        "disponiveis": sorted(JOBS)}), 404
    inicio = db.agora_iso()
    try:
        kw = {"ignorar_horario": True} if request.args.get("forcar") and "ignorar_horario" in fn.__code__.co_varnames else {}
        r = fn(**kw)
        db.registrar_execucao(f"agenda:{nome}", "ok", {"manual": True, "resultado": r}, inicio)
        return jsonify({"ok": True, "resultado": r})
    except Exception as exc:  # noqa: BLE001
        log.exception("Agendamento %s falhou", nome)
        return jsonify({"ok": False, "erro": f"{type(exc).__name__}: {exc}"}), 500
