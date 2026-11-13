"""Gatilho 'Central - Lider - Decisão de Envio' (webhook central-lider-revisao).

Enviar agora / Não enviar / mensagem editada (Revisão de Envio) e decisão da tela Respostas tardias.
responseMode 'lastNode' na v28: o painel espera o fim do processamento (inclui a pausa de ~5 s antes do template).
"""
import logging
import random
import time

from .. import comum as C
from .. import tabelas as T
from ..integracoes import digisac
from . import gatilho

log = logging.getLogger("central")
MEUS_USER_IDS = ["f4a00c56-b35b-4c7c-a5d5-9f963757ba93"]
BLOQUEAR_FILA_SEM_ATENDENTE = True
DEPARTAMENTO_CENTRAL = "8f751533-3693-4eda-831c-893ddec32690"
USUARIO_TRANSFERENCIA = "f4a00c56-b35b-4c7c-a5d5-9f963757ba93"


def decidir_revisao(body: dict, linha: dict) -> dict | None:
    """Nó 'Decidir Revisão'. None = nada a fazer (resposta tardia já decidida)."""
    dados = C.loads(linha.get("dadosPedido"))
    if not isinstance(dados, dict):
        raise ValueError(f"dadosPedido inválido no pedido {linha.get('pedidoLider')}")
    enviar = body.get("decisao") == "enviar"
    tardia = body.get("origem") == "RESPOSTA_TARDIA"
    if tardia and str(linha.get("status") or "") != "PENDENTE_RESPOSTA_TARDIA":
        return None
    if tardia:
        texto = str(body.get("mensagemPersonalizada") or "").strip()
        modo = "NAO_ENVIAR" if not enviar else ("RESPOSTA_DIFERENTE" if texto else "FLUXO_NORMAL")
        if modo == "RESPOSTA_DIFERENTE":
            dados["mensagemPadrao"] = dados.get("mensagem")
            dados["mensagem"] = texto
            dados["anexoUrlPadrao"] = dados.get("anexoUrl")
            dados["anexoUrl"] = ""
        dados["respostaTardiaDecisao"] = {"modo": modo, "texto": texto if modo == "RESPOSTA_DIFERENTE" else "",
                                          "decididoEm": C.agora_iso_utc()}
    editada = str(body.get("mensagemEditada") or "").replace("\r\n", "\n").strip()
    if not tardia and enviar and editada and editada != str(dados.get("mensagem") or "").strip():
        if dados.get("mensagemOriginal") is None:
            dados["mensagemOriginal"] = dados.get("mensagem")
        dados["mensagem"] = editada
        dados["mensagemEditada"] = {"editadaEm": C.agora_iso_utc()}
    return {**dados, "pedidoLider": str(linha.get("pedidoLider")), "enviar": enviar, "origemTardia": tardia,
            "dadosPedidoFinal": C.dumps(dados)}


def mapa_nomes(usuarios) -> dict:
    nomes = {}

    def coletar(v):
        if not v:
            return
        if isinstance(v, list):
            for x in v:
                coletar(x)
            return
        if not isinstance(v, dict):
            return
        i, n = v.get("id") or v.get("userId"), v.get("name") or v.get("nome")
        if i and n:
            nomes[str(i)] = str(n)
        for k in ("data", "users", "items", "results", "rows"):
            if isinstance(v.get(k), (dict, list)):
                coletar(v[k])
    coletar(usuarios)
    return nomes


def avaliar_chamado(contact_id, respostas: list, nomes: dict) -> dict:
    """Nó 'Avaliar chamado (envio)' (mesma regra do lembrete, reenvio e retomada)."""
    cid = str(contact_id or "").strip()
    nome_de = lambda i: nomes.get(str(i)) or str(i)  # noqa: E731

    def r(livre, sit, motivo, **extra):
        return {"chamadoLivre": livre, "chamadoSituacao": sit, "chamadoMotivo": motivo,
                "chamadoVerificadoEm": C.agora_iso_utc(), **extra}
    if not cid:
        return r(False, "INDETERMINADO", "Sem contactId para consultar o chamado.")
    itens = [x for x in (respostas or []) if x]
    if not itens:
        return r(False, "INDETERMINADO", "Consulta de chamados sem resposta.")
    com_erro = next((j for j in itens if j.get("error")), None)
    if com_erro:
        e = com_erro["error"]
        msg = e if isinstance(e, str) else (e.get("message") if isinstance(e, dict) and e.get("message") else C.dumps(e))
        return r(False, "INDETERMINADO", "Erro ao consultar chamados: " + str(msg)[:200])
    lista = None
    if len(itens) == 1 and isinstance(itens[0].get("data"), list):
        lista = itens[0]["data"]
    elif all("isOpen" in j for j in itens):
        lista = itens
    if not isinstance(lista, list):
        return r(False, "INDETERMINADO", "Resposta inesperada da consulta de chamados.")
    if any(t and t.get("contactId") and str(t["contactId"]) != cid for t in lista):
        return r(False, "INDETERMINADO", "A API não filtrou por contato; envio bloqueado por segurança.")
    abertos = [t for t in lista if t and t.get("isOpen") in (True, "true", 1)]
    if not abertos:
        return r(True, "SEM_CHAMADO", "Nenhum chamado aberto para o contato.")
    if any("userId" not in t for t in abertos):
        return r(False, "INDETERMINADO", "Chamado aberto sem a informação do atendente.")
    de_outros = [t for t in abertos if str(t.get("userId") or "") not in MEUS_USER_IDS]
    if not de_outros:
        return r(True, "CHAMADO_MEU", "Chamado aberto já está comigo.", chamadoId=str(abertos[0].get("id") or ""))
    com_at = next((t for t in de_outros if t.get("userId")), None)
    if com_at:
        return r(False, "OCUPADO", f"Chamado aberto com {nome_de(com_at['userId'])}.",
                 chamadoId=str(com_at.get("id") or ""), chamadoUserId=str(com_at["userId"]),
                 chamadoAtendente=nome_de(com_at["userId"]), chamadoDepartamentoId=str(com_at.get("departmentId") or ""))
    if BLOQUEAR_FILA_SEM_ATENDENTE:
        return r(False, "FILA_SEM_ATENDENTE", "Chamado aberto na fila, ainda sem atendente.",
                 chamadoId=str(de_outros[0].get("id") or ""), chamadoDepartamentoId=str(de_outros[0].get("departmentId") or ""))
    return r(True, "FILA_LIBERADA", "Chamado na fila sem atendente (liberado pela configuração).",
             chamadoId=str(de_outros[0].get("id") or ""))


def listar_usuarios_todos() -> list:
    """GET /users com paginação (até a última página)."""
    paginas, pagina = [], 1
    while pagina <= 50:
        r = digisac._seguro(digisac._req, "GET", "/api/v1/users", params={"perPage": "100", "page": str(pagina)})
        paginas.append(r)
        lista = r.get("data") if isinstance(r.get("data"), list) else []
        if r.get("error") or not lista:
            break
        atual = int(r.get("currentPage") or pagina)
        ultima = int(r.get("lastPage") or ((-(-int(r["total"]) // int(r["perPage"]))) if r.get("total") and r.get("perPage") else 0))
        if not ultima or atual >= ultima:
            break
        pagina += 1
    return paginas


def dados_com_espera(base: dict, av: dict) -> str:
    ce = base.get("chamadoEspera") or {}
    return C.dumps({**base, "chamadoEspera": {**av, "desde": ce.get("desde") or av["chamadoVerificadoEm"],
                                               "verificacoes": int(float(ce.get("verificacoes") or 0)) + 1}})


def processar_decisao(body: dict) -> dict:
    status_busca = "PENDENTE_RESPOSTA_TARDIA" if body.get("origem") == "RESPOSTA_TARDIA" else "PENDENTE_REVISAO"
    linhas = T.get("AGUARDANDO_ENTREGA", {"pedidoLider": body.get("pedidoLider"), "status": status_busca})
    if not linhas:
        return {"resultado": "nada a fazer"}
    p = decidir_revisao(body, linhas[0])
    if p is None:
        return {"resultado": "já decidido"}
    if p["origemTardia"]:
        T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p["pedidoLider"], "status": "PENDENTE_RESPOSTA_TARDIA"},
                 {"status": "PENDENTE_REVISAO", "dadosPedido": p["dadosPedidoFinal"]})
        try:
            T.update("SEM_CONFIRMACAO_DIARIO",
                     {"pedidoLider": (p.get("respostaTardia") or {}).get("pedidoLiderRegistro") or p["pedidoLider"],
                      "status": "RESPONDEU_DEPOIS"}, {"status": "RESPOSTA_TARDIA_TRATADA"})
        except Exception:  # noqa: BLE001
            log.exception("Marcar resposta tardia tratada")
    if not p["enviar"]:
        T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p["pedidoLider"], "status": "PENDENTE_REVISAO"}, {"status": "CANCELADO"})
        return {"resultado": "CANCELADO"}

    usuarios = listar_usuarios_todos()
    time.sleep(round((5 + random.random()) * 10) / 10)          # Timer envio Template
    resp = digisac.tickets_abertos(p.get("contactId")) if p.get("contactId") else {"error": "sem contactId"}
    av = avaliar_chamado(p.get("contactId"), [resp], mapa_nomes(usuarios))
    base = C.loads(p.get("dadosPedidoFinal") or linhas[0].get("dadosPedido") or "{}", {}) or {}
    if not av["chamadoLivre"]:
        T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p["pedidoLider"], "status": "PENDENTE_REVISAO"},
                 {"status": "AGUARDANDO_CHAMADO_LIVRE", "dadosPedido": dados_com_espera(base, av)})
        return {"resultado": "AGUARDANDO_CHAMADO_LIVRE", "motivo": av["chamadoMotivo"]}

    digisac.enviar_template(p.get("phone"), p.get("serviceId"))
    digisac.transferir_chamado(p.get("contactId"), DEPARTAMENTO_CENTRAL, USUARIO_TRANSFERENCIA,
                               f"{p['pedidoLider']} - {p.get('clienteLider')}")
    T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p["pedidoLider"], "status": "PENDENTE_REVISAO"}, {
        "contactId": p.get("contactId"), "serviceId": p.get("serviceId"), "phone": p.get("phone"),
        "status": "AGUARDANDO", "template": "conf002", "enviadoEm": C.agora_iso(), "pedidoLider": p["pedidoLider"],
        "mensagem": p.get("mensagem"), "cliente": p.get("clienteLider"), "responsavel": p.get("RESPONSÁVEL"),
        "tipoMensagem": p.get("tipoMensagem"), "anexoUrl": p.get("anexoUrl")})
    return {"resultado": "AGUARDANDO"}


@gatilho("central-lider-revisao")
def decisao_envio(entrada, req):
    body = entrada.get("body") if isinstance(entrada.get("body"), dict) else {}
    return processar_decisao(body), 200
