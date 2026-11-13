"""Agendamento 'Verificar chamados ocupados (30 min)'.

Pedidos em AGUARDANDO_CHAMADO_LIVRE: em horário comercial (seg-sex 08:00-17:30) confere de novo o
chamado no DigiSac; se ficou livre, envia o template, transfere o chamado e passa para AGUARDANDO.
"""
import logging
import random
import time

from .. import comum as C
from .. import tabelas as T
from ..integracoes import digisac
from . import agendamento
from .f1_revisao import (DEPARTAMENTO_CENTRAL, USUARIO_TRANSFERENCIA, avaliar_chamado, listar_usuarios_todos,
                         mapa_nomes)

log = logging.getLogger("central")
CAMPOS_CHAMADO = ["chamadoLivre", "chamadoSituacao", "chamadoMotivo", "chamadoVerificadoEm", "chamadoId", "chamadoUserId",
                  "chamadoAtendente", "chamadoDepartamentoId", "rowId", "dadosPedidoAtualizado", "nomesUsuarios", "enviar"]


def em_horario_comercial(agora=None) -> bool:
    agora = agora or C.agora()
    hm = agora.strftime("%H:%M")
    return agora.isoweekday() in (1, 2, 3, 4, 5) and "08:00" <= hm <= "17:30"


def preparar_retomada(linhas: list[dict], agora=None, ignorar_horario: bool = False) -> list[dict]:
    """Nó 'Preparar retomada do envio'."""
    if not ignorar_horario and not em_horario_comercial(agora):
        return []
    out = []
    for r in linhas:
        if str(r.get("status") or "") != "AGUARDANDO_CHAMADO_LIVRE":
            continue
        dados = C.loads(r.get("dadosPedido"))
        if not isinstance(dados, dict) or not dados.get("contactId") or not dados.get("phone") or not dados.get("serviceId"):
            continue
        out.append({**dados, "pedidoLider": str(r.get("pedidoLider")), "rowId": r.get("id")})
    out.sort(key=lambda j: str(j.get("contactId")))
    return out


def avaliar_retomada(pedido: dict, resp: dict) -> dict:
    """Nó 'Avaliar chamado (retomada)'."""
    av = avaliar_chamado(pedido.get("contactId"), [resp], pedido.get("nomesUsuarios") or {})
    base = {k: v for k, v in pedido.items() if k not in CAMPOS_CHAMADO}
    esp = pedido.get("chamadoEspera") or {}
    dados = C.dumps({**base, "chamadoEspera": {**esp, **av, "desde": esp.get("desde") or av["chamadoVerificadoEm"],
                                                "verificacoes": int(float(esp.get("verificacoes") or 0)) + 1}})
    return {**base, **av, "dadosPedidoAtualizado": dados}


@agendamento("chamados_ocupados")
def verificar_chamados_ocupados(ignorar_horario: bool = False):
    linhas = T.get("AGUARDANDO_ENTREGA", {"status": "AGUARDANDO_CHAMADO_LIVRE"})
    fila = preparar_retomada(linhas, ignorar_horario=ignorar_horario)
    if not fila:
        return {"verificados": 0}
    nomes = mapa_nomes(listar_usuarios_todos())
    resultado = {"verificados": 0, "enviados": 0}
    for p in fila:
        p = {**p, "nomesUsuarios": nomes}
        time.sleep(round((5 + random.random()) * 10) / 10)          # Timer retomada
        resp = digisac.tickets_abertos(p.get("contactId"))
        a = avaliar_retomada(p, resp)
        resultado["verificados"] += 1
        filtro = {"pedidoLider": a["pedidoLider"], "status": "AGUARDANDO_CHAMADO_LIVRE"}
        if a["chamadoLivre"] is True:
            envio = digisac.enviar_template(a.get("phone"), a.get("serviceId"))
            if not (envio or {}).get("error"):
                digisac.transferir_chamado(a.get("contactId"), DEPARTAMENTO_CENTRAL, USUARIO_TRANSFERENCIA,
                                           f"{a['pedidoLider']} - {a.get('clienteLider')}")
                T.update("AGUARDANDO_ENTREGA", filtro, {
                    "contactId": a.get("contactId"), "serviceId": a.get("serviceId"), "phone": a.get("phone"),
                    "status": "AGUARDANDO", "template": "conf002", "enviadoEm": C.agora_iso(),
                    "pedidoLider": a["pedidoLider"], "mensagem": a.get("mensagem"), "cliente": a.get("clienteLider"),
                    "responsavel": a.get("RESPONSÁVEL"), "tipoMensagem": a.get("tipoMensagem"),
                    "anexoUrl": a.get("anexoUrl"), "dadosPedido": a["dadosPedidoAtualizado"]})
                resultado["enviados"] += 1
                continue
        T.update("AGUARDANDO_ENTREGA", filtro, {"dadosPedido": a["dadosPedidoAtualizado"]})
    log.info("Chamados ocupados: %s", resultado)
    return resultado
