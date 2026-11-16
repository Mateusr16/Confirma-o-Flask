import os, tempfile, importlib

os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["MODO_TESTE"] = "true"

from app import create_app, db, saida  # noqa: E402


def test_rotas_e_saude():
    c = create_app().test_client()
    r = c.get("/api/saude").get_json()
    assert r["modo_teste"] is True
    assert "central-lider" in r["gatilhos_migrados"]
    assert r["gatilhos_pendentes"] == []          # os 9 webhooks da v28 estão migrados


def test_consultor_invalido_responde_erro_e_registra():
    c = create_app().test_client()
    r = c.post("/webhook/central-lider-consultor", json={"pedido": "97680"})
    assert r.status_code == 200 and r.get_json() == {"ok": False, "erro": "Consulta não encontrada."}
    ex = db.consultar("SELECT * FROM execucoes WHERE gatilho='central-lider-consultor'")
    assert ex and ex[-1]["status"] == "ok"


def test_todos_os_agendamentos_migrados():
    from app.agendador import AGENDA
    from app.fluxos import JOBS
    assert set(AGENDA) <= set(JOBS) and "ao_iniciar" in JOBS


def test_digisac_responde_na_hora():
    c = create_app().test_client()
    r = c.post("/webhook/digisac-resposta", json={"event": "message.created"})
    assert r.status_code == 200 and r.get_json() == {"recebido": True}


def test_modo_teste_nao_envia():
    chamado = []
    out = saida.externo("digisac", "enviar_template", {"a": 1}, lambda: chamado.append(1), "fake")
    assert out == "fake" and not chamado
    assert db.consultar("SELECT * FROM envios_simulados")
