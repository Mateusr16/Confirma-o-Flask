"""Paridade dos agendamentos: vigilância, reenvio, lembrete 13h, encerramento e varredura tardia."""
import json
from datetime import datetime, timedelta

import pytest

from app import comum as C
from app.fluxos import ag_rotinas as A

from .conftest import igual, rodar_js

AGORA_DT = C.agora().replace(microsecond=0)
AGORA = AGORA_DT.astimezone().isoformat()
AG_MS = int(AGORA_DT.timestamp() * 1000)


def antes(minutos=0, horas=0, dias=0, fmt="local"):
    d = AGORA_DT - timedelta(minutes=minutos, hours=horas, days=dias)
    if fmt == "utc":
        return C.iso_utc_de_ms(int(d.timestamp() * 1000))
    if fmt == "naive":
        return d.replace(tzinfo=None).isoformat(timespec="seconds")
    return d.isoformat(timespec="milliseconds")


def _sem_ts(lista, campo="chatConsultorNovo"):
    out = json.loads(json.dumps(lista, default=str))
    for o in out:
        if isinstance(o.get(campo), str):
            v = json.loads(o[campo])
            for m in v:
                m.pop("ts", None)
            o[campo] = v
    return out


# ------------------------------------------------------------------ vigilância
def test_vigilancia():
    perg = lambda m: {"role": "ia", "tipo": "pergunta", "texto": "?", "ts": antes(minutos=m, fmt="utc")}  # noqa: E731
    lemb = lambda m: {"role": "ia", "tipo": "lembrete", "texto": "l", "ts": antes(minutos=m, fmt="utc")}  # noqa: E731
    linhas = [
        {"id": 1, "pedidoLider": "1", "status": "AGUARDANDO_CONSULTOR", "chatConsultor": json.dumps([perg(30)])},
        {"id": 2, "pedidoLider": "2", "status": "AGUARDANDO_CONSULTOR", "chatConsultor": json.dumps([perg(90)]), "cliente": "ANA"},
        {"id": 3, "pedidoLider": "3", "status": "AGUARDANDO_CONSULTOR", "chatConsultor": json.dumps([perg(400), lemb(100)])},
        {"id": 4, "pedidoLider": "4", "status": "AGUARDANDO_CONSULTOR", "chatConsultor": json.dumps([perg(400), lemb(200)])},
        {"id": 5, "pedidoLider": "5", "status": "AGUARDANDO_CONSULTOR", "chatConsultor": json.dumps([perg(900)] + [lemb(500)] * 4)},
        {"id": 6, "pedidoLider": "6", "status": "AGUARDANDO_CONSULTOR", "chatConsultor": "", "respondidoEm": antes(minutos=61)},
        {"id": 7, "pedidoLider": "7", "status": "AGUARDANDO_CONSULTOR", "chatConsultor": None, "respondidoEm": None, "enviadoEm": None},
        {"id": 8, "pedidoLider": "8", "status": "CONCLUIDO", "vigiaAte": antes(minutos=5), "contactId": "c8"},
        {"id": 9, "pedidoLider": "9", "status": "CONCLUIDO", "vigiaAte": antes(minutos=-30), "contactId": "c9"},
        {"id": 10, "pedidoLider": "10", "status": "TRANSFERIDO", "vigiaAte": antes(minutos=5), "contactId": "c10"},
        {"id": 11, "pedidoLider": "11", "status": "CONCLUIDO", "vigiaAte": "lixo", "contactId": ""},
        {"id": 12, "pedidoLider": "12", "status": "CONCLUIDO", "vigiaAte": ""},
        {"id": 13, "pedidoLider": " ", "status": "CONCLUIDO", "vigiaAte": antes(minutos=5)},
        {"pedidoLider": "14", "status": "CONCLUIDO", "vigiaAte": antes(minutos=5)},
    ]
    js = rodar_js("Selecionar ações da varredura", linhas, {}, agora=AGORA)
    igual(_sem_ts(js), _sem_ts(A.selecionar_acoes_vigilancia(linhas, AG_MS)))


# ------------------------------------------------------------------ reenvio
def test_reenvio():
    b = {"status": "AGUARDANDO", "phone": "5511999998888", "serviceId": "s1", "template": "conf002"}
    linhas = [
        {**b, "pedidoLider": "1", "contactId": "c1", "enviadoEm": antes(horas=3)},
        {**b, "pedidoLider": "2", "contactId": "c1", "enviadoEm": antes(horas=4)},
        {**b, "pedidoLider": "3", "contactId": "c2", "enviadoEm": antes(minutos=30)},
        {**b, "pedidoLider": "4", "contactId": "c3", "enviadoEm": antes(horas=80)},
        {**b, "pedidoLider": "5", "contactId": "c4", "enviadoEm": antes(horas=2), "template": "conf002_reenvio"},
        {**b, "pedidoLider": "6", "contactId": "c5", "enviadoEm": antes(horas=2), "phone": ""},
        {**b, "pedidoLider": "7", "contactId": "c6", "enviadoEm": None},
        {**b, "pedidoLider": "8", "contactId": "c7", "enviadoEm": antes(horas=2, fmt="naive")},
        {**b, "pedidoLider": "9", "contactId": "c8", "enviadoEm": antes(horas=2), "status": "DATA_ENVIADA"},
    ]
    js = rodar_js("Filtrar reenvio elegível", linhas, {}, agora=AGORA)
    igual(js, A.filtrar_reenvio(linhas, AG_MS))


# ------------------------------------------------------------------ lembrete 13h
def _de(r, **kw):
    return {**r, **kw}


def test_lembrete():
    dp = lambda **k: json.dumps({"mensagem": "Olá, Rafi! ...", **k})  # noqa: E731
    base = {"status": "DATA_ENVIADA", "categoria": "", "cliente": "123.456 - RAFI GREEN", "tipoMensagem": "DATA_ENTREGA"}
    linhas = [
        {**base, "id": 1, "pedidoLider": "200", "contactId": "c1", "respondidoEm": antes(horas=2), "dadosPedido": dp(pedidosGrupo=[{"pedidoLider": "11-0150"}])},
        {**base, "id": 2, "pedidoLider": "150", "contactId": "c1", "status": "AGRUPADO", "dadosPedido": json.dumps({"agrupadoEm": "200"})},
        {**base, "id": 3, "pedidoLider": "300", "contactId": "c2", "respondidoEm": antes(horas=2), "dadosPedido": "{}",
         "cliente": "MOVEIS LTDA"},
        {**base, "id": 4, "pedidoLider": "400", "contactId": "c3", "respondidoEm": antes(horas=2), "dadosPedido": "{}",
         "cliente": "joão  silva", "tipoMensagem": "PRIMEIRA_CONFIRMACAO"},
        {**base, "id": 5, "pedidoLider": "500", "contactId": "c4", "respondidoEm": antes(minutos=20), "dadosPedido": "{}"},
        {**base, "id": 6, "pedidoLider": "600", "contactId": "c5", "respondidoEm": antes(horas=2), "dadosPedido": "{}"},
        {**base, "id": 7, "pedidoLider": "601", "contactId": "c5", "status": "AGUARDANDO", "dadosPedido": "{}"},
        {**base, "id": 8, "pedidoLider": "700", "contactId": "c6", "respondidoEm": antes(horas=2), "dadosPedido": "{}"},
        {**base, "id": 9, "pedidoLider": "800", "contactId": "c7", "respondidoEm": antes(horas=2),
         "dadosPedido": dp(lembreteConfirmacaoEm="x")},
        {**base, "id": 10, "pedidoLider": "900", "contactId": "c8", "respondidoEm": antes(horas=2), "dadosPedido": "{}",
         "categoria": "ACEITA"},
        {**base, "id": 11, "pedidoLider": "901", "contactId": "c8", "respondidoEm": antes(horas=3), "dadosPedido": "{}"},
        {**base, "id": 12, "pedidoLider": "1000", "contactId": "c9", "respondidoEm": antes(horas=2), "dadosPedido": "{}"},
        {**base, "id": 13, "pedidoLider": "999", "contactId": "c9", "respondidoEm": antes(horas=3), "dadosPedido": "{}"},
    ]
    msgs = [{"contactId": "c6", "papel": "CLIENTE", "ts": AG_MS - 30 * 60000},
            {"contactId": "c1", "papel": "CLIENTE", "ts": AG_MS - 5 * 3600000}, {"contactId": None}]
    js = rodar_js("Filtrar lembrete elegível", msgs, {"Ler AGUARDANDO_ENTREGA (lembrete)": linhas}, agora=AGORA)
    py = A.filtrar_lembrete(linhas, msgs, AG_MS)
    igual(js, py)
    assert {x["contactId"] for x in py} == {"c1", "c2", "c3", "c9"}
    js = rodar_js("Filtrar lembrete elegível", msgs + [{"error": "x"}], {"Ler AGUARDANDO_ENTREGA (lembrete)": linhas}, agora=AGORA)
    igual(js, A.filtrar_lembrete(linhas, msgs + [{"error": "x"}], AG_MS))


def test_pode_enviar_lembrete():
    r1 = {"id": 1, "pedidoLider": "200", "contactId": "c1", "status": "DATA_ENVIADA", "categoria": "", "respondidoEm": "2026-11-16T09:00:00.000-03:00",
          "dadosPedido": json.dumps({"a": 1})}
    item = {"contactId": "c1", "rowIds": [1], "respondidoEmOriginal": [r1["respondidoEm"]], "mensagem": "Boa tarde!",
            "chamadoSituacao": "CHAMADO_MEU", "chamadoMotivo": "ok"}
    casos = [
        (item, [r1]), ({**item, "chamadoSituacao": "OCUPADO", "chamadoMotivo": "Chamado aberto com JOYCE."}, [r1]),
        (item, [r1, {"id": 2, "contactId": "c1", "status": "AGUARDANDO_CONSULTOR"}]), (item, []),
        (item, [{**r1, "categoria": "ACEITA"}]), (item, [{**r1, "respondidoEm": "outro"}]),
        (item, [{**r1, "dadosPedido": json.dumps({"lembreteConfirmacaoEm": "x"})}]), (item, [{"error": "x"}]),
        ({**item, "respondidoEmOriginal": ["null"]}, [{**r1, "respondidoEm": None}]),
    ]
    for it, atuais in casos:
        js = rodar_js("Pode enviar lembrete?", atuais or [{}], {"Avaliar chamado (lembrete)": [it]})
        py = A.pode_enviar_lembrete(it, atuais)
        for o in (js[0], py):
            for l in o["linhasMarcar"]:
                l["dadosPedido"] = json.loads(l["dadosPedido"])
                l["dadosPedido"].pop("lembreteConfirmacaoEm", None)
        igual(js, [py])


# ------------------------------------------------------------------ encerramento sem retorno
SHEET = [
    {"row_number": 2, "Pedido": "11-100", "Cliente": "ANA", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"row_number": 3, "Pedido": "11-200", "Cliente": "BIA", "CONFIRMADO": "SIM", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"row_number": 4, "Pedido": "11-300", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"row_number": 5, "Pedido": "11-400", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"row_number": 6, "Pedido": "11-500", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"row_number": 7, "Pedido": "11-600", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"row_number": 8, "Pedido": "11-650", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"row_number": 9, "Pedido": "11-700", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"row_number": 10, "Pedido": "", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
    {"Pedido": "11-800"},
    {"row_number": 12, "Pedido": "11-900", "CONFIRMADO": "", "MOTIVO": "", "DATA ENVIO CONF.": ""},
]
TABELA = [
    {"id": 1, "pedidoLider": "100", "status": "AGUARDANDO", "contactId": "c1", "responsavel": "JOYCE", "cliente": "ANA"},
    {"id": 2, "pedidoLider": "200", "status": "DATA_ENVIADA", "contactId": "c2"},
    {"id": 3, "pedidoLider": "300", "status": "DATA_ENVIADA", "contactId": "c3"},
    {"id": 4, "pedidoLider": "301", "status": "AGUARDANDO_CONSULTOR", "contactId": "c3"},
    {"id": 5, "pedidoLider": "400", "status": "AGUARDANDO_CHAMADO_LIVRE", "contactId": "",
     "dadosPedido": json.dumps({"contactId": "c4", "chamadoEspera": {"chamadoAtendente": "JOYCE"}})},
    {"id": 6, "pedidoLider": "500", "status": "TRANSFERIDO", "contactId": "c5"},
    {"id": 7, "pedidoLider": "600", "status": "AGRUPADO", "contactId": "c1", "dadosPedido": json.dumps({"agrupadoEm": "100"})},
    {"id": 8, "pedidoLider": "650", "status": "AGUARDANDO", "contactId": ""},
    {"id": 9, "pedidoLider": "700", "status": "AGUARDANDO_CHAMADO_LIVRE", "contactId": "",
     "dadosPedido": json.dumps({"chamadoEspera": {"chamadoSituacao": "FILA_SEM_ATENDENTE"}})},
    {"id": 10, "pedidoLider": "900", "status": "CONCLUIDO", "contactId": "c9"},
]


def test_filtrar_sem_retorno():
    js = rodar_js("Filtrar sem retorno elegível", TABELA, {"Ler planilha de confirmações": SHEET})
    igual(js, A.filtrar_sem_retorno(SHEET, TABELA))


def test_filtrar_sem_retorno_varredura():
    enc = {"acao": "ENCERRAR", "linhas": [{"id": 1, "pedidoLider": "100", "dataRef": "2026-11-13"},
                                          {"id": 5, "pedidoLider": "400", "dataRef": "2026-11-12"}], "ids": ["1", "5"]}
    js = rodar_js("Filtrar sem retorno elegível", TABELA, {"Ler planilha de confirmações": SHEET,
                                                           "Analisar respostas (varredura tardia)": [{"acao": "RESUMO"}, enc]})
    py = A.filtrar_sem_retorno(SHEET, TABELA, {"ids": set(enc["ids"]), "dia": {str(l["id"]): l["dataRef"] for l in enc["linhas"]}})
    igual(js, py)
    assert [x["dataRef"] for x in py] == ["2026-11-13", "2026-11-12", "2026-11-13"]


@pytest.mark.parametrize("resp", [
    {"body": {"data": []}}, {"error": "x"}, {"body": {"data": [{"isOpen": True, "contactId": "c4", "userId": None}]}},
    {"body": {"data": [{"isOpen": True, "contactId": "c4", "userId": "u1"}]}},
    {"body": {"data": [{"isOpen": True, "contactId": "c4", "userId": A.MEUS_USER_IDS[0]}]}},
    {"body": {"data": [{"isOpen": True, "contactId": "c4"}]}}, {"body": {"data": [{"isOpen": True, "contactId": "zz"}]}},
    {"body": "texto"}, {"body": [{"isOpen": False, "contactId": "c4"}]},
])
def test_reconferir_fila(resp):
    orig = {"contactId": "c4", "pedidoLider": "400", "chamadoOcupado": True, "fecharChamado": True}
    js = rodar_js("Reconferir fila (encerramento)", [resp], {"Chamado ocupado? (encerramento)": [orig]})
    igual(js, [A.reconferir_fila(orig, resp)])


# ------------------------------------------------------------------ varredura tardia
HOJE = C.hoje_iso()
ONTEM = (AGORA_DT - timedelta(days=1)).strftime("%Y-%m-%d")
ANTEONTEM = (AGORA_DT - timedelta(days=2)).strftime("%Y-%m-%d")


def _tabelas():
    sem_conf = [
        {"pedidoLider": "100", "contactId": "c1", "dataRef": ONTEM, "status": "SEM_RETORNO_TEMPLATE",
         "registradoEm": f"{ONTEM}T16:20:05.000-03:00"},
        {"pedidoLider": "101", "contactId": "c1", "dataRef": ONTEM, "status": "RESPONDEU_DEPOIS",
         "registradoEm": f"{ONTEM}T16:20:06.000-03:00"},
        {"pedidoLider": "102", "contactId": "c2", "dataRef": ANTEONTEM, "status": "SEM_RETORNO_CONFIRMACAO",
         "registradoEm": f"{ANTEONTEM}T16:20:00.000-03:00"},
        {"pedidoLider": "103", "contactId": "", "dataRef": ONTEM, "status": "SEM_RETORNO_TEMPLATE", "registradoEm": "x"},
        {"pedidoLider": "104", "contactId": "c4", "dataRef": ONTEM, "status": "SEM_RETORNO_TEMPLATE", "registradoEm": ""},
        {"pedidoLider": "105", "contactId": "c5", "dataRef": HOJE, "status": "SEM_RETORNO_TEMPLATE", "registradoEm": f"{HOJE}T07:00:00Z"},
        {"pedidoLider": "", "contactId": "c6"},
    ]
    linhas = [
        {"id": 1, "pedidoLider": "100", "status": "SEM_RETORNO_CLIENTE", "contactId": "c1", "enviadoEm": f"{ONTEM}T07:18:28.000-03:00",
         "createdAt": f"{ONTEM}T07:00:00", "dadosPedido": json.dumps({"clienteLider": "ANA", "mensagem": "Olá"}), "cliente": "ANA"},
        {"id": 2, "pedidoLider": "200", "status": "AGUARDANDO", "contactId": "c7", "enviadoEm": f"{ONTEM}T08:00:00.000-03:00",
         "createdAt": f"{ONTEM}T07:00:00", "dadosPedido": "{}"},
        {"id": 3, "pedidoLider": "300", "status": "DATA_ENVIADA", "contactId": "", "enviadoEm": None,
         "createdAt": f"{ANTEONTEM}T07:00:00", "dadosPedido": json.dumps({"contactId": "c8"})},
        {"id": 4, "pedidoLider": "400", "status": "AGUARDANDO", "contactId": "c9", "createdAt": f"{HOJE}T07:00:00", "dadosPedido": "{}"},
        {"id": 5, "pedidoLider": "500", "status": "CONCLUIDO", "contactId": "c10", "createdAt": f"{ONTEM}T07:00:00"},
        {"id": 6, "pedidoLider": "201", "status": "AGRUPADO", "contactId": "c7", "createdAt": f"{ONTEM}T07:00:00",
         "dadosPedido": json.dumps({"agrupadoEm": "200"})},
    ]
    historico = [{"pedidoLider": "102", "arquivadoEm": f"{ONTEM}T23:00:00Z",
                  "dados": json.dumps({"pedidoLider": "102", "status": "SEM_RETORNO_CLIENTE", "enviadoEm": f"{ANTEONTEM}T09:00:00Z"})}]
    msgs = [{"contactId": "c1", "messageId": "m1", "papel": "CLIENTE", "texto": "ok", "ts": C.iso_ms(f"{ONTEM}T07:30:00-03:00")},
            {"contactId": "c1", "messageId": "lider-1", "papel": "BOT", "texto": "programada", "ts": C.iso_ms(f"{ONTEM}T07:31:00-03:00")},
            {"contactId": "c7", "messageId": "m9", "papel": "CLIENTE", "texto": "", "ts": None,
             "recebidoEm": f"{ONTEM}T09:00:00.000-03:00"}]
    return sem_conf, linhas, historico, msgs


NOMES = ("Ler SEM_CONFIRMACAO (varredura tardia)", "Ler AGUARDANDO_ENTREGA (varredura tardia)",
         "Ler HISTORICO_PEDIDOS (varredura tardia)", "Ler MENSAGENS_CLIENTE (varredura tardia)")


def test_selecionar_contatos_tardia():
    t = _tabelas()
    js = rodar_js("Selecionar contatos (varredura tardia)", [{}], dict(zip(NOMES, t)))
    py = A.selecionar_contatos_tardia(*t[:3])
    igual(js, py)
    assert {c["contactId"] for c in py} == {"c1", "c7", "c8"}


def test_analisar_respostas_tardia():
    t = _tabelas()
    contatos = A.selecionar_contatos_tardia(*t[:3])
    idx = {c["contactId"]: i for i, c in enumerate(contatos)}
    ms = lambda s: C.iso_utc_de_ms(C.iso_ms(s))  # noqa: E731
    paginas = [
        (idx["c1"], {"data": [
            {"id": "m1", "contactId": "c1", "isFromMe": False, "timestamp": ms(f"{ONTEM}T07:30:00-03:00"), "data": {"text": "ok"}},
            {"id": "m2", "contactId": "c1", "isFromMe": False, "timestamp": ms(f"{ONTEM}T18:00:00-03:00"), "data": {"text": "Pode ser dia 20?"}},
            {"id": "t1", "contactId": "c1", "type": "ticket", "timestamp": ms(f"{ONTEM}T18:01:00-03:00")},
            {"id": "m3", "contactId": "c1", "isFromMe": True, "timestamp": ms(f"{ONTEM}T18:05:00-03:00"), "text": "Vou verificar"},
            {"id": "m4", "contactId": "c1", "isFromMe": False, "createdAt": ms(f"{HOJE}T06:00:00-03:00")}]}),
        (idx["c7"], {"data": [{"id": "m9", "contactId": "c7", "isFromMe": False, "timestamp": ms(f"{ONTEM}T09:00:00-03:00")}]}),
        (idx["c7"], {"data": []}),
        (idx["c8"], {"data": [{"id": "z", "contactId": "outro", "timestamp": ms(f"{ONTEM}T09:00:00-03:00")}]}),
    ]
    itens = [{"json": j, "pairedItem": {"item": i}} for i, j in paginas]
    nodes = {**dict(zip(NOMES, t)), "Selecionar contatos (varredura tardia)": contatos}
    js = rodar_js("Analisar respostas (varredura tardia)", itens, nodes)
    py = A.analisar_respostas_tardia(contatos, paginas, t[1], t[2], t[3])
    for o in js + py:
        if isinstance(o.get("dadosPedido"), str):
            o["dadosPedido"] = json.loads(o["dadosPedido"])
            o["dadosPedido"]["respostaTardia"].pop("detectadoEm", None)
    igual(js, py)
    acoes = [o["acao"] for o in py]
    assert "CARTAO" in acoes and "GRAVAR_MSG" in acoes
    # c7 sem resposta nova -> pedido aberto de ontem vai para ENCERRAR; c8 falhou (API não filtrou)
    res = py[-1]
    assert "c8" in res["falhas"]
