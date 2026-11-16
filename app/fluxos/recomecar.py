"""Webhook 'central-lider-recomecar' — Recomeçar pedido / Trocar número (v18–v20 da v28).

Valida o pedido, define o contato do DigiSac (mesmo número, encontrado ou criado), zera a conversa,
devolve o pedido para a Revisão de Envio e, se pedido, avisa o contato anterior.
"""
import logging
import re

from .. import comum as C
from .. import tabelas as T
from ..integracoes import digisac
from . import gatilho

log = logging.getLogger("central")
PODE = ["PENDENTE_REVISAO", "PENDENTE_RESPOSTA_TARDIA", "AGUARDANDO_CHAMADO_LIVRE", "AGUARDANDO", "DATA_ENVIADA",
        "AGUARDANDO_DECISAO_RESPONSAVEL", "AGUARDANDO_CONSULTOR", "ESCALADO", "TRANSFERIDO", "TRANSFERENCIA_MANUAL",
        "SEM_RETORNO_CLIENTE", "CANCELADO", "CONCLUIDO"]
SO_COM_NUMERO_NOVO = ["PENDENTE_REVISAO", "PENDENTE_RESPOSTA_TARDIA"]
SERVICES = ["1211d47b-8ab8-47e8-8055-6b2307a8f466", "6518c8e7-72a4-4796-bb09-2ebd252ef2d6"]
SERVICE_CRIACAO = "6518c8e7-72a4-4796-bb09-2ebd252ef2d6"
ATIVOS = ["AGUARDANDO", "DATA_ENVIADA", "AGUARDANDO_DECISAO_RESPONSAVEL", "AGUARDANDO_CONSULTOR",
          "AGUARDANDO_CHAMADO_LIVRE", "EM_PROCESSAMENTO"]


def _recusar(msg):
    return {"ok": False, "resposta": {"ok": False, "erro": msg}}


def pedido_do_body(body: dict) -> str:
    a = re.findall(r"\d+", str(C.nn((body or {}).get("pedidoLider"), "")))
    return a[-1] if a else ""


# ===================================================================== Validar recomeço
def validar_recomeco(body: dict, linhas_brutas: list[dict]) -> dict:
    body = body or {}
    pedido = pedido_do_body(body)
    motivo = re.sub(r"\s+", " ", str(C.nn(body.get("motivo"), ""))).strip()[:300]
    nome = re.sub(r"[^\w .'\-]|_", "", str(C.nn(body.get("nomeContato"), "")))
    nome = re.sub(r"\s+", " ", nome).strip()[:60]
    tel = str(C.nn(body.get("novoTelefone"), "")).strip()
    aviso = str(C.nn(body.get("avisoContatoAntigo"), "")).replace("\r\n", "\n").strip()[:1000]

    if not pedido:
        return _recusar("Informe o número do pedido.")
    if len(motivo) < 5:
        return _recusar("Escreva o motivo do recomeço (mínimo 5 letras). Ele fica registrado no pedido.")
    linhas = [r for r in linhas_brutas if r and not r.get("error") and r.get("pedidoLider") is not None
              and str(r.get("pedidoLider")) != ""]
    if not linhas:
        return _recusar(f"Pedido 11-{pedido} não encontrado na AGUARDANDO_ENTREGA (a tabela guarda só os pedidos do dia).")
    if len(linhas) > 1:
        return _recusar(f"O pedido 11-{pedido} aparece {len(linhas)} vezes na AGUARDANDO_ENTREGA. Nada foi alterado; corrija a tabela antes.")
    linha = linhas[0]
    status = str(C.nn(linha.get("status"), ""))
    bruto = linha.get("dadosPedido")
    if isinstance(bruto, str):
        try:
            import json
            dados = json.loads(bruto)
        except ValueError:
            return _recusar(f"dadosPedido inválido no pedido 11-{pedido}. Nada foi alterado.")
    else:
        dados = C.js_or(bruto, {})
    if not isinstance(dados, dict):
        return _recusar(f"dadosPedido inválido no pedido 11-{pedido}. Nada foi alterado.")

    if status == "AGRUPADO" or C.js_truthy(dados.get("agrupadoEm")):
        ag = C.js_str(C.js_or(dados.get("agrupadoEm"), "?"))
        return _recusar(f"O pedido 11-{pedido} foi na mensagem única do pedido 11-{ag}. Recomece pelo pedido 11-{ag}.")
    if status == "OUTLET" or dados.get("outlet") is True:
        return _recusar(f"O pedido 11-{pedido} é outlet (confirmado sem contato). Não há conversa para recomeçar.")
    if status not in PODE:
        return _recusar(f"O pedido 11-{pedido} está com status {status or '(vazio)'}, que não permite recomeço. "
                        "Só pedidos que já têm mensagem pronta podem recomeçar.")
    if status == "CONCLUIDO" and body.get("confirmarConcluido") is not True:
        return _recusar(f"O pedido 11-{pedido} já está CONCLUIDO. Para recomeçar, marque a confirmação: o que já foi gravado "
                        "na intranet e na planilha NÃO é desfeito.")
    if not str(C.nn(dados.get("mensagem"), "")).strip():
        return _recusar(f"O pedido 11-{pedido} não tem mensagem de confirmação montada. Nada foi alterado.")

    phone_atual = C.js_or(linha.get("phone"), dados.get("phone"), None)
    contact_atual = C.js_or(linha.get("contactId"), dados.get("contactId"), None)
    service_atual = C.js_or(linha.get("serviceId"), dados.get("serviceId"), None)

    novo = None
    if tel:
        novo = C.normalizar_celular(tel)
        if not novo:
            return _recusar(f'O número "{tel}" não é um celular válido (DDD + 9 dígitos). Nada foi alterado.')
    modo = "NOVO_NUMERO" if novo and C.chave_tel(novo) != C.chave_tel(phone_atual) else "MESMO_NUMERO"

    if modo == "MESMO_NUMERO" and aviso:
        return _recusar("O aviso ao contato atual só vale quando o número muda. Informe o número novo ou apague o aviso.")
    if aviso and not C.js_truthy(contact_atual):
        return _recusar(f"O pedido 11-{pedido} não tem contato atual no Digisac para receber o aviso. Apague o aviso para seguir.")
    if modo == "MESMO_NUMERO":
        if status in SO_COM_NUMERO_NOVO:
            extra = " / Respostas tardias" if status == "PENDENTE_RESPOSTA_TARDIA" else ""
            return _recusar(f"O pedido 11-{pedido} ainda não foi enviado ({status}). Recomeçar sem trocar o número não muda nada: "
                            f"use a tela de Revisão{extra}.")
        if not C.js_truthy(contact_atual):
            return _recusar(f"O pedido 11-{pedido} não tem contato no Digisac. Informe o número para recomeçar.")

    tentativas = []
    if modo == "NOVO_NUMERO":
        ult8 = re.sub(r"\D", "", novo)[-8:]
        tentativas = [{"phoneBusca": f"%{ult8}", "serviceBusca": s, "chaveBusca": C.chave_tel(novo)} for s in SERVICES]

    cliente = C.js_or(linha.get("cliente"), dados.get("clienteLider"), "")
    doc_bruto = re.sub(r"\D", "", str(C.nn(dados.get("cpf"), "")))
    doc = C.js_or(C.normalizar_cpf("0" + doc_bruto) if len(doc_bruto) == 14 else C.normalizar_cpf(doc_bruto), doc_bruto)
    base = " - ".join(x for x in [doc, str(cliente).strip()] if x) or f"Contato pedido 11-{pedido}"
    internal = (f"{base}-({nome})" if nome else base)[:120]
    return {"ok": True, "modo": modo, "pedidoLider": str(linha.get("pedidoLider")), "idLinha": linha.get("id"),
            "statusAnterior": status, "linha": linha, "dados": dados, "motivo": motivo, "nomeContato": nome,
            "novoPhone": novo, "chaveNovo": C.chave_tel(novo) if novo else None,
            "phoneAtual": phone_atual, "contactIdAtual": contact_atual, "serviceIdAtual": service_atual,
            "tentativas": tentativas, "internalName": internal, "avisoContatoAntigo": aviso,
            "serviceCriacao": SERVICE_CRIACAO}


# ===================================================================== Avaliar busca / criação / contato definido
def avaliar_busca(v: dict, res: list[dict]) -> dict:
    if len(res) != len(v["tentativas"]) or any(not r or r.get("error") or not isinstance(r.get("data"), list) for r in res):
        return {"ok": False, "acao": "ERRO", "resposta": {"ok": False, "erro": "Falha ao pesquisar o número no Digisac. "
                                                                              "Nada foi alterado; tente de novo em instantes."}}
    dig = re.sub(r"\D", "", str(v["novoPhone"]))
    cand = [c for r in res for c in r["data"]
            if c and C.js_truthy(c.get("id")) and C.chave_tel(((c.get("data") or {}).get("number"))) == v["chaveNovo"]]

    def chave(c):
        ex = 0 if re.sub(r"\D", "", str(C.nn((c.get("data") or {}).get("number"), ""))) == dig else 1
        s = SERVICES.index(c.get("serviceId")) if c.get("serviceId") in SERVICES else 99
        return (ex, s)
    cand.sort(key=chave)
    if not cand:
        return {**v, "acao": "CRIAR"}
    c = cand[0]
    return {**v, "acao": "USAR", "ok": True, "contactIdNovo": c["id"], "serviceIdNovo": C.js_or(c.get("serviceId"), None),
            "phoneNovo": C.js_or(C.normalizar_celular((c.get("data") or {}).get("number")), v["novoPhone"]),
            "statusContato": "ENCONTRADO", "nomeDigisac": C.js_or(c.get("internalName"), c.get("name"), None),
            "qtdEncontrados": len(cand)}


def avaliar_criacao(v: dict, criado: dict) -> dict:
    if not criado or C.js_truthy(criado.get("error")) or not C.js_truthy(criado.get("id")):
        det = C.dumps(C.nn((criado or {}).get("error"), criado, None))[:300]
        return _recusar("Não foi possível salvar o número no Digisac. Nada foi alterado no pedido. Detalhe: " + det)
    return {**v, "ok": True, "contactIdNovo": criado["id"], "serviceIdNovo": C.js_or(criado.get("serviceId"), v["serviceCriacao"]),
            "phoneNovo": v["novoPhone"], "statusContato": "CRIADO",
            "nomeDigisac": C.js_or(criado.get("internalName"), criado.get("name"), v["internalName"])}


def contato_definido(v: dict, c: dict | None) -> dict:
    if v["modo"] == "MESMO_NUMERO":
        return {**v, "contactIdNovo": v["contactIdAtual"], "serviceIdNovo": v["serviceIdAtual"], "phoneNovo": v["phoneAtual"],
                "statusContato": "MESMO_CONTATO"}
    if not c or not C.js_truthy(c.get("ok")) or not C.js_truthy(c.get("contactIdNovo")):
        return _recusar("Contato do Digisac não definido. Nada foi alterado.")
    return c


# ===================================================================== Montar recomeço
def montar_recomeco(v: dict, outros: list[dict], agora_ms: int | None = None) -> dict:
    if not v or not C.js_truthy(v.get("ok")) or not C.js_truthy(v.get("contactIdNovo")):
        return _recusar("Contato do Digisac não definido. Nada foi alterado.")
    if any(o and C.js_truthy(o.get("error")) for o in outros):
        return _recusar("Falha ao conferir outros pedidos deste contato. Nada foi alterado; tente de novo.")
    agora_ms = agora_ms if agora_ms is not None else C.agora_ms()
    pg = v["dados"].get("pedidosGrupo")
    grupo = C.unicos([str(v["pedidoLider"]), *[C.js_str(g["pedidoLider"]) if isinstance(g, dict) and "pedidoLider" in g
                                               else "undefined" for g in (pg if isinstance(pg, list) else [])]])
    conflito = [o for o in outros if o and o.get("pedidoLider") is not None and str(o["pedidoLider"]) not in grupo and
                (o.get("status") in ATIVOS or (o.get("status") == "CONCLUIDO" and C.js_truthy(o.get("vigiaAte"))
                                               and C.iso_ms(o.get("vigiaAte")) > agora_ms))]
    if conflito:
        lista = ", ".join(f"11-{o['pedidoLider']} ({C.js_str(o.get('status'))})" for o in conflito)
        return _recusar(f"Este número já está em atendimento no pedido {lista}. Nada foi alterado. Termine aquele atendimento "
                        "antes, para a IA não misturar os pedidos.")
    agora_iso = C.iso_utc_de_ms(agora_ms)
    l = v["linha"]
    d = dict(v["dados"])
    registro = {"em": agora_iso, "modo": v["modo"], "motivo": v["motivo"], "statusAnterior": v["statusAnterior"],
                "categoriaAnterior": C.js_or(l.get("categoria"), None), "resumoIAAnterior": C.js_or(l.get("resumoIA"), None),
                "respostaAnterior": C.js_or(l.get("resposta"), None), "enviadoEmAnterior": C.js_or(l.get("enviadoEm"), None),
                "respondidoEmAnterior": C.js_or(l.get("respondidoEm"), None),
                "chatConsultorAnterior": C.js_or(l.get("chatConsultor"), None),
                "contactIdAnterior": v["contactIdAtual"], "phoneAnterior": v["phoneAtual"],
                "contactIdNovo": v["contactIdNovo"], "phoneNovo": v["phoneNovo"], "statusContato": v["statusContato"],
                "nomeContato": C.js_or(v.get("nomeContato"), None), "nomeDigisac": C.js_or(v.get("nomeDigisac"), None)}
    d["recomecos"] = [*(d["recomecos"] if isinstance(d.get("recomecos"), list) else []), registro]
    d["contactId"] = v["contactIdNovo"]
    d["serviceId"] = v["serviceIdNovo"]
    d["phone"] = v["phoneNovo"]
    if v["modo"] == "NOVO_NUMERO":
        d["statusBusca"] = v["statusContato"]
        d["contatoAlternativo"] = {"nome": C.js_or(v.get("nomeContato"), None), "phone": v["phoneNovo"], "definidoEm": agora_iso}
    if v.get("nomeContato"):
        primeiro = v["nomeContato"].split(" ")[0]
        nome = primeiro[:1].upper() + primeiro[1:].lower()
        m = C.js_str(d.get("mensagem"))
        nova = re.sub(r"^Olá(, [^!\n]{1,60})?!", lambda _: f"Olá, {nome}!", m, count=1)
        if nova != m:
            d["mensagemAntesRecomeco"] = C.nn(d.get("mensagemAntesRecomeco"), m)
            d["mensagem"] = nova
    for k in ("respostaTardia", "respostaTardiaDecisao", "lembreteConfirmacaoEm", "lembreteConfirmacaoTexto",
              "chamadoEspera", "videoEnvio"):
        d.pop(k, None)
    acomp = [p for p in grupo if p != str(v["pedidoLider"])]
    quem = f"{v['nomeContato']} " if v.get("nomeContato") else ""
    ped = v["pedidoLider"]
    if v["modo"] == "NOVO_NUMERO":
        msg = (f"Pedido 11-{ped} recomeçado com o número {quem}({C.js_str(v['phoneNovo'])}). Contato "
               f"{'criado' if v['statusContato'] == 'CRIADO' else 'encontrado'} no Digisac.")
    else:
        msg = f"Pedido 11-{ped} recomeçado com o mesmo número."
    msg += " Ele voltou para a Revisão de Envio: confira a mensagem e clique em Enviar."
    if acomp:
        msg += f" Os pedidos {', '.join('11-' + p for p in acomp)} da mensagem única acompanham."
    if v["statusAnterior"] == "CONCLUIDO":
        msg += " Atenção: o que já foi gravado na intranet e na planilha não foi desfeito."
    aviso = ({"contactId": v["contactIdAtual"], "texto": v["avisoContatoAntigo"]}
             if v["modo"] == "NOVO_NUMERO" and v.get("avisoContatoAntigo") and C.js_truthy(v.get("contactIdAtual"))
             and str(v["contactIdAtual"]) != str(v["contactIdNovo"]) else None)
    return {"ok": True, "pedidoLider": str(ped), "statusAnterior": v["statusAnterior"], "modo": v["modo"],
            "contactId": v["contactIdNovo"], "serviceId": v["serviceIdNovo"], "phone": v["phoneNovo"],
            "dadosPedido": C.dumps(d), "marcaEm": agora_iso, "acompanhantes": acomp, "avisoAntigo": aviso,
            "conversa": {"contactId": v["contactIdNovo"], "messageId": f"recomeco-{ped}-{agora_ms}", "papel": "RECOMECO",
                         "texto": f"[Atendimento do pedido 11-{ped} recomeçado pelo consultor. Motivo: {v['motivo']}]",
                         "ts": agora_ms},
            "resposta": {"ok": True, "pedidoLider": str(ped), "modo": v["modo"], "statusContato": v["statusContato"],
                         "phone": v["phoneNovo"], "contactId": v["contactIdNovo"], "mensagem": msg}}


def conferir_gravacao(m: dict, linhas: list[dict]) -> dict:
    ls = [r for r in linhas if r and not r.get("error") and str(C.nn(r.get("pedidoLider"), "")) == m["pedidoLider"]]
    ok = (len(ls) == 1 and ls[0].get("status") == "PENDENTE_REVISAO" and C.js_str(ls[0].get("contactId")) == C.js_str(m["contactId"])
          and m["marcaEm"] in str(C.nn(ls[0].get("dadosPedido"), "")))
    if not ok:
        return _recusar(f"Não consegui confirmar a gravação do pedido 11-{m['pedidoLider']}. O status pode ter mudado durante o "
                        "recomeço (ex.: o cliente respondeu agora). Atualize o painel e confira o pedido antes de tentar de novo.")
    return {**m, "ok": True}


def resultado_aviso(m: dict, r: dict, agora_ms: int | None = None) -> dict:
    r = r or {}
    agora_ms = agora_ms if agora_ms is not None else C.agora_ms()
    enviado = not C.js_truthy(r.get("error")) and C.js_truthy(C.js_or(r.get("id"), r.get("messageId")))
    e = r.get("error")
    motivo = None if enviado else str(C.js_or(e.get("message") if isinstance(e, dict) else None, e, r.get("message"),
                                              "resposta sem id"))[:200]
    return {"enviado": enviado, "motivo": motivo, "contactId": m["avisoAntigo"]["contactId"],
            "messageId": "recomeco-aviso-" + C.js_str(C.js_or(r.get("id"), agora_ms)), "papel": "BOT",
            "texto": m["avisoAntigo"]["texto"], "ts": agora_ms}


def resposta_final(r: dict | None, conferir: dict | None, conv: dict | None, aviso: dict | None) -> dict:
    """Nó 'Resposta recomeço'. conv=None: nó não executou; aviso=None: sem aviso pedido."""
    if not r and conferir:
        r = conferir.get("resposta")
    if not r:
        r = {"ok": False, "erro": "Resposta não montada."}
    if r.get("ok"):
        av = None
        if conv is not None and (not conv or conv.get("error")):
            av = ("O pedido foi recomeçado, mas a marca de recomeço não foi gravada na MENSAGENS_CLIENTE: a IA ainda pode ver "
                  "a conversa anterior deste número.")
        if av:
            r = {**r, "aviso": av}
        if aviso is not None:
            if aviso.get("enviado"):
                r = {**r, "mensagem": r["mensagem"] + " Aviso enviado ao contato anterior."}
            else:
                r = {**r, "aviso": " ".join(x for x in [r.get("aviso"),
                     "O pedido foi recomeçado, mas o aviso ao contato anterior NÃO foi enviado ("
                     + C.js_str(C.js_or(aviso.get("motivo"), "erro no Digisac")) + "). Avise o cliente pelo Digisac."] if x)}
    return r


# ===================================================================== fluxo
@gatilho("central-lider-recomecar")
def recomecar_pedido(entrada, req):
    body = entrada.get("body") or {}
    ped = pedido_do_body(body) or "__nenhum__"
    v = validar_recomeco(body, T.get("AGUARDANDO_ENTREGA", {"pedidoLider": ped}))
    if v.get("ok") is not True:
        return resposta_final(v.get("resposta"), None, None, None), 200

    if v["modo"] == "NOVO_NUMERO":
        res = [digisac.buscar_contatos(t["phoneBusca"], t["serviceBusca"]) for t in v["tentativas"]]
        b = avaliar_busca(v, res)
        if b.get("acao") == "CRIAR":
            b = avaliar_criacao(b, digisac.criar_contato(b["internalName"], b["novoPhone"], SERVICE_CRIACAO))
        if b.get("ok") is not True:
            return resposta_final(b.get("resposta"), None, None, None), 200
        c = contato_definido(v, b)
    else:
        c = contato_definido(v, None)

    try:
        outros = T.get("AGUARDANDO_ENTREGA", {"contactId": C.js_or(c.get("contactIdNovo"), "__sem_contato__")})
    except Exception as exc:  # noqa: BLE001
        outros = [{"error": str(exc)}]
    m = montar_recomeco(c, outros)
    if m.get("ok") is not True:
        return resposta_final(m.get("resposta"), None, None, None), 200

    T.update("AGUARDANDO_ENTREGA", {"pedidoLider": m["pedidoLider"], "status": m["statusAnterior"]}, {
        "status": "PENDENTE_REVISAO", "contactId": m["contactId"], "serviceId": m["serviceId"], "phone": m["phone"],
        "categoria": "", "resposta": "", "respostaData": "", "resumoIA": "", "respondidoEm": "", "enviadoEm": "",
        "vigiaAte": "", "chatConsultor": "", "dadosPedido": m["dadosPedido"]})
    try:
        relidas = T.get("AGUARDANDO_ENTREGA", {"pedidoLider": m["pedidoLider"]})
    except Exception as exc:  # noqa: BLE001
        relidas = [{"error": str(exc)}]
    cf = conferir_gravacao(m, relidas)
    if cf.get("ok") is not True:
        return resposta_final(cf.get("resposta"), None, None, None), 200

    try:
        conv = T.insert("MENSAGENS_CLIENTE", {**cf["conversa"], "papel": "RECOMECO", "recebidoEm": C.agora_iso()})
    except Exception as exc:  # noqa: BLE001
        log.exception("Marcar recomeço na conversa")
        conv = {"error": str(exc)}

    aviso = None
    if m.get("avisoAntigo") and m["avisoAntigo"].get("texto"):
        r = digisac.enviar_mensagem(m["avisoAntigo"]["contactId"], m["avisoAntigo"]["texto"])
        aviso = resultado_aviso(m, r)
        if aviso["enviado"] is True:
            try:
                T.insert("MENSAGENS_CLIENTE", {k: aviso[k] for k in ("contactId", "messageId", "texto", "ts")} |
                         {"papel": "BOT", "recebidoEm": C.agora_iso()})
            except Exception:  # noqa: BLE001
                log.exception("Registrar aviso na conversa")

    for p in cf.get("acompanhantes") or []:
        try:
            T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p, "status": "AGRUPADO"},
                     {"contactId": cf["contactId"], "serviceId": cf["serviceId"], "phone": cf["phone"]})
        except Exception:  # noqa: BLE001
            log.exception("Atualizar contato (pedidos do grupo)")
    return resposta_final(None, cf, conv, aviso), 200
