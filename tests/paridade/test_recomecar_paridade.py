"""Paridade do Recomeçar pedido / Trocar número (webhook central-lider-recomecar)."""
import json

import pytest

from app import comum as C
from app.fluxos import recomecar as R

from .conftest import igual, rodar_js

WH = "Central - Lider - Recomeçar Pedido"
DP = {"mensagem": "Olá, Rafi! A previsão de entrega do seu pedido *97680* é 27/02/2027.", "cpf": "114679806000076",
      "clienteLider": "RAFI GREEN", "phone": "5511999998888", "contactId": "c-old", "serviceId": R.SERVICES[0],
      "chamadoEspera": {"x": 1}, "lembreteConfirmacaoEm": "2026-11-16T16:00:00Z",
      "pedidosGrupo": [{"pedidoLider": "97680"}, {"pedidoLider": "97690"}]}
LINHA = {"id": 3, "pedidoLider": "97680", "status": "DATA_ENVIADA", "cliente": "RAFI GREEN", "phone": "5511999998888",
         "contactId": "c-old", "serviceId": R.SERVICES[0], "categoria": "", "resumoIA": "x", "enviadoEm": "2026-11-16T07:18:28.000-03:00",
         "dadosPedido": json.dumps(DP)}
B = {"pedidoLider": "11-97680", "motivo": "cliente pediu para falar com a esposa"}

CASOS = [
    ({**B, "novoTelefone": "(11) 98765-4321", "nomeContato": "anete  souza_!", "avisoContatoAntigo": "A partir de agora\r\nfalamos com a Anete"}, [LINHA]),
    (B, [LINHA]),
    ({**B, "novoTelefone": "11 99999-8888"}, [LINHA]),
    ({**B, "novoTelefone": "1133334444"}, [LINHA]),
    ({**B, "avisoContatoAntigo": "oi"}, [LINHA]),
    ({**B, "pedidoLider": ""}, [LINHA]),
    ({**B, "motivo": "abc"}, [LINHA]),
    (B, []),
    (B, [LINHA, LINHA]),
    (B, [{**LINHA, "status": "AGRUPADO", "dadosPedido": json.dumps({"agrupadoEm": "97600", "mensagem": "x"})}]),
    (B, [{**LINHA, "status": "OUTLET"}]),
    (B, [{**LINHA, "status": "BLOQUEADO"}]),
    (B, [{**LINHA, "status": "CONCLUIDO"}]),
    ({**B, "confirmarConcluido": True}, [{**LINHA, "status": "CONCLUIDO"}]),
    (B, [{**LINHA, "dadosPedido": json.dumps({**DP, "mensagem": " "})}]),
    (B, [{**LINHA, "dadosPedido": "{quebrado"}]),
    (B, [{**LINHA, "status": "PENDENTE_REVISAO"}]),
    (B, [{**LINHA, "status": "PENDENTE_RESPOSTA_TARDIA"}]),
    (B, [{**LINHA, "contactId": None, "dadosPedido": json.dumps({**DP, "contactId": None})}]),
    ({**B, "novoTelefone": "21987654321", "avisoContatoAntigo": "x"},
     [{**LINHA, "contactId": "", "dadosPedido": json.dumps({**DP, "contactId": ""})}]),
    ({**B, "novoTelefone": "21987654321"}, [{**LINHA, "dadosPedido": json.dumps({**DP, "cpf": "98182996000012"})}]),
    ({**B, "novoTelefone": "21987654321"}, [{**LINHA, "cliente": "", "dadosPedido": json.dumps({**DP, "cpf": "", "clienteLider": ""})}]),
]


@pytest.mark.parametrize("body,linhas", CASOS)
def test_validar(body, linhas):
    js = rodar_js("Validar recomeço", linhas or [{}], {WH: [{"body": body}]})
    igual(js, [R.validar_recomeco(body, linhas)])


V = R.validar_recomeco({**B, "novoTelefone": "(11) 98765-4321", "nomeContato": "Anete"}, [LINHA])


@pytest.mark.parametrize("res", [
    [{"data": []}, {"data": []}],
    [{"data": [{"id": "a", "serviceId": R.SERVICES[1], "data": {"number": "11987654321"}, "name": "A"},
               {"id": "x", "data": {"number": "21987654321"}}]},
     {"data": [{"id": "b", "serviceId": R.SERVICES[0], "data": {"number": "5511987654321"}, "internalName": "B"}]}],
    [{"data": [{"id": "a", "serviceId": "outro", "data": {"number": "5511987654321"}}]},
     {"data": [{"id": "b", "serviceId": R.SERVICES[1], "data": {"number": "5511987654321"}}]}],
    [{"data": []}, {"error": {"message": "500"}}],
    [{"data": []}],
])
def test_avaliar_busca(res):
    js = rodar_js("Avaliar busca (recomeço)", res, {"Validar recomeço": [V]})
    igual(js, [R.avaliar_busca(V, res)])


@pytest.mark.parametrize("criado", [{"id": "novo", "serviceId": R.SERVICES[1], "internalName": "X"}, {"id": "novo"},
                                    {"error": {"message": "número inválido"}}, {}])
def test_avaliar_criacao(criado):
    b = {**R.avaliar_busca(V, [{"data": []}, {"data": []}])}
    js = rodar_js("Avaliar criação (recomeço)", [criado], {"Avaliar busca (recomeço)": [b]})
    igual(js, [R.avaliar_criacao(b, criado)])


def test_contato_definido():
    mesmo = R.validar_recomeco(B, [LINHA])
    js = rodar_js("Contato definido (recomeço)", [{}], {"Validar recomeço": [mesmo]})
    igual(js, [R.contato_definido(mesmo, None)])
    c = R.avaliar_criacao(R.avaliar_busca(V, [{"data": []}, {"data": []}]), {"id": "n1"})
    js = rodar_js("Contato definido (recomeço)", [c], {"Validar recomeço": [V]})
    igual(js, [R.contato_definido(V, c)])
    js = rodar_js("Contato definido (recomeço)", [{"ok": True}], {"Validar recomeço": [V]})
    igual(js, [R.contato_definido(V, {"ok": True})])


AGORA = "2026-11-16T11:00:00.000Z"
AG_MS = C.iso_ms(AGORA)


@pytest.mark.parametrize("cenario", ["novo", "mesmo", "conflito", "conflito_vigia", "vigia_vencida", "erro_outros",
                                     "sem_contato", "nome_sem_ola", "concluido"])
def test_montar_recomeco(cenario):
    if cenario == "mesmo":
        c = R.contato_definido(R.validar_recomeco(B, [LINHA]), None)
    elif cenario == "concluido":
        c = R.contato_definido(R.validar_recomeco({**B, "confirmarConcluido": True}, [{**LINHA, "status": "CONCLUIDO"}]), None)
    else:
        v = R.validar_recomeco({**B, "novoTelefone": "(11) 98765-4321", "nomeContato": "anete souza",
                                "avisoContatoAntigo": "Agora falamos com a Anete"},
                               [LINHA if cenario != "nome_sem_ola" else {**LINHA, "dadosPedido": json.dumps({**DP, "mensagem": "Oi!"})}])
        c = R.contato_definido(v, R.avaliar_busca(v, [{"data": [{"id": "c-new", "serviceId": R.SERVICES[1],
                                                                  "data": {"number": "5511987654321"}}]}, {"data": []}]))
    outros = [{"pedidoLider": "97690", "status": "AGRUPADO"}, {"pedidoLider": "97680", "status": "DATA_ENVIADA"}]
    if cenario == "conflito":
        outros.append({"pedidoLider": "12345", "status": "AGUARDANDO_CONSULTOR"})
    if cenario == "conflito_vigia":
        outros.append({"pedidoLider": "12345", "status": "CONCLUIDO", "vigiaAte": "2026-11-16T09:00:00.000-03:00"})
    if cenario == "vigia_vencida":
        outros.append({"pedidoLider": "12345", "status": "CONCLUIDO", "vigiaAte": "2026-11-16T07:00:00.000-03:00"})
    if cenario == "erro_outros":
        outros.append({"error": "x"})
    if cenario == "sem_contato":
        c = {"ok": False}
    js = rodar_js("Montar recomeço", outros, {"Contato definido (recomeço)": [c]}, agora=AGORA)
    igual(js, [R.montar_recomeco(c, outros, AG_MS)])


def test_conferir_e_aviso():
    c = R.contato_definido(V, R.avaliar_criacao(R.avaliar_busca(V, [{"data": []}, {"data": []}]), {"id": "n1"}))
    m = R.montar_recomeco({**c, "avisoContatoAntigo": "Agora é com a Anete"}, [], AG_MS)
    ok = [{"pedidoLider": "97680", "status": "PENDENTE_REVISAO", "contactId": "n1", "dadosPedido": m["dadosPedido"]}]
    for linhas in (ok, [{**ok[0], "status": "AGUARDANDO"}], [], ok + ok, [{**ok[0], "dadosPedido": "{}"}]):
        js = rodar_js("Conferir gravação (recomeço)", linhas, {"Montar recomeço": [m]})
        igual(js, [R.conferir_gravacao(m, linhas)])
    for r in ({"id": "msg1"}, {"messageId": "m2"}, {"error": {"message": "fora do ar"}}, {}, {"error": "texto"}):
        js = rodar_js("Resultado do aviso (recomeço)", [r], {"Montar recomeço": [m]}, agora=AGORA)
        igual(js, [R.resultado_aviso(m, r, AG_MS)])


def test_resposta_final():
    c = R.contato_definido(V, R.avaliar_criacao(R.avaliar_busca(V, [{"data": []}, {"data": []}]), {"id": "n1"}))
    m = R.montar_recomeco(c, [], AG_MS)
    cf = {**m, "ok": True}
    av_ok = R.resultado_aviso({**m, "avisoAntigo": {"contactId": "c-old", "texto": "x"}}, {"id": "1"}, AG_MS)
    av_ruim = R.resultado_aviso({**m, "avisoAntigo": {"contactId": "c-old", "texto": "x"}}, {"error": {"message": "y"}}, AG_MS)
    for entrada, nodes, conv, aviso in [
        ({"ok": False, "resposta": {"ok": False, "erro": "x"}}, {}, None, None),
        ({"id": 1}, {"Conferir gravação (recomeço)": [cf], "Marcar recomeço na conversa": [{"id": 1}]}, {"id": 1}, None),
        ({"id": 1}, {"Conferir gravação (recomeço)": [cf], "Marcar recomeço na conversa": [{"error": "z"}]}, {"error": "z"}, None),
        (av_ok, {"Conferir gravação (recomeço)": [cf], "Marcar recomeço na conversa": [{"id": 1}],
                 "Resultado do aviso (recomeço)": [av_ok]}, {"id": 1}, av_ok),
        (av_ruim, {"Conferir gravação (recomeço)": [cf], "Marcar recomeço na conversa": [{"error": "z"}],
                   "Resultado do aviso (recomeço)": [av_ruim]}, {"error": "z"}, av_ruim),
        ({}, {}, None, None),
    ]:
        js = rodar_js("Resposta recomeço", [entrada], nodes)
        r = entrada.get("resposta")
        igual(js, [R.resposta_final(r, cf if "Conferir gravação (recomeço)" in nodes else None, conv, aviso)])
