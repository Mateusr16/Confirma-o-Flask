"""Consultor, Recomeçar e os agendamentos rodando de ponta a ponta (MODO_TESTE, integrações simuladas)."""
import json
import os
import tempfile
from datetime import timedelta

os.environ.setdefault("SQLITE_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ["MODO_TESTE"] = "true"

import pytest  # noqa: E402

from app import comum as C, create_app, db, tabelas as T  # noqa: E402
from app.fluxos import HANDLERS, ag_rotinas as A, consultor as K, recomecar as R  # noqa: E402

FORM = '<form><input name="item[]" value="101"><input name="item[]" value="202"></form>'


class FakeIntranet:
    def __init__(self, *a):
        pass

    def login(self, *a):
        return "PHPSESSID=x"

    def abrir_form_alteracao(self, data, pedido):
        return {"data": FORM}

    def alterar_data(self, url):
        return {"data": "ok"}

    def aviso_entrega(self, *a, **k):
        return {"data": "ok"}


@pytest.fixture
def amb(monkeypatch):
    create_app()
    for t in [*T.TABELAS, "envios_simulados"]:
        db.executar(f"DELETE FROM {t}")
    monkeypatch.setattr(K, "Intranet", FakeIntranet)
    monkeypatch.setattr(K.planilha, "ler_linhas", lambda: [{"row_number": 5, "Pedido": "11-97680"}])
    monkeypatch.setattr(K.gemini, "gerar_texto", lambda p, t=0: {"text": "Olá! A montagem é feita na entrega."})
    monkeypatch.setattr(K, "listar_usuarios_todos", lambda: [{"data": [{"id": "u-joyce", "name": "JOYCE SILVA"}]}])
    monkeypatch.setattr(K, "listar_usuarios_central", lambda: [{"data": [
        {"id": "u-joyce", "name": "JOYCE SILVA", "departments": [{"id": K.DEPARTAMENTO_CENTRAL, "name": "CENTRAL DE RELACIONAMENTO LIDER"}]},
        {"id": "u-joyce-2", "name": "JOYCE SILVA SANTOS", "departments": [{"id": "outro", "name": "VENDAS"}]}]}])
    monkeypatch.setattr(A, "_timer", lambda: None)
    monkeypatch.setattr(A.digisac, "tickets_abertos", lambda c: {"data": []})
    monkeypatch.setattr(R.digisac, "buscar_contatos", lambda n, s: {"data": []})
    yield monkeypatch
    for t in [*T.TABELAS, "envios_simulados"]:
        db.executar(f"DELETE FROM {t}")


def envios():
    return [(r["destino"], r["acao"]) for r in db.consultar("SELECT * FROM envios_simulados ORDER BY id")]


def _pedido(**kw):
    dp = {"pedidoLider": "97680", "clienteLider": "MATEUS", "mensagem": "Olá, Mateus! A previsão é 27/02/2027.",
          "entregas": [{"data": "27/02/2027"}], "Pedido": "11-97680", "phone": "5511999998888", "contactId": "c1",
          "serviceId": R.SERVICES[0], "cpf": "114679806000076"}
    base = {"pedidoLider": "97680", "status": "AGUARDANDO_CONSULTOR", "cliente": "MATEUS", "responsavel": "JOYCE SILVA",
            "contactId": "c1", "phone": "5511999998888", "serviceId": R.SERVICES[0], "tipoMensagem": "DATA_ENTREGA",
            "mensagem": dp["mensagem"], "resumoIA": "Dúvida do cliente",
            "chatConsultor": json.dumps([{"role": "cliente", "texto": "vem montador?", "ts": "2026-11-16T10:00:00Z"}]),
            "dadosPedido": json.dumps(dp)}
    return T.insert("AGUARDANDO_ENTREGA", {**base, **kw})


def _chamar(path, body):
    return HANDLERS[path]({"body": body, "query": {}, "headers": {}}, {})


def test_consultor_responder(amb):
    p = _pedido()
    resp, cod = _chamar("central-lider-consultor", {"id": p["id"], "acao": "RESPONDER", "texto": "Sim, monta na entrega"})
    assert cod == 200 and resp == {"ok": True, "acao": "RESPONDER"}
    l = T.get_um("AGUARDANDO_ENTREGA", {"id": p["id"]})
    assert l["status"] == "CONCLUIDO" and l["vigiaAte"] and "Respondido pelo consultor" in l["resumoIA"]
    assert ("digisac", "enviar_mensagem") in envios()
    # de novo: já tratada
    resp, _ = _chamar("central-lider-consultor", {"id": p["id"], "acao": "RESPONDER", "texto": "x"})
    assert resp == {"ok": False, "erro": "Esta consulta já foi tratada."}


def test_consultor_registrar_adiado(amb):
    p = _pedido()
    futura = (C.agora().date() + timedelta(days=60)).strftime("%Y-%m-%d")
    resp, _ = _chamar("central-lider-consultor", {"id": p["id"], "acao": "REGISTRAR", "resultado": "ADIADO", "dataAdiamento": futura})
    assert resp["ok"] is True and resp["planilha"] == "OK" and resp["intranet"] == "OK" and resp["avisos"] == [], resp
    l = T.get_um("AGUARDANDO_ENTREGA", {"id": p["id"]})
    assert l["status"] == "CONCLUIDO" and l["categoria"] == "PEDE_ADIAR"
    assert json.loads(l["dadosPedido"])["registroContato"]["origem"] == "CONSULTOR"
    assert ("planilha", "atualizar") in envios()


def test_consultor_transferir(amb):
    p = _pedido()
    resp, _ = _chamar("central-lider-consultor", {"id": p["id"], "acao": "TRANSFERIR"})
    assert resp == {"ok": True, "acao": "TRANSFERIR"}
    assert T.get_um("AGUARDANDO_ENTREGA", {"id": p["id"]})["status"] == "TRANSFERIDO"
    assert ("digisac", "transferir_chamado") in envios()


def test_transferir_so_usuario_da_central(amb):
    """19/11: homônimo fora da Central de Relacionamento é ignorado; sem ninguém da Central, vira manual."""
    from app.fluxos import f2_logica as L
    u = lambda i, n, dep, arq=None: {"id": i, "name": n, "archivedAt": arq,  # noqa: E731
                                     "departments": [{"id": dep, "name": "X"}]}
    lista = [{"data": [u("p1", "Pedro Leopoldino - Consultor", K.DEPARTAMENTO_CENTRAL),
                       u("p2", "Pedro Henrique", "vendas")]}]
    m = L.mapear_responsavel_transferencia({"responsavel": "PEDRO"}, lista, K.DEPARTAMENTO_CENTRAL)
    assert m["statusMapeamento"] == "OK" and m["userIdResponsavel"] == "p1"
    pelo_nome = [{"data": [{"id": "p3", "name": "Pedro Leopoldino", "departments": [{"id": "z", "name": "Central de Relacionamento Líder"}]}]}]
    assert L.mapear_responsavel_transferencia({"responsavel": "PEDRO"}, pelo_nome, K.DEPARTAMENTO_CENTRAL)["userIdResponsavel"] == "p3"
    arquivado = [{"data": [u("p4", "Pedro Leopoldino", K.DEPARTAMENTO_CENTRAL, "2026-01-01")]}]
    assert L.mapear_responsavel_transferencia({"responsavel": "PEDRO"}, arquivado, K.DEPARTAMENTO_CENTRAL)["statusMapeamento"] == "NAO_ENCONTRADO"
    sem_dep = [{"data": [{"id": "p5", "name": "Pedro Leopoldino"}]}]
    assert L.mapear_responsavel_transferencia({"responsavel": "PEDRO"}, sem_dep, K.DEPARTAMENTO_CENTRAL)["statusMapeamento"] == "NAO_ENCONTRADO"


def test_recomecar_novo_numero(amb):
    _pedido(status="DATA_ENVIADA")
    resp, _ = _chamar("central-lider-recomecar", {"pedidoLider": "11-97680", "motivo": "falar com a esposa",
                                                  "novoTelefone": "11987654321", "nomeContato": "Anete",
                                                  "avisoContatoAntigo": "A partir de agora falamos com a Anete."})
    assert resp["ok"] is True, resp
    assert "Aviso enviado ao contato anterior" in resp["mensagem"] and resp["statusContato"] == "CRIADO"
    l = T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "97680"})
    dp = json.loads(l["dadosPedido"])
    assert l["status"] == "PENDENTE_REVISAO" and l["phone"] == "5511987654321" and dp["mensagem"].startswith("Olá, Anete!")
    papeis = {m["papel"] for m in T.get("MENSAGENS_CLIENTE")}
    assert papeis == {"RECOMECO", "BOT"}
    # sem motivo
    resp, _ = _chamar("central-lider-recomecar", {"pedidoLider": "97680", "motivo": ""})
    assert resp["ok"] is False


def test_vigilancia_e_reenvio(amb):
    _pedido(status="CONCLUIDO", vigiaAte=(C.agora() - timedelta(minutes=5)).isoformat())
    _pedido(pedidoLider="2", status="AGUARDANDO", enviadoEm=(C.agora() - timedelta(hours=2)).isoformat(), contactId="c2",
            template="conf002")
    r = A.varredura_vigilancia()
    assert r["FECHAR"] == 1 and ("digisac", "fechar_chamado") in envios()
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "97680"})["vigiaAte"] == ""
    r = A.reenvio_template()
    assert r == {"contatos": 1, "reenviados": 1}
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "2"})["template"] == "conf002_reenvio"
    assert A.reenvio_template() == {"contatos": 0, "reenviados": 0}


def test_lembrete(amb):
    amb.setattr(A.digisac, "tickets_abertos", lambda c: {"data": [{"isOpen": True, "contactId": c, "userId": A.MEUS_USER_IDS[0]}]})
    _pedido(status="DATA_ENVIADA", categoria="", respondidoEm=(C.agora() - timedelta(hours=2)).isoformat())
    r = A.lembrete_13h()
    assert r == {"contatos": 1, "enviados": 1}
    dp = json.loads(T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "97680"})["dadosPedido"])
    assert dp["lembreteConfirmacaoEm"] and "Podemos confirmar a data de entrega do pedido nº *97680*?" in dp["lembreteConfirmacaoTexto"]
    assert A.lembrete_13h() == {"contatos": 0, "enviados": 0}


def test_encerramento_e_varredura_tardia(amb):
    amb.setattr(A.planilha, "ler_linhas", lambda: [{"row_number": 5, "Pedido": "11-97680", "CONFIRMADO": "", "MOTIVO": "",
                                                    "DATA ENVIO CONF.": ""}])
    _pedido(status="AGUARDANDO", enviadoEm=C.agora_iso())
    r = A.encerramento_pendencias()
    assert r == {"encerrados": 1, "chamadosFechados": 1}
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "97680"})["status"] == "SEM_RETORNO_CLIENTE"
    sc = T.get("SEM_CONFIRMACAO_DIARIO")
    assert len(sc) == 1 and sc[0]["status"] == "SEM_RETORNO_TEMPLATE"
    # varredura do dia seguinte: o cliente respondeu depois do encerramento
    ontem = (C.agora().date() - timedelta(days=1)).isoformat()
    T.update("SEM_CONFIRMACAO_DIARIO", {"id": sc[0]["id"]}, {"dataRef": ontem, "registradoEm": f"{ontem}T16:20:00.000-03:00"})
    amb.setattr(A, "_buscar_mensagens", lambda cs: [(0, {"data": [{"id": "mx", "contactId": "c1", "isFromMe": False,
                                                                   "timestamp": f"{ontem}T19:00:00.000Z", "data": {"text": "Ok!"}}]})])
    res = A.varredura_tardia()
    assert res["gravadas"] == 1 and res["cartoes"] == ["97680 (1 msg)"], res
    l = T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "97680"})
    assert l["status"] == "PENDENTE_RESPOSTA_TARDIA" and json.loads(l["dadosPedido"])["respostaTardia"]["respostas"][0]["texto"] == "Ok!"
    assert T.get("SEM_CONFIRMACAO_DIARIO")[0]["status"] == "RESPONDEU_DEPOIS"
    # o consultor registra a resposta tardia pela tela
    resp, _ = _chamar("central-lider-consultor", {"id": l["id"], "acao": "REGISTRAR", "resultado": "CONFIRMADO"})
    assert resp["ok"] is True
    assert T.get("SEM_CONFIRMACAO_DIARIO")[0]["status"] == "RESPOSTA_TARDIA_TRATADA"
