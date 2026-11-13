import os, tempfile
os.environ.setdefault("SQLITE_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
from app import create_app, tabelas as T  # noqa: E402

create_app()


def test_upsert_update_get():
    T.upsert("AGUARDANDO_ENTREGA", {"pedidoLider": "97680"}, {"status": "PENDENTE", "cliente": "X"})
    T.upsert("AGUARDANDO_ENTREGA", {"pedidoLider": "97680"}, {"status": "ENVIADO"})
    r = T.get("AGUARDANDO_ENTREGA", {"pedidoLider": "97680"})
    assert len(r) == 1 and r[0]["status"] == "ENVIADO" and r[0]["cliente"] == "X"
    assert T.get("AGUARDANDO_ENTREGA", {"status": ("in", ["ENVIADO", "Z"])})
    assert T.get("AGUARDANDO_ENTREGA", {"contactId": ("isEmpty", None)})


def test_mensagens_ordem_e_delete():
    for i in (3, 1, 2):
        T.insert("MENSAGENS_CLIENTE", {"contactId": "c1", "texto": str(i), "ts": i})
    assert [m["texto"] for m in T.get("MENSAGENS_CLIENTE", {"contactId": "c1"}, ordem="ts")] == ["1", "2", "3"]
    assert T.delete_rows("MENSAGENS_CLIENTE", {"contactId": "c1", "ts": ("lt", 3)}) == 2


def test_coluna_invalida():
    import pytest
    with pytest.raises(ValueError):
        T.get("AGUARDANDO_ENTREGA", {"naoExiste": 1})
