"""Agendamentos da v28 (além do 'chamados ocupados'):

  varredura_vigilancia     */10 min        fecha chamados com vigilância vencida e cobra o consultor
  lembrete_13h             seg-sex 13:00   lembrete a quem recebeu a confirmação e não respondeu
  reenvio_template         seg-sex 13:20   reenvia o template a quem não aceitou o 1º
  varredura_tardia         seg-sex 08:05   recupera respostas que chegaram fora do ar / encerra abertos de dias anteriores
  encerramento_pendencias  16:20 seg-qui / 15:20 sex   encerra "sem retorno"
  ao_iniciar               ao subir o servidor (60 s depois): varredura tardia

As funções puras são traduções 1:1 dos nós Code (testadas contra o JavaScript original).
"""
import logging
import random
import re
import time
from datetime import datetime, timezone

from .. import comum as C
from .. import tabelas as T
from ..integracoes import digisac, email, planilha
from . import agendamento
from .f1_revisao import avaliar_chamado

log = logging.getLogger("central")
EMAIL_AVISOS = "mateus.oliveira@lider.design"
MEUS_USER_IDS = ["f4a00c56-b35b-4c7c-a5d5-9f963757ba93"]


def _chat(valor) -> list:
    c = C.loads(C.js_or(valor, "[]"), None)
    return c if isinstance(c, list) else []


def _dp(valor) -> dict:
    d = C.loads(C.js_or(valor, "{}"), {})
    return d if isinstance(d, dict) else {}


def _up(v) -> str:
    return str(C.nn(v, "")).strip().upper()


def _timer():
    time.sleep(round((1 + random.random()) * 10) / 10)


# ===================================================================== VARREDURA DE VIGILÂNCIA (10 min)
def selecionar_acoes_vigilancia(linhas: list[dict], agora_ms: int | None = None) -> list[dict]:
    agora_ms = agora_ms if agora_ms is not None else C.agora_ms()
    lembrar_apos, repetir_apos, max_lembretes = 60, 180, 4

    def minutos(ts):
        t = C.js_date_ms(ts)
        return None if t is None else (agora_ms - t) / 60000
    out = []
    for r in linhas:
        if not r or r.get("id") is None or not str(C.nn(r.get("pedidoLider"), "")).strip():
            continue
        status = str(C.nn(r.get("status"), ""))
        chat = _chat(r.get("chatConsultor"))
        base = {"id": r["id"], "pedidoLider": r["pedidoLider"], "cliente": C.js_or(r.get("cliente"), ""),
                "contactId": C.js_or(r.get("contactId"), ""), "status": status}
        if status == "AGUARDANDO_CONSULTOR":
            perguntas = [m for m in chat if isinstance(m, dict) and m.get("role") == "ia" and m.get("tipo") == "pergunta"]
            lembretes = [m for m in chat if isinstance(m, dict) and m.get("tipo") == "lembrete"]
            ref = perguntas[-1].get("ts") if perguntas else C.js_or(r.get("respondidoEm"), r.get("enviadoEm"))
            desde = minutos(ref)
            if desde is None or desde < lembrar_apos or len(lembretes) >= max_lembretes:
                continue
            ult = minutos(lembretes[-1].get("ts")) if lembretes else None
            if ult is not None and ult < repetir_apos:
                continue
            novo = [*chat, {"role": "ia", "tipo": "lembrete",
                            "texto": f"Lembrete enviado ao responsável por e-mail: consulta sem resposta há {C.js_round(desde)} min.",
                            "ts": C.agora_iso_utc()}]
            out.append({"acao": "LEMBRAR", **base, "minutos": C.js_round(desde), "chatConsultorNovo": C.dumps(novo)})
            continue
        if not str(C.nn(r.get("vigiaAte"), "")).strip():
            continue
        venc = C.js_date_ms(r.get("vigiaAte"))
        if venc is not None and venc > agora_ms:
            continue
        pode = status == "CONCLUIDO" and C.js_truthy(r.get("contactId"))
        novo = [*chat, {"role": "ia", "tipo": "encerramento",
                        "texto": "Vigilância encerrada: chamado fechado automaticamente." if pode
                        else f"Vigilância encerrada (status {status}); chamado mantido aberto.", "ts": C.agora_iso_utc()}]
        out.append({"acao": "FECHAR" if pode else "LIMPAR", **base, "chatConsultorNovo": C.dumps(novo)})
    return out


@agendamento("varredura_vigilancia")
def varredura_vigilancia():
    acoes = selecionar_acoes_vigilancia(T.get("AGUARDANDO_ENTREGA"))
    cont = {"FECHAR": 0, "LIMPAR": 0, "LEMBRAR": 0}
    for a in acoes:
        cont[a["acao"]] += 1
        ped, cli = C.js_str(a["pedidoLider"]), C.js_str(a["cliente"])
        if a["acao"] in ("FECHAR", "LIMPAR"):
            T.update("AGUARDANDO_ENTREGA", {"id": a["id"]}, {"vigiaAte": "", "chatConsultor": a["chatConsultorNovo"]})
            if a["acao"] == "FECHAR":
                r = digisac.fechar_chamado(a["contactId"])
                if (r or {}).get("error"):
                    email.enviar(EMAIL_AVISOS, f"Falha ao fechar chamado - Pedido {ped}",
                                 f"<p>A vigilância do pedido <b>{ped}</b> ({cli}) venceu, mas o DigiSac não fechou o chamado. "
                                 "Feche manualmente.</p>")
        else:
            T.update("AGUARDANDO_ENTREGA", {"id": a["id"]}, {"chatConsultor": a["chatConsultorNovo"]})
            email.enviar(EMAIL_AVISOS, f"Consulta da IA sem resposta - Pedido {ped}",
                         f"<p>A IA está aguardando sua orientação sobre o pedido <b>{ped}</b> ({cli}) há {a['minutos']} min. "
                         "Abra a aba <b>Consultas da IA</b> na Central Líder e responda ou solicite a transferência.</p>")
    if acoes:
        log.info("Varredura de vigilância: %s", cont)
    return cont


# ===================================================================== REENVIO DO TEMPLATE (13:20)
def filtrar_reenvio(linhas: list[dict], agora_ms: int | None = None) -> list[dict]:
    agora_ms = agora_ms if agora_ms is not None else C.agora_ms()
    por = {}
    for r in linhas:
        if _up(r.get("status")) != "AGUARDANDO":
            continue
        if "reenvio" in str(C.nn(r.get("template"), "")).lower():
            continue
        cid, phone, sid = (str(C.nn(r.get(k), "")).strip() for k in ("contactId", "phone", "serviceId"))
        if not cid or not phone or not sid:
            continue
        env = C.js_date_ms(r.get("enviadoEm"))
        if env is None:
            continue
        idade = (agora_ms - env) / 60000
        if idade < 60 or idade > 72 * 60:
            continue
        por.setdefault(cid, {"contactId": cid, "phone": phone, "serviceId": sid, "pedidos": []})
        por[cid]["pedidos"].append(C.js_str(C.nn(r.get("pedidoLider"), "")))
    return list(por.values())


@agendamento("reenvio_template")
def reenvio_template():
    fila = filtrar_reenvio(T.get("AGUARDANDO_ENTREGA", {"status": "AGUARDANDO"}))
    res = {"contatos": len(fila), "reenviados": 0}
    for item in fila:
        _timer()
        av = {**item, **avaliar_chamado(item["contactId"], [digisac.tickets_abertos(item["contactId"])], {})}
        if av["chamadoLivre"] is not True:
            continue
        envio = digisac.enviar_template(av["phone"], av["serviceId"])
        if (envio or {}).get("error"):
            continue
        T.update("AGUARDANDO_ENTREGA", {"contactId": item["contactId"], "status": "AGUARDANDO"}, {"template": "conf002_reenvio"})
        res["reenviados"] += 1
    log.info("Reenvio do template: %s", res)
    return res


# ===================================================================== LEMBRETE DE CONFIRMAÇÃO (13:00)
PROTEGER_LEMBRETE = ["AGUARDANDO", "AGUARDANDO_CONSULTOR", "AGUARDANDO_DECISAO_RESPONSAVEL", "TRANSFERIDO",
                     "TRANSFERENCIA_MANUAL", "ESCALADO", "PENDENTE_REVISAO", "PENDENTE_RESPOSTA_TARDIA",
                     "AGUARDANDO_CHAMADO_LIVRE", "EM_PROCESSAMENTO"]


def _primeiro_nome_lembrete(r: dict, dp: dict):
    m = re.match(r"^\s*Ol[áa],\s*([^!\n,]{2,30})!", str(C.js_or(r.get("mensagem"), dp.get("mensagem"), "")), re.I)
    if m:
        return m.group(1).strip()
    n = re.sub(r"^[\d\s.\-/]+-\s*", "", str(C.nn(r.get("cliente"), ""))).strip()
    if not n or re.search(r"\b(LTDA|S/A|SA|ME|EIRELI|SISTEMAS|COMERCIO|INDUSTRIA)\b", n, re.I):
        return None
    x = n.split()[0]
    return x[:1].upper() + x[1:].lower()


def _lista_pedidos(ps):
    return f"*{ps[0]}*" if len(ps) == 1 else ", ".join(f"*{p}*" for p in ps[:-1]) + f" e *{ps[-1]}*"


def filtrar_lembrete(linhas_brutas: list[dict], msgs_brutas: list[dict], agora_ms: int | None = None) -> list[dict]:
    agora_ms = agora_ms if agora_ms is not None else C.agora_ms()
    if any(m and m.get("error") for m in msgs_brutas):
        return []
    msgs = [m for m in msgs_brutas if m and m.get("contactId") is not None]
    linhas = [r for r in linhas_brutas if r and r.get("id") is not None]
    por = {}
    for r in linhas:
        cid = str(C.nn(r.get("contactId"), "")).strip()
        if cid:
            por.setdefault(cid, []).append(r)
    saida = []
    for cid, rows in por.items():
        if any(_up(r.get("status")) in PROTEGER_LEMBRETE for r in rows):
            continue

        def elegivel(r):
            if _up(r.get("status")) != "DATA_ENVIADA" or str(C.nn(r.get("categoria"), "")).strip():
                return False
            if C.js_truthy(_dp(r.get("dadosPedido")).get("lembreteConfirmacaoEm")):
                return False
            t = C.js_date_ms(r.get("respondidoEm"))
            if t is None:
                return False
            idade = (agora_ms - t) / 60000
            return 60 <= idade <= 23 * 60
        alvo = [r for r in rows if elegivel(r)]
        if not alvo:
            continue
        if any(_up(r.get("status")) == "DATA_ENVIADA" and all(r is not a for a in alvo) for r in rows):
            continue
        desde = min(C.js_date_ms(r.get("respondidoEm")) for r in alvo)

        def num_ts(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return float("nan")
        if any(str(m.get("contactId")).strip() == cid and _up(m.get("papel")) == "CLIENTE" and num_ts(m.get("ts")) > desde
               for m in msgs):
            continue
        pedidos = []

        def add(p):
            x = C.n_ped(p)
            if x and x not in pedidos:
                pedidos.append(x)
        for r in alvo:
            add(r.get("pedidoLider"))
            dp = _dp(r.get("dadosPedido"))
            for g in (dp.get("pedidosGrupo") if isinstance(dp.get("pedidosGrupo"), list) else []):
                add(g.get("pedidoLider") if isinstance(g, dict) else g)
            for x in rows:
                if _up(x.get("status")) == "AGRUPADO" and C.n_ped(_dp(x.get("dadosPedido")).get("agrupadoEm")) == C.n_ped(r.get("pedidoLider")):
                    add(x.get("pedidoLider"))
        pedidos.sort(key=lambda p: int(p))
        tipos = [str(C.js_or(r.get("tipoMensagem"), _dp(r.get("dadosPedido")).get("tipoMensagem"), "")).upper() for r in alvo]
        so_primeira = bool(tipos) and all(t == "PRIMEIRA_CONFIRMACAO" for t in tipos)
        nome = _primeiro_nome_lembrete(alvo[0], _dp(alvo[0].get("dadosPedido")))
        plural = len(pedidos) > 1
        ped = f"{'dos pedidos' if plural else 'do pedido'} nº {_lista_pedidos(pedidos)}"
        pergunta = (f"Pode nos confirmar o recebimento da mensagem sobre {'os seus pedidos' if plural else 'o seu pedido'} "
                    f"nº {_lista_pedidos(pedidos)}?" if so_primeira else f"Podemos confirmar a data de entrega {ped}?")
        saida.append({"contactId": cid, "rowIds": [r["id"] for r in alvo],
                      "respondidoEmOriginal": [C.js_str(r.get("respondidoEm")) for r in alvo], "pedidos": pedidos,
                      "cliente": str(C.nn(alvo[0].get("cliente"), "")),
                      "tipoLembrete": "PRIMEIRA_CONFIRMACAO" if so_primeira else "DATA",
                      "mensagem": f"{C.saudacao()}{', ' + nome if nome else ''}!\n\n{pergunta}"})
    return saida


def pode_enviar_lembrete(item: dict, atuais_brutos: list[dict]) -> dict:
    atuais = [r for r in atuais_brutos if r and r.get("id") is not None]
    motivo = ""
    if any(r and r.get("error") for r in atuais_brutos):
        motivo = "Erro ao reconferir o pedido."
    elif item.get("chamadoSituacao") != "CHAMADO_MEU":
        motivo = f"Chamado não está comigo ({C.js_str(item.get('chamadoSituacao'))}): {C.js_or(item.get('chamadoMotivo'), '')}".strip()
    elif any(str(C.nn(r.get("contactId"), "")).strip() == str(item.get("contactId")) and _up(r.get("status")) in PROTEGER_LEMBRETE
             for r in atuais):
        motivo = "Outro pedido do contato em atendimento."
    else:
        orig = item.get("respondidoEmOriginal") or []
        for k, rid in enumerate(item.get("rowIds") or []):
            r = next((x for x in atuais if str(x["id"]) == str(rid)), None)
            if not r:
                motivo = "Pedido não encontrado na reconferência."
                break
            if _up(r.get("status")) != "DATA_ENVIADA" or str(C.nn(r.get("categoria"), "")).strip():
                motivo = "Cliente respondeu antes do lembrete."
                break
            if C.js_str(r.get("respondidoEm")) != (orig[k] if k < len(orig) else "undefined"):
                motivo = "Pedido mudou desde a leitura das 13:00."
                break
            if C.js_truthy(_dp(r.get("dadosPedido")).get("lembreteConfirmacaoEm")):
                motivo = "Lembrete já enviado."
                break
    enviado_em = C.agora_iso_utc()
    marcar = [] if motivo else [
        {"id": rid, "dadosPedido": C.dumps({**_dp(next(x for x in atuais if str(x["id"]) == str(rid)).get("dadosPedido")),
                                            "lembreteConfirmacaoEm": enviado_em, "lembreteConfirmacaoTexto": item.get("mensagem")})}
        for rid in (item.get("rowIds") or [])]
    return {**item, "enviar": not motivo, "motivoLembrete": motivo or "OK", "linhasMarcar": marcar}


@agendamento("lembrete_13h")
def lembrete_13h():
    fila = filtrar_lembrete(T.get("AGUARDANDO_ENTREGA"), T.get("MENSAGENS_CLIENTE"))
    res = {"contatos": len(fila), "enviados": 0}
    for item in fila:
        _timer()
        av = {**item, **avaliar_chamado(item["contactId"], [digisac.tickets_abertos(item["contactId"])], {})}
        try:
            atuais = T.get("AGUARDANDO_ENTREGA", {"contactId": item["contactId"]})
        except Exception as exc:  # noqa: BLE001
            atuais = [{"error": str(exc)}]
        p = pode_enviar_lembrete(av, atuais)
        if p["enviar"] is not True:
            log.info("Lembrete não enviado para %s: %s", item["contactId"], p["motivoLembrete"])
            continue
        envio = digisac.enviar_mensagem(p["contactId"], p["mensagem"])
        if (envio or {}).get("error"):
            continue
        for l in p["linhasMarcar"]:
            T.update("AGUARDANDO_ENTREGA", {"id": l["id"]}, {"dadosPedido": l["dadosPedido"]})
        ts = C.agora_ms()
        try:
            T.insert("MENSAGENS_CLIENTE", {"contactId": p["contactId"], "messageId": f"lider-lembrete-{ts}", "papel": "BOT",
                                           "texto": str(p["mensagem"])[:3000], "ts": ts, "recebidoEm": C.agora_iso()})
        except Exception:  # noqa: BLE001
            log.exception("Registrar lembrete na conversa")
        res["enviados"] += 1
    log.info("Lembrete 13h: %s", res)
    return res


# ===================================================================== ENCERRAMENTO SEM RETORNO (16:20 / 15:20)
ETAPA_SEM_RETORNO = {"AGUARDANDO": "SEM_RETORNO_TEMPLATE", "DATA_ENVIADA": "SEM_RETORNO_CONFIRMACAO",
                     "AGUARDANDO_CHAMADO_LIVRE": "SEM_RETORNO_CHAMADO_OCUPADO"}
COM_RESPONSAVEL = ["TRANSFERIDO", "TRANSFERENCIA_MANUAL", "ESCALADO"]
PROTEGER_CHAMADO = [*COM_RESPONSAVEL, "AGUARDANDO_CONSULTOR", "AGUARDANDO_DECISAO_RESPONSAVEL"]


def filtrar_sem_retorno(sheet_rows: list[dict], table_brutos: list[dict], varredura: dict | None = None) -> list[dict]:
    """Nó 'Filtrar sem retorno elegível'. varredura = {'ids': set, 'dia': {id: dataRef}} quando vem da varredura tardia."""
    norm = lambda v: C.sem_acento(str(C.nn(v, "")).strip()).upper()  # noqa: E731
    brutos = [t for t in table_brutos if t and "pedidoLider" in t]
    todos = []
    for t in brutos:
        if norm(t.get("status")) != "AGRUPADO":
            todos.append(t)
            continue
        ag = _dp(t.get("dadosPedido")).get("agrupadoEm")
        p = next((x for x in brutos if C.n_ped(x.get("pedidoLider")) == C.n_ped(ag) and norm(x.get("status")) != "AGRUPADO"), None)
        todos.append({**t, "status": p.get("status"), "contactId": p.get("contactId"),
                      "responsavel": C.js_or(t.get("responsavel"), p.get("responsavel")),
                      "cliente": C.js_or(t.get("cliente"), p.get("cliente")), "agrupadoEm": C.js_str(p.get("pedidoLider")),
                      "_idPrincipal": C.js_str(p.get("id"))} if p else t)
    tabela = ([t for t in todos if str(t.get("id")) in varredura["ids"] or (t.get("_idPrincipal") and t["_idPrincipal"] in varredura["ids"])]
              if varredura else todos)
    agora_txt = C.agora().strftime("%d/%m/%Y %H:%M")
    com_resp = {str(t["contactId"]).strip() for t in todos
                if norm(t.get("status")) in PROTEGER_CHAMADO and str(C.nn(t.get("contactId"), "")).strip()}
    a_fechar = set()
    saida = []
    for row in sheet_rows:
        pedido = C.nn(row.get("Pedido"), row.get("PEDIDO"), row.get("pedidoLider"))
        if not C.js_truthy(pedido) or row.get("row_number") is None:
            continue
        if any(str(C.nn(row.get(c), "")).strip() != "" for c in ("CONFIRMADO", "MOTIVO", "DATA ENVIO CONF.")):
            continue
        key = C.n_ped(pedido)
        matches = [t for t in tabela if C.n_ped(t.get("pedidoLider")) == key]
        if not matches or any(norm(t.get("status")) in COM_RESPONSAVEL for t in matches):
            continue
        t = next((m for m in matches if norm(m.get("status")) in ETAPA_SEM_RETORNO and norm(m.get("status")) != "AGUARDANDO_CHAMADO_LIVRE"
                  and str(C.nn(m.get("contactId"), "")).strip()), None) \
            or next((m for m in matches if norm(m.get("status")) == "AGUARDANDO_CHAMADO_LIVRE"), None)
        if not t:
            continue
        ocupado = norm(t.get("status")) == "AGUARDANDO_CHAMADO_LIVRE"
        cid = str(C.nn(t.get("contactId"), "")).strip() or str(C.nn(_dp(t.get("dadosPedido")).get("contactId"), "")).strip()
        fechar = bool(cid) and cid not in com_resp and cid not in a_fechar
        if fechar:
            a_fechar.add(cid)
        if ocupado:
            ce = _dp(t.get("dadosPedido")).get("chamadoEspera") or {}
            quem = (f" com {ce['chamadoAtendente']}" if C.js_truthy(ce.get("chamadoAtendente"))
                    else " na fila sem atendente" if ce.get("chamadoSituacao") == "FILA_SEM_ATENDENTE" else "")
            resumo = (f"Sem retorno do cliente: chamado ocupado o dia todo{quem}, template não enviado; "
                      f"encerrado automaticamente em {agora_txt}")
        else:
            resumo = f"Sem retorno do cliente; chamado encerrado automaticamente em {agora_txt}"
        if varredura:
            resumo += " (varredura da manhã: o encerramento da tarde não rodou)"
        dia = None
        if varredura:
            dia = varredura["dia"].get(str(t.get("id"))) or varredura["dia"].get(C.js_str(t["_idPrincipal"]) if "_idPrincipal" in t else "undefined")
        saida.append({"row_number": int(float(row["row_number"])), "pedido": C.js_str(pedido),
                      "pedidoLider": str(C.nn(t.get("pedidoLider"), "")).strip(), "responsavel": str(C.nn(t.get("responsavel"), "")).strip(),
                      "contactId": cid, "dataTableId": t.get("id"), "statusAnterior": t.get("status"),
                      "etapaSemRetorno": ETAPA_SEM_RETORNO.get(norm(t.get("status"))),
                      "cliente": C.nn(row.get("Cliente"), row.get("CLIENTE"), t.get("cliente"), ""), "fecharChamado": fechar,
                      "chamadoOcupado": ocupado, "resumoEncerramento": resumo, "dataRef": dia or None})
    return saida


def reconferir_fila(orig: dict, resp: dict) -> dict:
    cid = str(C.nn(orig.get("contactId"), "")).strip()
    resp = resp or {}
    body = resp["body"] if "body" in resp else resp

    def avaliar():
        if not cid:
            return "INDETERMINADO", "Sem contactId."
        if C.js_truthy(resp.get("error")):
            return "INDETERMINADO", "Erro ao consultar chamados."
        lista = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else body if isinstance(body, list) else None
        if not isinstance(lista, list):
            return "INDETERMINADO", "Resposta inesperada da consulta de chamados."
        if any(t and t.get("contactId") and str(t["contactId"]) != cid for t in lista):
            return "INDETERMINADO", "A API não filtrou por contato."
        abertos = [t for t in lista if t and t.get("isOpen") in (True, "true", 1)]
        if not abertos:
            return "SEM_CHAMADO", "Nenhum chamado aberto."
        if any("userId" not in t for t in abertos):
            return "INDETERMINADO", "Chamado aberto sem a informação do atendente."
        outros = [t for t in abertos if str(C.nn(t.get("userId"), "")) not in MEUS_USER_IDS]
        if not outros:
            return "CHAMADO_MEU", "Chamado já está comigo."
        if any(C.js_truthy(t.get("userId")) for t in outros):
            return "OCUPADO", "Chamado com outro atendente."
        return "FILA_SEM_ATENDENTE", "Chamado na fila sem atendente."
    sit, mot = avaliar()
    return {**orig, "fecharChamado": sit in ("FILA_SEM_ATENDENTE", "CHAMADO_MEU"), "chamadoReconferido": sit,
            "chamadoReconferidoMotivo": mot}


def encerrar_sem_retorno(varredura: dict | None = None) -> dict:
    """Nós de 'Ler planilha de confirmações' até 'Registrar sem confirmação do dia'."""
    sheet = planilha.ler_linhas()
    itens = filtrar_sem_retorno(sheet, T.get("AGUARDANDO_ENTREGA"), varredura)
    res = {"encerrados": 0, "chamadosFechados": 0}
    for it in itens:
        extra = ""
        if it["fecharChamado"] is True:
            fechar = True
            if it["chamadoOcupado"] is True:
                r = digisac.tickets_abertos(it["contactId"])
                rc = reconferir_fila(it, {"error": r["error"]} if r.get("error") else {"body": r})
                fechar = rc["fecharChamado"] is True
                extra = (" | chamado estava na fila e foi fechado" if fechar
                         else f" | chamado não foi fechado ({C.js_str(rc['chamadoReconferidoMotivo'])})")
            if fechar:
                f = digisac.fechar_chamado(it["contactId"])
                if (f or {}).get("error"):
                    extra += " | ATENÇÃO: não foi possível fechar o chamado no Digisac"
                else:
                    res["chamadosFechados"] += 1
        planilha.atualizar("row_number", it["row_number"], {"CONFIRMADO": "NÃO", "MOTIVO": "SEM RETORNO CLIENTE"})
        resumo = C.js_or(it["resumoEncerramento"], "Sem retorno do cliente; chamado encerrado automaticamente em "
                         + C.agora().strftime("%d/%m/%Y %H:%M"))
        T.update("AGUARDANDO_ENTREGA", {"id": it["dataTableId"]}, {"status": "SEM_RETORNO_CLIENTE", "resumoIA": resumo + extra})
        data_ref = it["dataRef"] or C.hoje_iso()
        T.upsert("SEM_CONFIRMACAO_DIARIO", {"pedidoLider": it["pedidoLider"], "dataRef": data_ref}, {
            "pedidoLider": it["pedidoLider"], "cliente": C.js_str(it["cliente"]), "responsavel": it["responsavel"],
            "contactId": it["contactId"], "dataRef": data_ref, "status": C.js_or(it["etapaSemRetorno"], "SEM_RETORNO"),
            "registradoEm": C.agora_iso()})
        res["encerrados"] += 1
    log.info("Encerramento sem retorno%s: %s", " (varredura da manhã)" if varredura else "", res)
    return res


@agendamento("encerramento_pendencias")
def encerramento_pendencias():
    return encerrar_sem_retorno(None)


# ===================================================================== VARREDURA DE RESPOSTAS TARDIAS (08:05 e ao iniciar)
CONSIDERAR = lambda s: s.startswith("SEM_RETORNO") or s == "RESPONDEU_DEPOIS"  # noqa: E731
ABERTOS = ["AGUARDANDO", "DATA_ENVIADA", "AGUARDANDO_CHAMADO_LIVRE"]
PODE_CARTAO = {"ENCERRADO": ["SEM_RETORNO_CLIENTE", "PENDENTE_REVISAO", "PENDENTE_RESPOSTA_TARDIA"],
               "ABERTO": ["AGUARDANDO", "DATA_ENVIADA", "AGUARDANDO_CHAMADO_LIVRE", "PENDENTE_RESPOSTA_TARDIA"]}
SEM_TEXTO = "[mensagem sem texto: áudio, imagem ou arquivo]"
INF = float("inf")


def _inicio_do_dia(dia: str) -> int:
    return C.iso_ms(f"{dia}T00:00:00-03:00")


def _dia_de(v):
    if v is None or v == "":
        return None
    t = C.js_date_ms(v)
    if t is None:
        return None
    return datetime.fromtimestamp((t - 3 * 3600e3) / 1000, timezone.utc).strftime("%Y-%m-%d")


def _linha_do_pedido(ped, linhas, historico):
    k = C.n_ped(ped)
    ag = [r for r in linhas if C.n_ped(r.get("pedidoLider")) == k]
    if ag:
        return next((r for r in ag if _up(r.get("status")) != "AGRUPADO"), ag[0])
    hs = sorted((h for h in historico if C.n_ped(h.get("pedidoLider")) == k),
                key=lambda h: str(C.nn(h.get("arquivadoEm"), "")), reverse=True)
    return {**_dp(hs[0].get("dados")), "_doHistorico": True} if hs else None


def selecionar_contatos_tardia(sem_conf: list[dict], linhas: list[dict], historico: list[dict]) -> list[dict]:
    hoje = C.hoje_iso()
    sem_conf = [r for r in sem_conf if r and not r.get("error") and str(C.nn(r.get("pedidoLider"), "")).strip()]
    linhas = [r for r in linhas if r and not r.get("error") and r.get("id") is not None and str(C.nn(r.get("pedidoLider"), "")).strip()]
    historico = [r for r in historico if r and not r.get("error") and str(C.nn(r.get("pedidoLider"), "")).strip()]
    env_ts = lambda row: C.iso_ms(C.js_or((row or {}).get("enviadoEm"), ""))  # noqa: E731
    alvos = []
    dias = sorted({str(C.nn(r.get("dataRef"), "")).strip() for r in sem_conf if CONSIDERAR(_up(r.get("status")))} - {""})
    dias = [d for d in dias if d < hoje]
    ultimo = dias[-1] if dias else None
    if ultimo:
        for r in sem_conf:
            if str(C.nn(r.get("dataRef"), "")).strip() != ultimo or not CONSIDERAR(_up(r.get("status"))):
                continue
            cid = str(C.nn(r.get("contactId"), "")).strip()
            if not cid:
                continue
            corte = C.iso_ms(C.js_or(r.get("registradoEm"), ""))
            if not corte:
                continue
            env = env_ts(_linha_do_pedido(r.get("pedidoLider"), linhas, historico))
            alvos.append({"tipo": "ENCERRADO", "pedidoLider": C.js_str(r.get("pedidoLider")), "contactId": cid, "dataRef": ultimo,
                          "corte": corte, "desde": min(_inicio_do_dia(ultimo), env or INF), "etapa": _up(r.get("status")),
                          "encerradoEm": C.js_str(r.get("registradoEm")), "statusSemConf": _up(r.get("status"))})
    for r in linhas:
        dia = _dia_de(r.get("createdAt"))
        if not dia or dia >= hoje:
            continue
        st = _up(r.get("status"))
        if st not in ABERTOS:
            continue
        cid = str(C.nn(r.get("contactId"), "")).strip() or str(C.nn(_dp(r.get("dadosPedido")).get("contactId"), "")).strip()
        if not cid:
            continue
        env = env_ts(r)
        alvos.append({"tipo": "ABERTO", "pedidoLider": C.js_str(r.get("pedidoLider")), "contactId": cid, "dataRef": dia,
                      "idLinha": r["id"], "corte": env or _inicio_do_dia(dia), "desde": env or _inicio_do_dia(dia),
                      "etapa": "NAO_ENCERRADO", "statusAnterior": st, "enviadoEm": C.js_str(C.nn(r.get("enviadoEm"), ""))})
    por = {}
    for a in alvos:
        c = por.setdefault(a["contactId"], {"contactId": a["contactId"], "desde": a["desde"], "alvos": []})
        c["desde"] = min(c["desde"], a["desde"])
        c["alvos"].append(a)
    return [{**c, "desdeISO": C.iso_utc_de_ms(int(c["desde"])), "ultimoDia": ultimo, "hoje": hoje} for c in por.values()]


def analisar_respostas_tardia(contatos: list[dict], paginas: list[tuple[int, dict]], linhas: list[dict],
                              historico: list[dict], msgs_tabela: list[dict]) -> list[dict]:
    """paginas: (índice do contato, resposta da API) — uma por página buscada."""
    linhas = [r for r in linhas if r and not r.get("error") and r.get("id") is not None and str(C.nn(r.get("pedidoLider"), "")).strip()]
    historico = [r for r in historico if r and not r.get("error") and str(C.nn(r.get("pedidoLider"), "")).strip()]
    msgs_tabela = [m for m in msgs_tabela if m and not m.get("error")]
    cids = [str(c["contactId"]) for c in contatos]
    api_por: dict[str, dict] = {}
    falhou = set()
    for idx, j in paginas:
        j = j or {}
        cid_par = cids[idx] if idx is not None and idx < len(cids) else None
        body = j["body"] if "body" in j else j
        lista = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else body if isinstance(body, list) else None
        if C.js_truthy(j.get("error")) or lista is None:
            if cid_par:
                falhou.add(cid_par)
            continue
        for m in lista:
            if not m or not C.js_truthy(m.get("id")):
                continue
            cid = C.js_str(C.nn(m.get("contactId"), cid_par, ""))
            if not cid:
                continue
            if cid_par and cid != cid_par:
                falhou.add(cid_par)
                continue
            api_por.setdefault(cid, {})[C.js_str(m["id"])] = m
        if cid_par and cid_par not in api_por:
            api_por[cid_par] = {}

    def ts_msg(m):
        t = C.iso_ms(C.js_or(m.get("timestamp"), m.get("createdAt"), ""))
        if t:
            return t
        try:
            n = float(m.get("timestamp"))
            return n if n == n else 0
        except (TypeError, ValueError):
            return 0

    def texto_msg(m):
        d = m.get("data") if isinstance(m.get("data"), dict) else {}
        return str(C.js_or(d.get("text"), m.get("text"), "")).strip() or SEM_TEXTO

    def ts_tab(m):
        try:
            n = float(m.get("ts"))
            if n == n and n:
                return n
        except (TypeError, ValueError):
            pass
        return C.iso_ms(m.get("recebidoEm"))

    def principal(row):
        if not row or _up(row.get("status")) != "AGRUPADO":
            return row
        ag = _dp(row.get("dadosPedido")).get("agrupadoEm")
        p = _linha_do_pedido(ag, linhas, historico) if C.js_truthy(ag) else None
        return p if p and _up(p.get("status")) != "AGRUPADO" else row

    saida, encerrar, cartoes = [], [], set()
    logr = {"contatos": len(contatos), "falhas": [], "cartoes": [], "gravadas": 0, "encerrar": [], "ignorados": []}
    for c in contatos:
        cid = str(c["contactId"])
        if cid in falhou or cid not in api_por:
            logr["falhas"].append(cid)
            continue
        do_tab = [m for m in msgs_tabela if str(C.nn(m.get("contactId"), "")).strip() == cid]
        conhecidas = {C.js_str(C.nn(m.get("messageId"), "")) for m in do_tab}
        api = [{"id": C.js_str(m["id"]), "ts": ts_msg(m), "cliente": m.get("isFromMe") is not True, "texto": texto_msg(m),
                "nova": C.js_str(m["id"]) not in conhecidas}
               for m in api_por[cid].values()
               if str(C.nn(m.get("type"), "")).lower() not in ("ticket", "comment") and ts_msg(m)]
        novas = [m for m in api if m["cliente"] and m["nova"] and m["ts"] >= c["desde"]]
        for m in novas:
            saida.append({"acao": "GRAVAR_MSG", "contactId": cid, "messageId": m["id"], "papel": "CLIENTE", "texto": m["texto"],
                          "ts": m["ts"], "recebidoEm": C.iso_utc_de_ms(int(m["ts"]))})
            logr["gravadas"] += 1
        ids_novas = {m["id"] for m in novas}
        for a in c["alvos"]:
            cli_tab = [{"id": C.js_str(C.nn(m.get("messageId"), "")), "ts": ts_tab(m), "cliente": True,
                        "texto": str(C.nn(m.get("texto"), "")).strip() or SEM_TEXTO}
                       for m in do_tab if _up(m.get("papel")) == "CLIENTE" and ts_tab(m) > a["corte"]]
            cli_api = [m for m in api if m["cliente"] and (m["ts"] > a["corte"] or (m["id"] in ids_novas and m["ts"] >= a["desde"]))]
            mapa = {}
            for m in [*cli_tab, *cli_api]:
                mapa.setdefault(m["id"], m)
            resp_cli = sorted(mapa.values(), key=lambda x: x["ts"])
            if not resp_cli:
                if a["tipo"] == "ABERTO":
                    encerrar.append({"id": a["idLinha"], "pedidoLider": a["pedidoLider"], "dataRef": a["dataRef"]})
                    logr["encerrar"].append(a["pedidoLider"])
                continue
            primeira = resp_cli[0]["ts"]
            row = principal(_linha_do_pedido(a["pedidoLider"], linhas, historico))
            if not row:
                logr["ignorados"].append(f"{a['pedidoLider']}: linha do pedido não encontrada")
                continue
            ped_cartao = C.js_str(row.get("pedidoLider"))
            if C.n_ped(ped_cartao) in cartoes:
                continue
            st = _up(row.get("status"))
            if st not in PODE_CARTAO[a["tipo"]]:
                logr["ignorados"].append(f"{ped_cartao}: pedido já está em {st}")
                continue
            cartoes.add(C.n_ped(ped_cartao))
            lider = [m for m in api if not m["cliente"] and m["ts"] >= primeira]
            fala = lambda m: {"papel": "CLIENTE" if m["cliente"] else "LIDER", "texto": str(m["texto"])[:2000], "ts": m["ts"]}  # noqa: E731
            respostas = [fala(m) for m in sorted([*resp_cli, *lider], key=lambda x: x["ts"])[-20:]]
            contexto = [{"papel": "CLIENTE" if _up(m.get("papel")) == "CLIENTE" else "LIDER",
                         "texto": str(C.nn(m.get("texto"), "")).strip()[:2000], "ts": ts_tab(m)}
                        for m in sorted((m for m in do_tab if ts_tab(m) < primeira and _up(m.get("papel")) != "RECOMECO"),
                                        key=ts_tab)[-6:]]
            dp = _dp(row.get("dadosPedido"))
            rt = {"pedidoLiderRegistro": a["pedidoLider"] if a["tipo"] == "ENCERRADO" else None, "dataRef": a["dataRef"],
                  "encerradoEm": a["encerradoEm"] if a["tipo"] == "ENCERRADO" else "",
                  "enviadoEm": C.js_or(a.get("enviadoEm"), C.js_str(C.nn(row.get("enviadoEm"), ""))), "etapa": a["etapa"],
                  "statusAnterior": st, "contactId": cid, "respostas": respostas, "contexto": contexto, "origem": "VARREDURA",
                  "detectadoEm": C.agora_iso_utc()}
            saida.append({"acao": "CARTAO", "pedidoLider": ped_cartao, "status": "PENDENTE_RESPOSTA_TARDIA",
                          "dadosPedido": C.dumps({**dp, "pedidoLider": C.nn(dp.get("pedidoLider"), ped_cartao), "respostaTardia": rt}),
                          "cliente": C.js_str(C.nn(row.get("cliente"), dp.get("clienteLider"), dp.get("Cliente"), "")),
                          "responsavel": C.js_str(C.nn(row.get("responsavel"), dp.get("responsavel"), "")),
                          "contactId": str(C.nn(row.get("contactId"), "")).strip() or cid,
                          "mensagem": C.js_str(C.nn(row.get("mensagem"), dp.get("mensagem"), "")),
                          "tipoMensagem": C.js_str(C.nn(row.get("tipoMensagem"), dp.get("tipoMensagem"), "")),
                          "marcarSemConf": a["tipo"] == "ENCERRADO" and a.get("statusSemConf") != "RESPONDEU_DEPOIS",
                          "semConfPedido": a["pedidoLider"], "semConfDataRef": a["dataRef"],
                          "recriado": bool(row.get("_doHistorico"))})
            logr["cartoes"].append(f"{ped_cartao} ({len(resp_cli)} msg)")
    if encerrar:
        saida.append({"acao": "ENCERRAR", "linhas": encerrar, "ids": [C.js_str(e["id"]) for e in encerrar]})
    saida.append({"acao": "RESUMO", **logr, "em": C.agora().strftime("%d/%m/%Y %H:%M")})
    return saida


def _buscar_mensagens(contatos: list[dict]) -> list[tuple[int, dict]]:
    """Nó 'Buscar mensagens no DigiSac' (paginação até 10 páginas, 1 contato por vez com 300 ms)."""
    paginas = []
    for idx, c in enumerate(contatos):
        if idx:
            time.sleep(0.3)
        for pagina in range(1, 11):
            r = digisac._seguro(digisac._req, "GET", "/api/v1/messages", params={
                "where[contactId]": c["contactId"], "perPage": "100", "page": str(pagina)})
            paginas.append((idx, r))
            dados = r.get("data") if isinstance(r, dict) else None
            if r.get("error") or not isinstance(dados, list) or len(dados) < 100:
                break
            if r.get("lastPage") is not None and float(r.get("currentPage") or 0) >= float(r["lastPage"]):
                break
    return paginas


@agendamento("varredura_tardia")
def varredura_tardia():
    def ler(tabela):
        try:
            return T.get(tabela)
        except Exception as exc:  # noqa: BLE001
            return [{"error": str(exc)}]
    sem_conf, linhas, hist, msgs = (ler(t) for t in ("SEM_CONFIRMACAO_DIARIO", "AGUARDANDO_ENTREGA", "HISTORICO_PEDIDOS",
                                                     "MENSAGENS_CLIENTE"))
    contatos = selecionar_contatos_tardia(sem_conf, linhas, hist)
    if not contatos:
        return {"contatos": 0}
    acoes = analisar_respostas_tardia(contatos, _buscar_mensagens(contatos), linhas, hist, msgs)
    for a in acoes:
        if a["acao"] == "GRAVAR_MSG":
            try:
                T.insert("MENSAGENS_CLIENTE", {k: a[k] for k in ("contactId", "messageId", "texto", "ts", "recebidoEm")}
                         | {"papel": "CLIENTE"})
            except Exception:  # noqa: BLE001
                log.exception("Gravar mensagem recuperada (varredura tardia)")
    for a in acoes:
        if a["acao"] == "CARTAO":
            try:
                T.upsert("AGUARDANDO_ENTREGA", {"pedidoLider": a["pedidoLider"]},
                         {k: a[k] for k in ("status", "dadosPedido", "cliente", "responsavel", "contactId", "mensagem",
                                            "tipoMensagem", "pedidoLider")})
            except Exception:  # noqa: BLE001
                log.exception("Gravar cartão tardio (varredura tardia)")
            if a["marcarSemConf"] is True:
                try:
                    T.update("SEM_CONFIRMACAO_DIARIO", {"pedidoLider": a["semConfPedido"], "dataRef": a["semConfDataRef"]},
                             {"status": "RESPONDEU_DEPOIS"})
                except Exception:  # noqa: BLE001
                    log.exception("Marcar respondeu depois (varredura tardia)")
    enc = next((a for a in acoes if a["acao"] == "ENCERRAR"), None)
    if enc:
        encerrar_sem_retorno({"ids": set(enc["ids"]), "dia": {str(l["id"]): l["dataRef"] for l in enc["linhas"]}})
    resumo = next(a for a in acoes if a["acao"] == "RESUMO")
    log.info("Varredura tardia: %s", {k: v for k, v in resumo.items() if k != "acao"})
    return resumo


@agendamento("ao_iniciar")
def ao_iniciar():
    """Gatilho 'Varredura tardia - n8n iniciou': espera 60 s (rede) e roda a varredura tardia."""
    time.sleep(60)
    return varredura_tardia()
