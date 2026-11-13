"""Paridade do Fluxo 2 (resposta do cliente): JS original x Python."""
import json
from datetime import timedelta

import pytest

from app import comum as C
from app.fluxos import f2_logica as L

from .conftest import igual, rodar_js

IGN = ("ts", "messageId", "chamadoVerificadoEm", "em", "detectadoEm")


def d(dias):
    return C.fmt_br(C.agora().date() + timedelta(days=dias))


AGORA = C.agora_ms()


def test_filtrar_mensagem():
    for body in [{"data": {"contactId": "c1", "serviceId": "s", "id": "m1", "data": {"text": " oi "}}},
                 {"data": {"contactId": "c1", "isFromMe": True}}, {"data": {"type": "ticket"}},
                 {"data": {"contactId": "c1", "id": "m2"}}]:
        js = rodar_js("Filtrar Mensagem", [{"body": body}])
        py = L.filtrar_mensagem({"body": body})
        igual(js, [py] if py else [], ignorar=("ts", "messageId") if "id" not in body.get("data", {}) else ("ts",))


@pytest.mark.parametrize("caso", ["simples", "rajada_outra", "rajada_ultima", "duplicada", "recomeco"])
def test_agrupar(caso):
    me = {"contactId": "c1", "messageId": "m3", "ts": AGORA, "text": "dia 15"}
    linhas = [{"contactId": "c1", "papel": "BOT", "texto": "Qual dia de março fica melhor?", "ts": AGORA - 600000, "messageId": "b1"},
              {"contactId": "c1", "papel": "CLIENTE", "texto": "quero março", "ts": AGORA - 700000, "messageId": "m1"},
              {"contactId": "c1", "papel": "CLIENTE", "texto": "Extender*", "ts": AGORA - 60000, "messageId": "m2"},
              {"contactId": "c1", "papel": "CLIENTE", "texto": "dia 15", "ts": AGORA, "messageId": "m3"}]
    if caso == "rajada_outra":
        linhas.append({"contactId": "c1", "papel": "CLIENTE", "texto": "obrigado", "ts": AGORA + 5000, "messageId": "m4"})
    if caso == "duplicada":
        linhas.insert(0, {"contactId": "c1", "papel": "CLIENTE", "texto": "dia 15", "ts": AGORA - 3000, "messageId": "m3"})
    if caso == "recomeco":
        linhas.append({"contactId": "c1", "papel": "RECOMECO", "texto": "x", "ts": AGORA - 650000, "messageId": "r"})
    if caso == "simples":
        linhas = linhas[-1:]
    js = rodar_js("Agrupar mensagens do cliente", linhas, {"Filtrar Mensagem": [me]})
    py = L.agrupar_mensagens(me, linhas)
    igual(js, [py] if py else [])


def test_escolher_linha():
    msg = {"text": "ok", "historico": "Líder: oi"}
    ant = C.agora().replace(microsecond=0) - timedelta(minutes=5)
    cenarios = [
        [{"id": 1, "status": "AGUARDANDO", "enviadoEm": ant.isoformat()}, {"id": 2, "status": "AGUARDANDO", "enviadoEm": ant.isoformat()}],
        [{"id": 1, "status": "AGUARDANDO", "enviadoEm": C.agora().isoformat()}],
        [{"id": 1, "status": "DATA_ENVIADA", "enviadoEm": "2026-11-10"}, {"id": 2, "status": "DATA_ENVIADA", "enviadoEm": "2026-11-12"}],
        [{"id": 1, "status": "AGUARDANDO_CONSULTOR", "respondidoEm": "2026-11-12"}, {"id": 2, "status": "AGUARDANDO_DECISAO_RESPONSAVEL"}],
        [{"id": 1, "status": "CONCLUIDO", "vigiaAte": (C.agora() + timedelta(minutes=30)).isoformat()}],
        [{"id": 1, "status": "CONCLUIDO", "vigiaAte": (C.agora() - timedelta(minutes=30)).isoformat()}],
    ]
    for linhas in cenarios:
        js = rodar_js("Escolher Linha", linhas, {"Agrupar mensagens do cliente": [msg]})
        igual(js, L.escolher_linha(msg, linhas))


def test_preparar_contexto():
    grupo = {"pedidosGrupo": [{"pedidoLider": "1", "entregas": [{"data": d(20)}]}, {"pedidoLider": "2", "entregas": [{"data": d(30)}]}]}
    for j in [{"mensagem": f"previsão *{d(20)}*", "historicoConversa": "Cliente: oi"},
              {"mensagem": "sem data", "dadosPedido": json.dumps(grupo)},
              {"mensagem": f"x {d(20)}", "dadosPedido": json.dumps({"registroContato": {"dataEntrega": d(40), "resultado": "CONFIRMADO"}})}]:
        js = rodar_js("Preparar contexto IA", [j])
        py = L.preparar_contexto(j)
        js[0]["ctxHoje"] = js[0]["ctxHoje"].split(" ")[0]
        py["ctxHoje"] = py["ctxHoje"].split(" ")[0]
        igual(js, [py])


@pytest.mark.parametrize("texto", ["sim, pode", "não precisa", "pode sim, não tenho problema", "talvez", "ok obrigado", "n"])
def test_decisao_responsavel(texto):
    j = {"textoCliente": texto, "id": 1}
    igual(rodar_js("Interpretar Decisão Responsável", [j]), [L.interpretar_decisao_responsavel(j)])


PREV = 30  # prevista daqui a 30 dias


def _linha(**extra):
    base = {"id": 9, "pedidoLider": "97680", "mensagem": f"A previsão é *{d(PREV)}*.", "status": "DATA_ENVIADA",
            "historicoConversa": "", "textoCliente": "x", "dadosPedido": "{}", "categoria": ""}
    base.update(extra)
    return base


def _mes(dias):
    dt = C.agora().date() + timedelta(days=dias)
    return f"{dt.month:02d}/{dt.year}"


CASOS_NORMALIZAR = [
    ({"categoria": "ACEITA", "confianca": 0.9}, {}),
    ({"categoria": "ACEITA", "confianca": 0.3}, {}),
    ({"categoria": "ACEITA", "confianca": None}, {}),
    ({"categoria": "ACEITA"}, {}),
    ({"categoria": "lixo", "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "dataSolicitada": d(PREV + 10), "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "dataSolicitada": d(PREV), "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "dataSolicitada": d(PREV - 5), "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "dataSolicitada": d(PREV + 200), "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "mesSolicitado": _mes(PREV + 60), "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "mesSolicitado": _mes(PREV + 400), "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "mesSolicitado": _mes(PREV - 40), "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "confianca": 0.9}, {}),
    ({"categoria": "PEDE_ADIAR", "confianca": 0.9}, {"historicoConversa": "Líder: Para qual data você gostaria? qual data\nCliente: hm"}),
    ({"categoria": "PEDE_ADIAR", "confianca": 0.9}, {"historicoConversa": "Líder: qual data?\nLíder: preciso do dia exato\nCliente: x"}),
    ({"categoria": "DUVIDA_ADIAMENTO", "confianca": 0.9}, {}),
    ({"categoria": "DUVIDA_ADIAMENTO", "confianca": 0.9}, {"historicoConversa": "Líder: armazenamento 30 dias"}),
    ({"categoria": "NAO_ACEITA", "confianca": 0.8}, {}),
    ({"categoria": "OUTRO", "confianca": 0.8}, {}),
    ({"categoria": "ACEITA", "confianca": 0.9, "foraDaRegra": True, "assuntoFora": "faltou item"}, {}),
    ({"categoria": "ACEITA", "confianca": 0.9, "foraDaRegra": "true"}, {"_base": {"usarBase": True, "respostaBase": "Os itens vão separados.", "kbId": 3}}),
    ({"categoria": "OUTRO", "confianca": 0.9, "foraDaRegra": True}, {"_base": {"usarBase": True, "respostaBase": "Resp.", "kbId": 3}, "categoria": "ACEITA"}),
    ({"categoria": "ACEITA", "confianca": 0.9}, {"dadosPedido": json.dumps({"registroContato": {"dataEntrega": d(PREV), "resultado": "CONFIRMADO"}}), "categoria": "ACEITA"}),
    ({"categoria": "PEDE_ADIAR", "dataSolicitada": d(PREV + 10), "confianca": 0.9}, {"dadosPedido": json.dumps({"registroContato": {"dataEntrega": d(PREV)}})}),
    ({"categoria": "PEDE_ADIAR", "dataSolicitada": d(PREV + 15), "confianca": 0.9},
     {"mensagem": "x", "dadosPedido": json.dumps({"pedidosGrupo": [{"pedidoLider": "1", "entregas": [{"data": d(PREV)}]},
                                                                   {"pedidoLider": "2", "entregas": [{"data": d(PREV + 20)}]}]})}),
    ({"categoria": "PEDE_ADIAR", "dataSolicitada": d(PREV + 40), "confianca": 0.9},
     {"mensagem": "x", "dadosPedido": json.dumps({"pedidosGrupo": [{"pedidoLider": "1", "entregas": [{"data": d(PREV)}]},
                                                                   {"pedidoLider": "2", "entregas": [{"data": d(PREV + 20)}]}]})}),
    ({"categoria": "PEDE_ADIAR", "dataSolicitada": d(10), "confianca": 0.9}, {"mensagem": "sem data"}),
]


@pytest.mark.parametrize("out,extra", CASOS_NORMALIZAR)
def test_normalizar_categoria(out, extra):
    extra = dict(extra)
    base = extra.pop("_base", None)
    linha = _linha(**extra)
    nodes = {"Escolher Linha": [linha], "Basic LLM Chain": [{"output": out}]}
    if base is not None:
        nodes["Interpretar resposta da base (1ª resposta)"] = [base]
    js = rodar_js("Normalizar Categoria", [{}], nodes)
    igual(js, [L.normalizar_categoria(linha, out, base)])


def test_anti_repeticao():
    agora = C.agora_ms()
    tab = [{"contactId": "c1", "papel": "CLIENTE", "texto": "oi", "ts": agora - 50000, "messageId": "1"},
           {"contactId": "c1", "papel": "BOT", "texto": "*Perfeito*, obrigado", "ts": agora - 100000, "messageId": "2"},
           {"contactId": "c2", "papel": "CLIENTE", "texto": "oi", "ts": agora - 90000, "messageId": "3"},
           {"contactId": "c2", "papel": "BOT", "texto": "resposta", "ts": agora - 10000, "messageId": "4"},
           {"contactId": "c3", "papel": "CLIENTE", "texto": "x", "ts": agora - 10000, "messageId": "5"}]
    originais = [{"contactId": "c1", "respostaFixa": "Perfeito, obrigado"}, {"contactId": "c2", "respostaFixa": "nova"},
                 {"contactId": "c3", "respostaFixa": "outra"}]
    js = rodar_js("Anti-repetição: pode enviar? (resposta fixa)", tab, {"Anti-repetição (resposta fixa)": originais})
    igual(js, L.anti_repeticao(originais, tab, lambda j: j.get("respostaFixa")))


def test_sheet_registro_observacao():
    grupo = {"Pedido": "11-1", "pedidosGrupo": [{"pedidoLider": "1", "Pedido": "11-1", "entregas": [{"data": d(20)}], "tipoMensagem": "UNICA"},
                                                {"pedidoLider": "2", "entregas": [{"data": d(25)}], "tipoMensagem": "PARCIAL"}]}
    for cat, dp, extra in [("ACEITA", {"Pedido": "11-0097680", "entregas": [{"data": d(20)}]}, {}),
                           ("NAO_ACEITA", {}, {"dataPrevistaOriginal": d(20)}),
                           ("PEDE_ADIAR", {}, {"adiamentoValido": True, "dataSolicitada": d(40), "dataPrevistaOriginal": d(20)}),
                           ("ACEITA", {"registroContato": {"em": "x"}}, {}),
                           ("ACEITA", grupo, {}),
                           ("ACEITA_PEDE_ADIANTAR", {"tipoMensagem": "PRIMEIRA_CONFIRMACAO", "dataSistema": "01/12/2040"}, {}),
                           ("OUTRO", {}, {})]:
        n = {"id": 5, "pedidoLider": "97680", "categoria": cat, "dadosPedido": json.dumps(dp), "cliente": "JOSÉ",
             "pedidosGrupo": ["97680"], **extra}
        js = rodar_js("Classificar Resposta Sheet", [{}], {"Normalizar Categoria": [n]})
        py = L.classificar_resposta_sheet(n)
        igual(js, py, ignorar=("sheetI",))
        rows = [{"row_number": 2, "Pedido": "11-97680"}, {"row_number": 3, "Pedido": "11-1"}, {"row_number": 4, "Pedido": "11-2"}]
        if any(c["deveAtualizar"] for c in py):
            loc_js = rodar_js("Localizar Linha Sheet", rows, {"Classificar Resposta Sheet": py})
            loc = L.localizar_linhas_sheet(py, rows)
            igual(loc_js, loc)
            igual(rodar_js("Montar Observação Contato", loc, {"Normalizar Categoria": [n], "Localizar Linha Sheet": loc}),
                  L.montar_observacoes_contato(n, loc))
            reg = rodar_js("Montar registro único", [py[0]], {"Normalizar Categoria": [n]})
            pr = L.montar_registro_unico(n, py[0])
            if reg:
                reg[0]["dadosPedido"] = json.loads(reg[0]["dadosPedido"])
                pr["dadosPedido"] = json.loads(pr["dadosPedido"])
            igual(reg, [pr] if pr else [], ignorar=("em",))


def test_chats_consultor():
    for tipo in ["ALTERAR_REGISTRO", "FORA_DA_REGRA", "OUTRO"]:
        n = {"id": 1, "pedidoLider": "97680", "cliente": "ANA", "contactId": "c1", "textoCliente": "oi", "tipoResposta": tipo, "resumoIA": "quer x",
             "assuntoFora": "faltou item", "pedidosGrupo": ["97680"], "chatConsultor": "[]",
             "registroAnterior": {"resultado": "CONFIRMADO", "dataEntrega": "10/12/2026"} if tipo != "OUTRO" else None}
        js = rodar_js("Montar chat com consultor", [{}], {"Normalizar Categoria": [n]})
        py = L.montar_chat_consultor(n)
        js[0]["chatConsultor"] = json.loads(js[0]["chatConsultor"])
        py["chatConsultor"] = json.loads(py["chatConsultor"])
        igual(js, [py], ignorar=("ts",))
    v = {"id": 1, "pedidoLider": "1", "cliente": "ANA", "contactId": "c1", "textoCliente": "horário?", "vigResumo": "quer horário"}
    js = rodar_js("Montar dúvida ao consultor (vigilância)", [{}], {"Interpretar classificação (vigilância)": [v]})
    py = L.montar_duvida_vigilancia(v)
    js[0]["chatConsultor"] = json.loads(js[0]["chatConsultor"])
    py["chatConsultor"] = json.loads(py["chatConsultor"])
    igual(js, [py], ignorar=("ts",))


def test_adiamento_confirmar():
    grupo = [{"pedidoLider": "1", "entregas": [{"data": d(25)}, {"data": d(20)}]}, {"pedidoLider": "2", "entregas": []}]
    n = {"pedidoLider": "1", "dataSolicitada": d(50), "dataPrevistaOriginal": d(20), "textoCliente": "adiar", "grupoPedidos": grupo}
    js = rodar_js("Expandir adiamento (grupo)", [n])
    py = L.expandir_adiamento(n)
    igual(js, py)
    montar = [{"urlAlterar": "u1", "pedidoLider": "1"}, {"urlAlterar": None, "pedidoLider": "2", "erroAdiamento": "sem itens"}]
    resps = [{"data": "<b>ok</b>"}, {"data": ""}]
    js = rodar_js("Confirmar Alteração Intranet", resps, {"Normalizar Categoria": [n], "Montar URL Adiamento": montar, "Expandir adiamento (grupo)": py})
    igual(js, [L.confirmar_alteracao(n, list(zip(montar, py, resps)))])


def test_classificacao_vigilancia_e_base():
    linha = {"id": 1, "textoCliente": "oi"}
    for txt in ['```json\n{"tipo":"regra","resumo":"adiar"}\n```', "lixo", '{"tipo":"SEM_ACAO"}']:
        js = rodar_js("Interpretar classificação (vigilância)", [{"text": txt}], {"Escolher Linha": [linha]})
        igual(js, [L.interpretar_classificacao_vigilancia(linha, {"text": txt})])
    base = [{"id": 3, "pergunta": "monta?", "resposta": "sim", "usos": 2}]
    j = {"textoCliente": "x", "assuntoFora": "montagem"}
    for txt in ['{"encontrou": true, "id": 3, "resposta": "Montamos sim"}', '{"encontrou": true, "id": 9, "resposta": "x"}', "nada"]:
        js = rodar_js("Interpretar resposta da base (1ª resposta)", [{"text": txt}],
                      {"Montar consulta à base (1ª resposta)": [j], "Ler base de conhecimento (1ª resposta)": base})
        py = L.interpretar_resposta_base({"text": txt}, base)
        igual(js, [{"assuntoFora": "montagem", "usarBase": py["usarBase"], "kbId": py["kbId"], "kbUsos": py["kbUsos"],
                    "respostaBase": py["respostaBase"] if py["usarBase"] else ""}])
