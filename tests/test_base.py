import os, tempfile, importlib

os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["MODO_TESTE"] = "true"

from app import create_app, db, saida  # noqa: E402


def test_rotas_e_saude():
    c = create_app().test_client()
    r = c.get("/api/saude").get_json()
    assert r["modo_teste"] is True
    assert "central-lider" in r["gatilhos_migrados"]
    assert "central-lider-consultor" in r["gatilhos_pendentes"]


def test_nao_migrado_responde_501_e_registra():
    c = create_app().test_client()
    r = c.post("/webhook/central-lider-consultor", json={"pedido": "97680"})
    assert r.status_code == 501
    ex = db.consultar("SELECT * FROM execucoes WHERE gatilho='central-lider-consultor'")
    assert ex and ex[-1]["status"] == "nao_migrado"


def test_digisac_responde_na_hora():
    c = create_app().test_client()
    r = c.post("/webhook/digisac-resposta", json={"event": "message.created"})
    assert r.status_code == 200 and r.get_json() == {"recebido": True}


def test_modo_teste_nao_envia():
    chamado = []
    out = saida.externo("digisac", "enviar_template", {"a": 1}, lambda: chamado.append(1), "fake")
    assert out == "fake" and not chamado
    assert db.consultar("SELECT * FROM envios_simulados")
