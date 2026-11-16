"""Paridade da tela Consultas da IA (webhook central-lider-consultor)."""
import json
from datetime import timedelta

import pytest

from app import comum as C
from app.fluxos import consultor as K

from .conftest import igual, rodar_js

WH = "Central - Lider - Consultor (Chat)"


def _sem_ts(x):
    """chatConsultor / dadosPedidoNovo são JSON em texto: compara sem os carimbos de hora."""
    x = json.loads(json.dumps(x, default=str))
    for o in (x if isinstance(x, list) else [x]):
        for campo in ("chatConsultor", "dadosPedidoNovo"):
            if isinstance(o.get(campo), str):
                v = json.loads(o[campo])
                if isinstance(v, list):
                    for m in v:
                        m.pop("ts", None)
                elif isinstance(v, dict) and isinstance(v.get("registroContato"), dict):
                    v["registroContato"].pop("em", None)
                o[campo] = v
    return x


FUTURA = (C.agora().date() + timedelta(days=40)).strftime("%Y-%m-%d")
PASSADA = (C.agora().date() - timedelta(days=1)).strftime("%d/%m/%Y")
CHAT = json.dumps([{"role": "cliente", "texto": "o montador vem junto?", "ts": "2026-11-16T10:00:00.000Z"},
                   {"role": "ia", "tipo": "pergunta", "texto": "Cliente perguntou...", "ts": "2026-11-16T10:00:01.000Z"}])
DP = {"pedidoLider": "97680", "clienteLider": "MATEUS RIBEIRO", "tipoMensagem": "DATA_ENTREGA",
      "entregas": [{"data": "27/02/2027", "itens": [{"descricao": "MESA"}]}], "Pedido": "11-97680"}
ROW = {"id": 7, "pedidoLider": "97680", "status": "AGUARDANDO_CONSULTOR", "cliente": "MATEUS RIBEIRO", "contactId": "c1",
       "responsavel": "JOYCE SILVA", "tipoMensagem": "DATA_ENTREGA", "resumoIA": "Cliente perguntou do montador",
       "mensagem": "Olá! A previsão de entrega é 27/02/2027.", "chatConsultor": CHAT, "vigiaAte": None,
       "dadosPedido": json.dumps(DP)}

CASOS = [
    ({"id": 7, "acao": "responder", "texto": "Sim, a montagem é feita na entrega."}, ROW),
    ({"id": 7, "acao": "RESPONDER", "texto": "  "}, ROW),
    ({"id": 7, "acao": "TRANSFERIR", "texto": "cliente quer negociar", "resultado": "CONFIRMADO"}, ROW),
    ({"id": 7, "acao": "TRANSFERIR"}, ROW),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"}, ROW),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "ADIADO", "dataAdiamento": FUTURA}, ROW),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "ADIADO", "dataAdiamento": PASSADA}, ROW),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "ADIADO", "dataAdiamento": "31/02/2030"}, ROW),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "ADIADO"}, ROW),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "ADIADO", "dataAdiamento": FUTURA},
     {**ROW, "tipoMensagem": "PRIMEIRA_CONFIRMACAO"}),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "XPTO"}, ROW),
    ({"id": 7, "acao": "REGISTRAR"}, ROW),
    ({"id": 7, "acao": "APAGAR"}, ROW),
    ({"id": 9, "acao": "RESPONDER", "texto": "x"}, {}),
    ({"id": 7, "acao": "RESPONDER", "texto": "x"}, {**ROW, "status": "CONCLUIDO"}),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"}, {**ROW, "status": "TRANSFERIDO"}),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "NAO_CONCORDA"},
     {**ROW, "status": "PENDENTE_RESPOSTA_TARDIA",
      "dadosPedido": json.dumps({**DP, "registroContato": {"origem": "IA"}, "respostaTardia": {"pedidoLiderRegistro": "97681"}})}),
    ({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"},
     {**ROW, "status": "CONCLUIDO", "chatConsultor": json.dumps([{"role": "consultor", "tipo": "resultado", "texto": "x"}])}),
    ({"id": 7, "acao": "RESPONDER", "texto": "ok"}, {**ROW, "chatConsultor": "lixo", "dadosPedido": ""}),
]


@pytest.mark.parametrize("body,row", CASOS)
def test_processar_acao(body, row):
    js = rodar_js("Processar ação do consultor", [row], {WH: [{"body": body}]})
    igual(_sem_ts(js), _sem_ts([K.processar_acao(body, row)]))


def _proc(body, row):
    return K.processar_acao(body, row)


GRUPO = {**DP, "pedidosGrupo": [
    {"pedidoLider": "97681", "Pedido": "11-97681", "clienteLider": "JOSÉ", "tipoMensagem": "DATA_ENTREGA",
     "entregas": [{"data": "10/03/2027"}, {"data": "01/03/2027"}]},
    {"pedidoLider": "97680", "clienteLider": "JOSÉ", "tipoMensagem": "PRIMEIRA_CONFIRMACAO", "entregas": [],
     "dataSistema": "01/12/2040"}]}


@pytest.mark.parametrize("r", [
    _proc({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"}, ROW),
    _proc({"id": 7, "acao": "REGISTRAR", "resultado": "ADIADO", "dataAdiamento": FUTURA}, ROW),
    _proc({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"}, {**ROW, "dadosPedido": json.dumps({"Cliente": "ÁGUA"})}),
    _proc({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"},
          {**ROW, "tipoMensagem": "PRIMEIRA_CONFIRMACAO", "mensagem": "sem data", "dadosPedido": json.dumps({"dataSistema": "01/12/2040"})}),
    _proc({"id": 7, "acao": "REGISTRAR", "resultado": "NAO_CONCORDA"}, {**ROW, "dadosPedido": json.dumps(GRUPO)}),
])
def test_preparar_resultado(r):
    js = rodar_js("Preparar resultado (consultor)", [r], {"Processar ação do consultor": [r]})
    igual(js, K.preparar_resultado(r))


FORM = """<form><input type="checkbox" name="item[]" value="101 &amp; A"><input name='item[]' value='202'>
<input name=item[] value=101&amp;A><input type="hidden" name="outro" value="x"></form>"""


@pytest.mark.parametrize("html", [FORM, "<html><body>Sessão expirada</body></html>", None])
def test_montar_url(html):
    p = {"pedidoLider": "97680", "dataPrevistaBR": "27/02/2027", "dataAdiamentoBR": "24/05/2027", "dataAdiamentoISO": "2027-05-24"}
    js = rodar_js("Montar URL (consultor)", [{"data": html} if html is not None else {}],
                  {"Itens do registro (consultor)": [p]})
    igual(js, [K.montar_url_consultor(html, p)])


def _itens(res, **kw):
    base = {"id": 7, "pedidoLider": "97680", "pedidoSheet": "11-97680", "clienteIntranet": "MATEUS", "resultado": res,
            "datasInformadas": "27/02/2027", "dataPrevistaBR": "27/02/2027", "dataPrevistaISO": "2027-02-27",
            "dataAdiamentoBR": "24/05/2027" if res == "ADIADO" else None,
            "dataAdiamentoISO": "2027-05-24" if res == "ADIADO" else "", "primeiraConfirmacao": False, "pularIntranet": False}
    return {**base, **kw}


@pytest.mark.parametrize("lista,entradas,urls", [
    ([_itens("CONFIRMADO")], None, None),
    ([_itens("NAO_CONCORDA"), _itens("NAO_CONCORDA", pedidoLider="97681", dataPrevistaISO="")], None, None),
    ([_itens("CONFIRMADO", primeiraConfirmacao=True)], None, None),
    ([_itens("CONFIRMADO", pularIntranet=True)], None, None),
    ([_itens("ADIADO")], [{"data": "ok"}], [{"urlAlterar": "http://x"}]),
    ([_itens("ADIADO")], [{"error": {"message": "timeout"}}], [{"urlAlterar": "http://x"}]),
    ([_itens("ADIADO")], [{"error": "URL"}], [{"urlAlterar": None, "erroAdiamento": "Itens do formulário não encontrados."}]),
    ([_itens("ADIADO", dataPrevistaBR=None)], [{"data": "ok"}], [{"urlAlterar": "http://x"}]),
])
def test_montar_observacao(lista, entradas, urls):
    nodes = {"Itens do registro (consultor)": lista}
    if urls is not None:
        nodes["Montar URL (consultor)"] = urls
    entradas_js = entradas if entradas is not None else lista
    js = rodar_js("Montar observação (consultor)", entradas_js, nodes)
    py = K.montar_observacao(lista, entradas if entradas is not None else [], urls or [])
    igual(js, py, ignorar=("sheetI",))


def test_localizar_linha():
    regs = [_itens("CONFIRMADO"), _itens("CONFIRMADO", pedidoLider="5", pedidoSheet="11-0005"),
            _itens("CONFIRMADO", pedidoLider="999", pedidoSheet="11-999")]
    linhas = [{"row_number": 2, "Pedido": "12-97680"}, {"row_number": 3, "Pedido": "11-97680"},
              {"row_number": 4, "Pedido": "11-5"}, {"Pedido": "11-999"}]
    js = rodar_js("Localizar linha (consultor)", linhas, {"Montar observação (consultor)": regs})
    igual(js, K.localizar_linha(regs, linhas))


@pytest.mark.parametrize("cenario", ["um", "varios", "adiado_falhou", "tardia", "concluido", "com_resposta"])
def test_resumo_registro(cenario):
    proc = K.processar_acao({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"}, ROW)
    mr = None
    regs = [{**_itens("CONFIRMADO", row_number=3, temObservacao=True, alteracaoOk=None, statusAnterior="AGUARDANDO_CONSULTOR",
                      vigiaAteAnterior="")}]
    gravs, obs = [{"CONFIRMADO": "SIM"}], [{"data": "ok"}]
    if cenario == "varios":
        regs = [{**regs[0], "pedidoPrincipal": "97680"},
                {**regs[0], "pedidoLider": "97681", "row_number": None, "temObservacao": False, "pedidoPrincipal": "97680"}]
    if cenario == "adiado_falhou":
        regs = [{**_itens("ADIADO", row_number=3, temObservacao=True, alteracaoOk=False, erroAdiamento="timeout",
                          statusAnterior="AGUARDANDO_CONSULTOR", vigiaAteAnterior="")}]
        gravs, obs = [{"error": "x"}], [{"error": "y"}]
    if cenario == "tardia":
        proc = K.processar_acao({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"}, {**ROW, "status": "PENDENTE_RESPOSTA_TARDIA"})
        regs = [{**regs[0], "statusAnterior": "PENDENTE_RESPOSTA_TARDIA"}]
    if cenario == "concluido":
        proc = K.processar_acao({"id": 7, "acao": "REGISTRAR", "resultado": "CONFIRMADO"},
                                {**ROW, "status": "CONCLUIDO", "dadosPedido": json.dumps({**DP, "registroContato": {"a": 1}})})
        regs = [{**regs[0], "statusAnterior": "CONCLUIDO", "vigiaAteAnterior": "2026-11-16T10:00:00.000-03:00", "pularIntranet": True,
                 "temObservacao": False}]
        obs = []
    nodes = {"Localizar linha (consultor)": regs, "Gravar resultado na planilha (consultor)": gravs,
             "Observação Intranet (consultor)": obs, "Processar ação do consultor": [proc]}
    if cenario == "com_resposta":
        proc = K.processar_acao({"id": 7, "acao": "RESPONDER", "texto": "ok", "resultado": "CONFIRMADO"}, ROW)
        mr = K.montar_resposta_cliente(proc, {"text": "Olá!"})
        nodes.update({"Processar ação do consultor": [proc], "Montar resposta ao cliente": [mr]})
    if not gravs:
        nodes.pop("Gravar resultado na planilha (consultor)")
    js = rodar_js("Resumo do registro (consultor)", [{}], nodes)
    py = K.resumo_registro(regs, gravs, obs, proc, mr)
    ign = ("vigiaAte",) if regs[0]["statusAnterior"] == "AGUARDANDO_CONSULTOR" else ()
    igual(_sem_ts(js), _sem_ts([py]), ignorar=ign)
    if not ign:
        assert py["vigiaAte"] == js[0]["vigiaAte"]


@pytest.mark.parametrize("out", [{"text": '"Olá! Sim, a montagem é na entrega."'}, {"text": "  "}, {"error": "x"}, {"output": "“Oi”"}])
def test_montar_resposta(out):
    base = K.processar_acao({"id": 7, "acao": "RESPONDER", "texto": "Sim"}, ROW)
    js = rodar_js("Montar resposta ao cliente", [out], {"Processar ação do consultor": [base]})
    igual(_sem_ts(js), _sem_ts([K.montar_resposta_cliente(base, out)]))


def test_aprendizado():
    base = [{"id": 1, "pergunta": "Monta?", "resposta": "Sim"}, {"id": 2, "pergunta": "", "resposta": "x"}]
    proc = K.processar_acao({"id": 7, "acao": "RESPONDER", "texto": "Sim"}, ROW)
    mr = K.montar_resposta_cliente(proc, {"text": "Sim!"})
    js = rodar_js("Preparar aprendizado", base, {"Montar resposta ao cliente": [mr]})
    py = K.preparar_aprendizado(mr, base)
    igual(js, [py] if py else [])
    # chat com a dúvida depois do último envio
    mr2 = {**mr, "chatConsultor": json.dumps([{"role": "ia", "tipo": "envio", "texto": "a"}, {"role": "cliente", "texto": "e o frete?"},
                                              {"role": "cliente", "texto": "é grátis?"}])}
    js = rodar_js("Preparar aprendizado", base, {"Montar resposta ao cliente": [mr2]})
    igual(js, [K.preparar_aprendizado(mr2, base)])
    for txt in ['{"generalizavel": true, "pergunta": "Frete?", "resposta": "Grátis", "idExistente": 1}',
                '```json\n{"generalizavel": true, "pergunta": "P", "resposta": "R", "idExistente": 99}```',
                '{"generalizavel": false}', "não é json"]:
        out = {"text": txt}
        js = rodar_js("Interpretar aprendizado", [out], {"Ler base (aprendizado)": base})
        py = K.interpretar_aprendizado(out, base)
        igual(js, [py] if py else [])
