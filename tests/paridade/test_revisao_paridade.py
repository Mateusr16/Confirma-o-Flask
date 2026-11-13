"""Paridade do gatilho Decisão de Envio."""
import json

import pytest

from app.fluxos import f1_revisao as RV

from .conftest import igual, rodar_js

DADOS = {"pedidoLider": "97680", "mensagem": "Olá!\nTexto", "anexoUrl": "/files/LIDER.mp4", "contactId": "c1"}
IGN = ("decididoEm", "editadaEm", "dadosPedidoFinal", "chamadoVerificadoEm", "desde")


@pytest.mark.parametrize("body,status", [
    ({"decisao": "enviar"}, "PENDENTE_REVISAO"),
    ({"decisao": "enviar", "mensagemEditada": "Novo\r\ntexto "}, "PENDENTE_REVISAO"),
    ({"decisao": "cancelar"}, "PENDENTE_REVISAO"),
    ({"decisao": "enviar", "origem": "RESPOSTA_TARDIA", "mensagemPersonalizada": "Oi, tudo certo"}, "PENDENTE_RESPOSTA_TARDIA"),
    ({"decisao": "enviar", "origem": "RESPOSTA_TARDIA"}, "PENDENTE_RESPOSTA_TARDIA"),
    ({"decisao": "cancelar", "origem": "RESPOSTA_TARDIA"}, "PENDENTE_REVISAO"),
])
def test_decidir_revisao(body, status):
    linha = {"pedidoLider": "97680", "status": status, "dadosPedido": json.dumps(DADOS)}
    js = rodar_js("Decidir Revisão", [linha], {"Central - Lider - Decisão de Envio": [{"body": body}]})
    py = RV.decidir_revisao(body, linha)
    igual(js, [py] if py is not None else [], ignorar=IGN)


@pytest.mark.parametrize("resp", [
    {"data": []},
    {"data": [{"isOpen": True, "contactId": "c1", "userId": "f4a00c56-b35b-4c7c-a5d5-9f963757ba93", "id": "t1"}]},
    {"data": [{"isOpen": True, "contactId": "c1", "userId": "u9", "id": "t2", "departmentId": "d"}]},
    {"data": [{"isOpen": True, "contactId": "c1", "userId": None, "id": "t3"}]},
    {"data": [{"isOpen": True, "contactId": "OUTRO", "userId": "u9"}]},
    {"error": {"message": "timeout"}},
    {"x": 1},
])
def test_avaliar_chamado(resp):
    pedido = {"pedidoLider": "97680", "contactId": "c1"}
    usuarios = [{"data": [{"id": "u9", "name": "JOYCE LIMA"}]}]
    base = {**DADOS, "chamadoEspera": {"verificacoes": 2, "desde": "2026-11-13T10:00:00Z"}}
    js = rodar_js("Avaliar chamado (envio)", [resp], {"Timer envio Template": [pedido], "GET Listar usuarios": usuarios,
                                                       "Decidir Revisão": [{"dadosPedidoFinal": json.dumps(base)}]})
    av = RV.avaliar_chamado("c1", [resp], RV.mapa_nomes(usuarios))
    py = {**pedido, **av, "dadosPedidoAtualizado": RV.dados_com_espera(base, av)}
    js[0]["dadosPedidoAtualizado"] = json.loads(js[0]["dadosPedidoAtualizado"])
    py["dadosPedidoAtualizado"] = json.loads(py["dadosPedidoAtualizado"])
    igual(js, [py], ignorar=IGN)
