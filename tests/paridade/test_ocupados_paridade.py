"""Paridade do agendamento Verificar chamados ocupados."""
import json

import pytest

from app import comum as C
from app.fluxos import ag_chamados_ocupados as O

from .conftest import igual, rodar_js

IGN = ("chamadoVerificadoEm", "desde")


def test_preparar_retomada_horario():
    linhas = [{"id": 1, "pedidoLider": "2", "status": "AGUARDANDO_CHAMADO_LIVRE",
               "dadosPedido": json.dumps({"contactId": "b", "phone": "55", "serviceId": "s"})},
              {"id": 2, "pedidoLider": "3", "status": "AGUARDANDO_CHAMADO_LIVRE",
               "dadosPedido": json.dumps({"contactId": "a", "phone": "55", "serviceId": "s"})},
              {"id": 3, "pedidoLider": "4", "status": "AGUARDANDO_CHAMADO_LIVRE", "dadosPedido": "{}"},
              {"id": 4, "pedidoLider": "5", "status": "AGUARDANDO", "dadosPedido": "{}"}]
    for agora in ("2026-11-13T14:00:00-03:00", "2026-11-13T18:00:00-03:00", "2026-11-14T10:00:00-03:00"):
        from datetime import datetime
        dt = datetime.fromisoformat(agora).astimezone(C.TZ)
        js = rodar_js_luxon("Preparar retomada do envio", linhas, agora)
        igual(js, O.preparar_retomada(linhas, dt))


def rodar_js_luxon(no, entrada, agora):
    # o nó usa DateTime.now().weekday: simula com o mesmo instante
    from .conftest import rodar_js as r
    import tests.paridade.conftest as cf
    return r(no, entrada, {}, agora=agora)


@pytest.mark.parametrize("resp", [{"data": []}, {"data": [{"isOpen": True, "contactId": "c1", "userId": "u9", "id": "t"}]},
                                  {"error": "x"}])
def test_avaliar_retomada(resp):
    pedido = {"pedidoLider": "97680", "contactId": "c1", "mensagem": "oi", "rowId": 5, "nomesUsuarios": {"u9": "JOYCE"},
              "chamadoEspera": {"verificacoes": 1, "desde": "2026-11-13T10:00:00Z", "chamadoSituacao": "OCUPADO"}}
    js = rodar_js("Avaliar chamado (retomada)", [resp], {"Timer retomada": [pedido]})
    py = O.avaliar_retomada(pedido, resp)
    js[0]["dadosPedidoAtualizado"] = json.loads(js[0]["dadosPedidoAtualizado"])
    py["dadosPedidoAtualizado"] = json.loads(py["dadosPedidoAtualizado"])
    igual(js, [py], ignorar=IGN)
