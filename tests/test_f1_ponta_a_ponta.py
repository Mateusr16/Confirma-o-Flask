"""Disparo completo do Fluxo 1 com intranet, planilha, DigiSac e rotas simulados."""
import os
import tempfile
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("SQLITE_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ["MODO_TESTE"] = "true"

import pytest  # noqa: E402

from app import comum as C, create_app, db, tabelas as T  # noqa: E402
from app.fluxos import f1_disparo  # noqa: E402

FIX = Path(__file__).parent / "paridade" / "fixtures"


def _lojas(pedido, entrega, uf="MG", cidade="NOVA LIMA", fone="31999998888", ref="LUCIANA CALISTO ( M.LEME)"):
    return (f"<html><b>ENTREGA</b>: RUA X, 10 - CENTRO, {cidade} - {uf}.<br>"
            f"PEDIDO: {pedido} / 0 01/10/2026 ENTREGA: {entrega} Sit.: N MARIA DA SILVA 012345678901234 "
            f"{fone} {ref} NATUREZA OPERACAO</html>")


class FakeIntranet:
    base = "http://intranet"

    def __init__(self):
        futuro = C.fmt_br(C.agora().date() + timedelta(days=30))
        passado = C.fmt_br(C.agora().date() - timedelta(days=5))
        self.paginas = {
            "1001": _lojas("1001", futuro),
            "1002": _lojas("1002", passado),                     # entrega já passou
            "1003": "<html>PEDIDO: 1003 CANCELADO</html>",       # cancelado
            "1004": _lojas("1004", futuro, uf="GO"),             # UF sem depósito -> pendência
        }
        self.futuro = futuro

    def login(self, *a):
        return "PHPSESSID=x"

    def pedido_lojas(self, p):
        return self.paginas.get(p, "<html></html>")

    def situacao_pedidos(self, p):
        return {"data": (f'<html>Saldo de pedidos entre os dias<table><tr><td>(11)-{p}</td><td>x</td><td>N</td>'
                         f'<td>{self.futuro}</td><td>y</td><td>1MESA0001</td><td>MESA JANTAR - TAMPO</td><td>1,00</td></tr></table></html>')}

    def conferir_boletos(self, d):
        return {"data": "<html>" + "x" * 60 + "</html>"}

    def lista_emails(self):
        return {"data": ""}

    def projetos_postados(self):
        return {"data": ""}

    def aviso_entrega(self, *a, **k):
        return {"data": "ok"}


@pytest.fixture
def ambiente(monkeypatch):
    create_app()
    for t in T.TABELAS:
        db.executar(f"DELETE FROM {t}")
    linhas = [{"row_number": i + 2, "Pedido": f"11-{n}", "Cliente": "MARIA", "RESPONSÁVEL": "DANIELA",
               "MOTIVO": "", "CONFIRMADO": ""} for i, n in enumerate(["1001", "1002", "1003", "1004"])]
    monkeypatch.setattr(f1_disparo.planilha, "ler_linhas", lambda: linhas)
    monkeypatch.setattr(f1_disparo, "Intranet", FakeIntranet)
    monkeypatch.setattr(f1_disparo.digisac, "buscar_contatos",
                        lambda n, s: {"data": [{"id": "contato-1", "serviceId": s, "data": {"number": "5531999998888"}}]})
    monkeypatch.setattr(f1_disparo.rotas_geo, "geocodificar", lambda c, u: {"data": '[{"lat": "-20.1", "lon": "-44.4"}]'})
    monkeypatch.setattr(f1_disparo.rotas_geo, "rota", lambda o, d: {"code": "Ok", "routes": [{"distance": 30000}]})


def test_disparo_completo(ambiente):
    f1_disparo.rodar_disparo("teste-1")
    st = {r["pedidoLider"]: r["status"] for r in T.get("AGUARDANDO_ENTREGA")}
    assert st == {"1001": "PENDENTE_REVISAO", "1002": "PEDIDO_ENTREGUE", "1003": "PEDIDO_CANCELADO",
                  "1004": "PENDENTE_DESTINO"}, st
    msg = C.loads(T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})["dadosPedido"])["mensagem"]
    assert "Olá, Maria! Aqui é da *Líder*." in msg and "MESA JANTAR" in msg
    ev = [r["msg"] for r in T.get("FLUXO_STATUS", {"disparoId": "teste-1"}, ordem="ts")]
    assert ev[0] == "Coletando dados da planilha" and "Registrando envios" in ev
    assert not T.get("FLUXO_STATUS", {"tipo": "erro"})
    simulados = {(r["destino"], r["acao"]) for r in db.consultar("SELECT destino, acao FROM envios_simulados")}
    assert ("planilha", "atualizar") in simulados and ("email", "enviar") in simulados


def test_tela_de_login_para_tudo(ambiente, monkeypatch):
    monkeypatch.setattr(FakeIntranet, "pedido_lojas", lambda self, p: '<input name="usuario"><input name="senha">')
    f1_disparo.rodar_disparo("teste-2")
    erros = T.get("FLUXO_STATUS", {"tipo": "erro"})
    assert erros and "Sessão da intranet inválida" in erros[0]["msg"]
    assert all(r["status"] == "EM_PROCESSAMENTO" for r in T.get("AGUARDANDO_ENTREGA"))


def test_resolver_pendencia_libera_pedido(ambiente, monkeypatch):
    from app.fluxos import f1_resolver
    f1_disparo.rodar_disparo("teste-3")
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1004"})["status"] == "PENDENTE_DESTINO"
    f1_resolver.rodar_resolver({"pedidoLider": "1004", "cidade": "Goiânia", "uf": "GO", "referencia": "ANA (SION)"})
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1004"})["status"] == "PENDENTE_REVISAO"
    f1_resolver.rodar_resolver({"pedidoLider": "1001", "cidade": "x", "uf": "MG"})  # não está pendente: ignora
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})["status"] == "PENDENTE_REVISAO"


def test_revisao_enviar_e_cancelar(ambiente, monkeypatch):
    from app.fluxos import f1_revisao
    monkeypatch.setattr(f1_revisao.time, "sleep", lambda s: None)
    monkeypatch.setattr(f1_revisao, "listar_usuarios_todos", lambda: [{"data": []}])
    monkeypatch.setattr(f1_revisao.digisac, "tickets_abertos", lambda c: {"data": []})
    f1_disparo.rodar_disparo("teste-4")
    c = create_app().test_client()
    r = c.post("/webhook/central-lider-revisao", json={"pedidoLider": "1001", "decisao": "enviar", "mensagemEditada": "Texto novo"})
    assert r.status_code == 200 and r.get_json()["resultado"] == "AGUARDANDO"
    linha = T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})
    assert linha["status"] == "AGUARDANDO" and linha["mensagem"] == "Texto novo" and linha["template"] == "conf002"
    acoes = [r["acao"] for r in db.consultar("SELECT acao FROM envios_simulados")]
    assert "enviar_template" in acoes and "transferir_chamado" in acoes
    # chamado ocupado -> AGUARDANDO_CHAMADO_LIVRE
    db.executar("UPDATE AGUARDANDO_ENTREGA SET status='PENDENTE_REVISAO' WHERE pedidoLider='1001'")
    monkeypatch.setattr(f1_revisao.digisac, "tickets_abertos",
                        lambda c: {"data": [{"isOpen": True, "contactId": c, "userId": "outro", "id": "t"}]})
    r = c.post("/webhook/central-lider-revisao", json={"pedidoLider": "1001", "decisao": "enviar"})
    assert r.get_json()["resultado"] == "AGUARDANDO_CHAMADO_LIVRE"
    db.executar("UPDATE AGUARDANDO_ENTREGA SET status='PENDENTE_REVISAO' WHERE pedidoLider='1001'")
    c.post("/webhook/central-lider-revisao", json={"pedidoLider": "1001", "decisao": "cancelar"})
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})["status"] == "CANCELADO"


def test_chamado_ocupado_retomada(ambiente, monkeypatch):
    from app.fluxos import f1_revisao, ag_chamados_ocupados as O
    for m in (f1_revisao, O):
        monkeypatch.setattr(m.time, "sleep", lambda s: None)
        monkeypatch.setattr(m, "listar_usuarios_todos", lambda: [{"data": []}])
    ocupado = lambda c: {"data": [{"isOpen": True, "contactId": c, "userId": "outro", "id": "t"}]}  # noqa: E731
    monkeypatch.setattr(f1_revisao.digisac, "tickets_abertos", ocupado)
    f1_disparo.rodar_disparo("teste-5")
    c = create_app().test_client()
    c.post("/webhook/central-lider-revisao", json={"pedidoLider": "1001", "decisao": "enviar"})
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})["status"] == "AGUARDANDO_CHAMADO_LIVRE"
    r = c.post("/api/rodar/chamados_ocupados?forcar=1").get_json()          # continua ocupado
    assert r["resultado"] == {"verificados": 1, "enviados": 0}
    dp = C.loads(T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})["dadosPedido"])
    assert dp["chamadoEspera"]["verificacoes"] == 2
    monkeypatch.setattr(O.digisac, "tickets_abertos", lambda c: {"data": []})   # liberou
    r = c.post("/api/rodar/chamados_ocupados?forcar=1").get_json()
    assert r["resultado"]["enviados"] == 1
    assert T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})["status"] == "AGUARDANDO"


def test_ciclo_completo_resposta_do_cliente(ambiente, monkeypatch):
    """disparo -> enviar template -> cliente aceita o template -> mensagem -> cliente confirma a data."""
    from app.fluxos import f1_revisao, f2_resposta
    monkeypatch.setattr(f1_revisao.time, "sleep", lambda s: None)
    monkeypatch.setattr(f1_revisao, "listar_usuarios_todos", lambda: [{"data": []}])
    monkeypatch.setattr(f1_revisao.digisac, "tickets_abertos", lambda c: {"data": []})
    monkeypatch.setattr(f2_resposta, "Intranet", FakeIntranet)
    avisos = []
    monkeypatch.setattr(FakeIntranet, "aviso_entrega", lambda self, *a, **k: avisos.append(a) or {"data": "ok"})
    linhas_planilha = [{"row_number": 2, "Pedido": "11-1001"}]
    f1_disparo.rodar_disparo("teste-6")
    monkeypatch.setattr(f2_resposta.planilha, "ler_linhas", lambda: linhas_planilha)
    c = create_app().test_client()
    c.post("/webhook/central-lider-revisao", json={"pedidoLider": "1001", "decisao": "enviar"})
    db.executar("UPDATE AGUARDANDO_ENTREGA SET enviadoEm='2026-01-01T00:00:00' WHERE pedidoLider='1001'")
    # 1) cliente clica no botão do template
    f2_resposta.processar({"body": {"data": {"contactId": "contato-1", "id": "w1", "data": {"text": "Sim"}}}}, esperar=False)
    l = T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})
    assert l["status"] == "DATA_ENVIADA"
    # 2) cliente confirma a data -> IA classifica ACEITA
    monkeypatch.setattr(f2_resposta.gemini, "gerar_json",
                        lambda p, e, t=0: {"output": {"categoria": "ACEITA", "confianca": 0.95, "foraDaRegra": False, "resumo": "confirmou"}})
    f2_resposta.processar({"body": {"data": {"contactId": "contato-1", "id": "w2", "data": {"text": "pode ser, obrigado"}}}}, esperar=False)
    l = T.get_um("AGUARDANDO_ENTREGA", {"pedidoLider": "1001"})
    assert l["status"] == "CONCLUIDO" and l["categoria"] == "ACEITA" and l["vigiaAte"]
    assert C.loads(l["dadosPedido"])["registroContato"]["resultado"] == "CONFIRMADO"
    sim = db.consultar("SELECT destino, acao, payload FROM envios_simulados ORDER BY id")
    textos = [C.loads(r["payload"]).get("text") for r in sim if r["acao"] == "enviar_mensagem"]
    assert any("Produtos do pedido" in (t or "") for t in textos)
    assert "Perfeito, obrigado pela confirmação! Qualquer novidade, avisamos por aqui." in textos
    assert avisos and "CONFIRMOU A DATA DE ENTREGA" in avisos[-1][4]
    planilhas = [C.loads(r["payload"]) for r in sim if r["destino"] == "planilha"]
    assert any(p["busca"] == {"row_number": 2} and p["valores"]["MOTIVO"] == "CONFIRMADO" for p in planilhas)
    # 3) mesma mensagem entregue de novo pelo DigiSac: não responde em dobro
    antes = len(sim)
    f2_resposta.processar({"body": {"data": {"contactId": "contato-1", "id": "w2", "data": {"text": "pode ser, obrigado"}}}}, esperar=False)
    assert len(db.consultar("SELECT id FROM envios_simulados")) == antes


def test_mensagem_de_contato_nao_atendido_nao_e_gravada(ambiente):
    from app.fluxos import f2_resposta
    f2_resposta.processar({"body": {"data": {"contactId": "estranho", "id": "x1", "data": {"text": "oi"}}}}, esperar=False)
    assert T.get("MENSAGENS_CLIENTE", {"contactId": "estranho"}) == []
    T.insert("SEM_CONFIRMACAO_DIARIO", {"pedidoLider": "5", "contactId": "tardio", "dataRef": C.hoje_iso(), "status": "SEM_RETORNO"})
    f2_resposta.processar({"body": {"data": {"contactId": "tardio", "id": "x2", "data": {"text": "oi, vi agora"}}}}, esperar=False)
    assert len(T.get("MENSAGENS_CLIENTE", {"contactId": "tardio"})) == 1


def test_limpeza_inicial_de_mensagens(ambiente):
    from app.fluxos import f2_resposta
    T.insert("MENSAGENS_CLIENTE", {"contactId": "qualquer", "papel": "CLIENTE", "texto": "oi", "ts": 1})
    T.insert("AGUARDANDO_ENTREGA", {"pedidoLider": "9", "contactId": "meu", "status": "AGUARDANDO"})
    T.insert("MENSAGENS_CLIENTE", {"contactId": "meu", "papel": "CLIENTE", "texto": "oi", "ts": 1})
    assert f2_resposta.limpar_mensagens_nao_atendidas() == 1
    assert [m["contactId"] for m in T.get("MENSAGENS_CLIENTE")] == ["meu"]
