"""Webhook 'central-lider-consultor' — tela Consultas da IA (v28).

Ações do painel: RESPONDER (IA reescreve a orientação e envia ao cliente), REGISTRAR (grava o resultado
do contato na planilha/intranet e fecha o card) e TRANSFERIR (transfere o chamado ao responsável).
As funções puras abaixo são traduções 1:1 dos nós Code; o handler segue a ordem dos nós.
"""
import logging
import re
import threading
from datetime import date, timedelta

from .. import comum as C
from .. import tabelas as T
from ..integracoes import digisac, email, gemini, planilha
from ..integracoes.intranet import Intranet, url_com_query
from . import f2_logica as L
from . import gatilho
from . import prompts as P
from .f1_revisao import DEPARTAMENTO_CENTRAL, listar_usuarios_todos

log = logging.getLogger("central")
EMAIL_AVISOS = "mateus.oliveira@lider.design"
INTRANET_FIXA = "http://192.168.0.6"   # a v28 monta a URL de alteração com o endereço fixo
RESULTADOS = {"CONFIRMADO": "Cliente confirmou a data de entrega",
              "NAO_CONCORDA": "Cliente não concorda com a data de entrega",
              "ADIADO": "Cliente adiou a entrega"}
CATEGORIA = {"CONFIRMADO": "ACEITA", "NAO_CONCORDA": "NAO_ACEITA", "ADIADO": "PEDE_ADIAR"}


def _data_js(a: int, m: int, d: int) -> date:
    """new Date(a, m - 1, d) com o 'transbordo' do JS (31/02 vira 03/03)."""
    base = date(a + (m - 1) // 12, (m - 1) % 12 + 1, 1)
    return base + timedelta(days=d - 1)


def _parse_data(s):
    s = str("" if s is None else s).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return _data_js(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        return _data_js(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _chat(valor) -> list:
    c = C.loads(C.js_or(valor, "[]"), None)
    return c if isinstance(c, list) else []


def _dp(valor) -> dict:
    d = C.loads(C.js_or(valor, "{}"), {})
    return d if isinstance(d, dict) else {}


def _campo(m, k) -> str:
    return C.js_str(m[k]) if isinstance(m, dict) and k in m else "undefined"


# ===================================================================== Processar ação do consultor
def processar_acao(body: dict, row: dict) -> dict:
    body = body or {}
    row = row or {}
    acao = str(body.get("acao") or "").upper()
    texto = str(body.get("texto") or "").strip()
    resultado = str(body.get("resultado") or "").upper().strip()
    if acao == "TRANSFERIR":
        resultado = ""
    data_adiamento = _parse_data(body.get("dataAdiamento")) if resultado == "ADIADO" else None
    hoje = C.agora().date()

    chat = _chat(row.get("chatConsultor"))
    ja_registrado = any(isinstance(m, dict) and m.get("tipo") == "resultado" for m in chat)
    dp_row = _dp(row.get("dadosPedido"))
    primeira = str(C.js_or(row.get("tipoMensagem"), dp_row.get("tipoMensagem"), "")) == "PRIMEIRA_CONFIRMACAO"
    status = row.get("status")

    erro = ""
    if not C.js_truthy(row.get("id")):
        erro = "Consulta não encontrada."
    elif acao not in ("RESPONDER", "REGISTRAR", "TRANSFERIR"):
        erro = "Ação inválida."
    elif acao != "REGISTRAR" and status != "AGUARDANDO_CONSULTOR":
        erro = "Esta consulta já foi tratada."
    elif acao == "REGISTRAR" and status not in ("AGUARDANDO_CONSULTOR", "CONCLUIDO", "PENDENTE_RESPOSTA_TARDIA"):
        erro = f"Não é possível registrar resultado com o pedido em {C.js_str(status) if 'status' in row else 'undefined'}."
    elif acao == "RESPONDER" and not texto:
        erro = "Escreva a orientação para o cliente."
    elif acao == "REGISTRAR" and not resultado:
        erro = "Escolha o resultado do contato."
    elif resultado and resultado not in RESULTADOS:
        erro = "Resultado inválido."
    elif resultado == "ADIADO" and primeira:
        erro = "1ª confirmação de planejados não tem data de entrega para adiar. Registre como Confirmado ou transfira."
    elif resultado == "ADIADO" and not data_adiamento:
        erro = "Informe a nova data de entrega."
    elif resultado == "ADIADO" and data_adiamento <= hoje:
        erro = "A nova data precisa ser futura."

    ts = C.agora_iso_utc()
    pular = bool(resultado and (C.js_truthy(dp_row.get("registroContato")) or ja_registrado))
    if not erro:
        if acao == "RESPONDER":
            chat.append({"role": "consultor", "texto": texto, "ts": ts})
        if acao == "TRANSFERIR":
            chat.append({"role": "consultor", "texto": f"Solicitou a transferência: {texto}" if texto
                         else "Solicitou a transferência do atendimento.", "ts": ts})
        if resultado:
            chat.append({"role": "consultor", "tipo": "resultado", "resultado": resultado,
                         "texto": f"Resultado registrado: {RESULTADOS[resultado]}"
                                  f"{' para ' + C.fmt_br(data_adiamento) if data_adiamento else ''}."
                                  f"{' (Contato já registrado na intranet antes: observação não gravada de novo.)' if pular else ''}",
                         "ts": ts})
    resumo_chat = " | ".join(f"{_campo(m, 'role')}: {_campo(m, 'texto')}" for m in chat[-4:])
    tardia = status == "PENDENTE_RESPOSTA_TARDIA"
    saida = {**row, "acao": acao, "resultado": resultado, "statusAnterior": status, "pularIntranet": pular,
             "origemTardia": tardia,
             "semConfPedidoTardia": C.js_str(C.js_or((dp_row.get("respostaTardia") or {}).get("pedidoLiderRegistro")
                                                     if isinstance(dp_row.get("respostaTardia"), dict) else None,
                                                     row.get("pedidoLider"), "")) if tardia else "",
             "dataAdiamentoBR": C.fmt_br(data_adiamento) if data_adiamento else None,
             "textoConsultor": texto, "chatConsultor": C.dumps(chat), "resumoChat": resumo_chat, "erro": erro}
    if "status" not in row:
        saida.pop("statusAnterior")
    return saida


# ===================================================================== Preparar resultado (consultor)
def preparar_resultado(r: dict) -> list[dict]:
    dp = _dp(C.nn(r.get("dadosPedido"), "{}"))

    def montar(fonte, usar_mensagem):
        pedido = str(C.nn(fonte.get("pedidoLider"), "")).strip()
        cliente = str(C.nn(fonte.get("clienteLider"), dp.get("Cliente"), r.get("cliente"), "")).strip()
        ent = fonte.get("entregas")
        datas = [e.get("data") for e in ent if isinstance(e, dict) and C.js_truthy(e.get("data"))] if isinstance(ent, list) else []
        if not datas and usar_mensagem:
            datas = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", str(C.nn(r.get("mensagem"), "")))
        datas = C.unicos(datas)
        if not usar_mensagem:
            datas.sort(key=C.data_num)
        tipo = C.js_or(r.get("tipoMensagem"), dp.get("tipoMensagem")) if usar_mensagem else fonte.get("tipoMensagem")
        primeira = str(C.js_or(tipo, "")) == "PRIMEIRA_CONFIRMACAO"
        if primeira and not datas:
            datas = [C.js_or(fonte.get("dataSistema"), fonte.get("entregaLider"), "01/12/2040")]
        sheet = str(C.nn(fonte.get("Pedido"), fonte.get("pedidoOriginal"), f"11-{pedido}")).strip()
        return {"id": r.get("id"), "pedidoLider": pedido, "pedidoSheet": sheet, "contactId": r.get("contactId"),
                "clienteIntranet": C.sem_acento(cliente).upper(), "resultado": r.get("resultado"),
                "categoria": CATEGORIA.get(r.get("resultado")), "datasInformadas": " E ".join(datas),
                "dataPrevistaBR": datas[0] if datas else None, "dataPrevistaISO": C.br_para_iso(datas[0] if datas else ""),
                "dataAdiamentoBR": r.get("dataAdiamentoBR"), "dataAdiamentoISO": C.br_para_iso(r.get("dataAdiamentoBR")),
                "statusAnterior": r.get("statusAnterior"), "primeiraConfirmacao": primeira,
                "pularIntranet": bool(r.get("pularIntranet")), "vigiaAteAnterior": C.js_or(r.get("vigiaAte"), "")}

    grupo = dp.get("pedidosGrupo")
    if isinstance(grupo, list) and len(grupo) > 1:
        return [{**montar(m, False), "pedidoPrincipal": str(C.nn(r.get("pedidoLider"), "")), "qtdPedidosGrupo": len(grupo)}
                for m in grupo]
    solo = {"pedidoLider": C.nn(r.get("pedidoLider"), dp.get("pedidoLider")),
            "clienteLider": C.nn(dp.get("clienteLider"), dp.get("Cliente"), r.get("cliente")),
            "entregas": dp.get("entregas"), "dataSistema": dp.get("dataSistema"), "entregaLider": dp.get("entregaLider"),
            "Pedido": dp.get("Pedido"), "pedidoOriginal": dp.get("pedidoOriginal")}
    return [montar(solo, True)]


# ===================================================================== Montar resposta ao cliente
def montar_resposta_cliente(base: dict, out_ia: dict) -> dict:
    out_ia = out_ia or {}
    ia = str(C.nn(out_ia.get("text"), out_ia.get("output"), "")).strip()
    ia = re.sub(r'^["“”]+|["“”]+$', "", ia)
    msg = ia or base.get("textoConsultor")
    chat = _chat(base.get("chatConsultor"))
    chat.append({"role": "ia", "tipo": "envio", "texto": "Mensagem enviada ao cliente: " + C.js_str(msg), "ts": C.agora_iso_utc()})
    return {**base, "respostaCliente": msg, "chatConsultor": C.dumps(chat)}


# ===================================================================== Montar URL (consultor)
def montar_url_consultor(html, p: dict, base: str = INTRANET_FIXA) -> dict:
    html = str(C.nn(html, ""))
    itens = []
    for tag in re.findall(r"<input\b[^>]*>", html, re.I):
        if not re.search(r"name\s*=\s*[\"']?item\[\][\"']?", tag, re.I):
            continue
        v = re.search(r"value\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", tag, re.I)
        if v:
            itens.append(C.nn(v.group(1), v.group(2), v.group(3), "").replace("&amp;", "&"))
    unicos = C.unicos(itens)
    if not unicos:
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html)).strip()
        return {"urlAlterar": None, "pedidoLider": p.get("pedidoLider"),
                "erroAdiamento": f"Itens do formulário não encontrados. Resposta: {txt[:200]}"}
    obs = (f"ADIAMENTO SOLICITADO PELO CLIENTE (REGISTRADO PELO CONSULTOR): DATA ALTERADA DE "
           f"{C.js_or(p.get('dataPrevistaBR'), '-')} PARA {C.js_str(p.get('dataAdiamentoBR'))}.")
    params = [("data", p.get("dataAdiamentoISO")), ("cod_empresa", "11"), ("pedido", p.get("pedidoLider")),
              ("motivo", "SOLICITACAO DO CLIENTE"), ("agendamento", ""), ("observacao", obs), ("opcao[]", "A"),
              *[("item[]", i) for i in unicos]]
    return {"urlAlterar": url_com_query(f"{base}/vdp/altera_data_entrega2.php", [(k, C.js_str(v)) for k, v in params]),
            "qtdItens": len(unicos), "pedidoLider": p.get("pedidoLider")}


# ===================================================================== Montar observação (consultor)
def montar_observacao(lista: list[dict], entradas: list[dict], urls: list[dict]) -> list[dict]:
    ts = C.carimbo_br()
    saida = []
    for i, p in enumerate(lista):
        alteracao_ok, erro_adi = None, None
        if p.get("resultado") == "ADIADO":
            montar = urls[i] if i < len(urls) and urls[i] else {}
            resp = (entradas[i] if i < len(entradas) else None) or {}
            alteracao_ok = bool(montar.get("urlAlterar")) and not C.js_truthy(resp.get("error"))
            if not alteracao_ok:
                e = resp.get("error")
                msg_e = e.get("message") if isinstance(e, dict) else None
                erro_adi = C.js_or(montar.get("erroAdiamento"),
                                   C.js_str(C.js_or(msg_e, e, "falha ao alterar a data na intranet")))
        obs, dat = "", p.get("dataPrevistaISO")
        res = p.get("resultado")
        if p.get("primeiraConfirmacao") and res == "CONFIRMADO":
            obs = ("CLIENTE CONTATADO VIA WHATSAPP (1A CONFIRMACAO - PLANEJADOS) E CONFIRMOU O RECEBIMENTO DA MENSAGEM. "
                   "PRAZO DE ENTREGA SERA INFORMADO APOS A POSTAGEM DO PROJETO. (ATENDIMENTO PELO CONSULTOR)")
        elif res == "CONFIRMADO":
            obs = f"CLIENTE CONTATADO VIA WHATSAPP E CONFIRMOU A DATA DE ENTREGA {C.js_str(p.get('datasInformadas'))}. (ATENDIMENTO PELO CONSULTOR)"
        elif res == "NAO_CONCORDA":
            obs = f"CLIENTE CONTATADO VIA WHATSAPP E NAO ACEITA A DATA DE ENTREGA {C.js_str(p.get('datasInformadas'))}. (ATENDIMENTO PELO CONSULTOR)"
        elif res == "ADIADO" and alteracao_ok:
            dat = p.get("dataAdiamentoISO")
            obs = (f"CLIENTE CONTATADO VIA WHATSAPP E SOLICITOU ADIAMENTO DA ENTREGA DE "
                   f"{C.js_str(C.js_or(p.get('dataPrevistaBR'), p.get('datasInformadas')))} PARA {C.js_str(p.get('dataAdiamentoBR'))}. "
                   "PRAZO ALTERADO NO SISTEMA. (ATENDIMENTO PELO CONSULTOR)")
        elif res == "ADIADO":
            obs = (f"CLIENTE CONTATADO VIA WHATSAPP E SOLICITOU ADIAMENTO DA ENTREGA PARA {C.js_str(p.get('dataAdiamentoBR'))}. "
                   "ALTERACAO AUTOMATICA FALHOU: AJUSTAR O PRAZO MANUALMENTE.")
        sheet = {"CONFIRMADO": ["SIM", "CONFIRMADO"], "NAO_CONCORDA": ["SIM", "CLIENTE NÃO CONCORDA"],
                 "ADIADO": ["SIM", "CONFIRMADO"] if alteracao_ok else ["SIM", "ADIAR MANUALMENTE (FALHA INTRANET)"]
                 }.get(res) or ["", ""]
        saida.append({**p, "alteracaoOk": alteracao_ok, "erroAdiamento": erro_adi, "observacao": C.sem_acento(obs).upper(),
                      "datEntrega": dat,
                      "temObservacao": not p.get("pularIntranet") and bool(obs and C.js_truthy(p.get("pedidoLider")) and C.js_truthy(dat)),
                      "sheetG": sheet[0], "sheetH": sheet[1], "sheetI": ts})
    return saida


# ===================================================================== Localizar linha (consultor)
def localizar_linha(regs: list[dict], linhas: list[dict]) -> list[dict]:
    linhas = [r for r in linhas if r and r.get("row_number") is not None]
    saida = []
    for p in regs:
        alvo = C.n_ped(p.get("pedidoSheet")) or C.n_ped(p.get("pedidoLider"))
        achadas = [r for r in linhas if C.n_ped(r.get("Pedido")) == alvo]
        if len(achadas) > 1:
            ex = [r for r in achadas if C.js_str(r.get("Pedido")).strip() == p.get("pedidoSheet")]
            if ex:
                achadas = ex
        saida.append({**p, "row_number": achadas[0]["row_number"] if achadas else None})
    return saida


# ===================================================================== Resumo do registro (consultor)
def resumo_registro(regs: list[dict], gravs: list[dict], obs_int: list[dict], processar: dict,
                    montar_resposta: dict | None) -> dict:
    p = regs[0]
    gi = oi = 0
    por = []
    for r in regs:
        if not C.js_truthy(r.get("row_number")):
            pl = "PEDIDO NÃO ENCONTRADO NA PLANILHA"
        else:
            g = gravs[gi] if gi < len(gravs) else None
            gi += 1
            pl = "OK" if g is not None and not C.js_truthy(g.get("error")) else "FALHOU"
        if r.get("pularIntranet"):
            it = "JÁ REGISTRADA ANTES (NÃO GRAVADA DE NOVO)"
        elif not r.get("temObservacao"):
            it = "SEM OBSERVAÇÃO"
        else:
            o = obs_int[oi] if oi < len(obs_int) else None
            oi += 1
            it = "OK" if o is not None and not C.js_truthy(o.get("error")) else "FALHOU"
        por.append({"r": r, "planilha": pl, "intranet": it})
    varios = len(por) > 1

    def juntar(campo):
        vals = C.unicos(x[campo] for x in por)
        if not varios or len(vals) == 1:
            return vals[0]
        return "; ".join(f"{C.js_str(x['r'].get('pedidoLider'))}: {x[campo]}" for x in por)
    planilha_txt, intranet_txt = juntar("planilha"), juntar("intranet")
    alteracao_ok = all(x["r"].get("alteracaoOk") for x in por) if varios else p.get("alteracaoOk")
    pref = lambda x: f"Pedido {C.js_str(x['r'].get('pedidoLider'))} — " if varios else ""  # noqa: E731

    avisos = []
    avisos += [f"{pref(x)}Planilha: {x['planilha'].lower()}" for x in por if x["planilha"] != "OK"]
    avisos += [f"{pref(x)}Observação na intranet falhou" for x in por if x["intranet"] == "FALHOU"]
    avisos += [f"{pref(x)}Intranet NÃO preenchida (pedido sem data de entrega). Lance o aviso manualmente." for x in por
               if x["intranet"] == "SEM OBSERVAÇÃO" and C.js_truthy(x["r"].get("resultado"))]
    avisos += [f"{pref(x)}Data NÃO alterada na intranet ({C.js_str(x['r'].get('erroAdiamento'))}). Altere manualmente." for x in por
               if x["r"].get("resultado") == "ADIADO" and not x["r"].get("alteracaoOk")]

    base = montar_resposta if montar_resposta is not None else processar
    chat = _chat(base.get("chatConsultor"))
    texto = (f"Registro concluído{f' ({len(por)} pedidos: ' + ', '.join(C.js_str(x['r'].get('pedidoLider')) for x in por) + ')' if varios else ''}"
             f". Planilha: {planilha_txt}. Intranet: {intranet_txt}"
             f"{('. Data: ' + ('alterada para ' + C.js_str(p.get('dataAdiamentoBR')) if alteracao_ok else 'NÃO alterada')) if p.get('resultado') == 'ADIADO' else ''}.")
    chat.append({"role": "ia", "tipo": "registro", "texto": texto, "ts": C.agora_iso_utc()})

    st = p.get("statusAnterior")
    if st == "AGUARDANDO_CONSULTOR":
        vigia = C.iso_local_mais(2 if montar_resposta is not None else 1)
    else:
        vigia = "" if st == "PENDENTE_RESPOSTA_TARDIA" else p.get("vigiaAteAnterior")
    resumo = {"CONFIRMADO": "Consultor registrou (resposta tardia): cliente confirmou a data" if st == "PENDENTE_RESPOSTA_TARDIA"
              else "Consultor registrou: cliente confirmou a data",
              "NAO_CONCORDA": "Consultor registrou: cliente não concorda com a data",
              "ADIADO": f"Consultor registrou: adiamento para {C.js_str(p.get('dataAdiamentoBR'))}{'' if alteracao_ok else ' (alterar manualmente)'}"}
    pedido_base = C.js_or(p.get("pedidoPrincipal"), p.get("pedidoLider")) if varios else p.get("pedidoLider")
    dp_novo = _dp(processar.get("dadosPedido"))
    if C.js_truthy(p.get("resultado")) and not C.js_truthy(dp_novo.get("registroContato")):
        res = p.get("resultado")
        dp_novo["registroContato"] = {
            "em": C.agora_iso_utc(), "origem": "CONSULTOR", "resultado": res,
            "dataEntrega": (p.get("dataAdiamentoBR") if alteracao_ok else "") if res == "ADIADO" else C.js_or(p.get("dataPrevistaBR"), ""),
            "pedidos": [C.js_str(x["r"].get("pedidoLider")) for x in por]}
    return {**p, "pedidoLider": pedido_base, "alteracaoOk": alteracao_ok, "dadosPedidoNovo": C.dumps(dp_novo),
            "planilha": planilha_txt, "intranet": intranet_txt, "avisos": avisos, "chatConsultor": C.dumps(chat),
            "vigiaAte": vigia,
            "pedidosRegistrados": [{"pedidoLider": x["r"].get("pedidoLider"), "planilha": x["planilha"], "intranet": x["intranet"],
                                    "alteracaoOk": x["r"].get("alteracaoOk")} for x in por],
            "resumoIA": " | ".join(v for v in [str(C.js_or(base.get("resumoIA"), "")).strip(), resumo.get(p.get("resultado"))]
                                   if C.js_truthy(v))}


# ===================================================================== aprendizado (base de conhecimento)
def preparar_aprendizado(b: dict, base: list[dict]) -> dict | None:
    atual = []
    for m in _chat(b.get("chatConsultor")):
        if m.get("role") == "ia" and m.get("tipo") == "envio":
            atual = []
        elif m.get("role") == "cliente":
            atual.append(str(C.js_or(m.get("texto"), "")))
    pergunta = " / ".join(atual).strip()
    orientacao = str(C.js_or(b.get("textoConsultor"), "")).strip()
    if not pergunta or not orientacao or b.get("acao") != "RESPONDER":
        return None
    texto_base, _ = L.montar_baseTexto(base)
    return {"perguntaCliente": pergunta, "orientacao": orientacao,
            "respostaEnviada": str(C.js_or(b.get("respostaCliente"), "")), "baseTexto": texto_base}


def interpretar_aprendizado(out: dict, base: list[dict]) -> dict | None:
    bruto = str(C.nn(out.get("text"), out.get("output"), "")).strip()
    r = C.loads(re.sub(r"```json|```", "", bruto).strip(), None)
    if not isinstance(r, dict):
        return None
    pergunta = str(C.nn(r.get("pergunta"), "")).strip()
    resposta = str(C.nn(r.get("resposta"), "")).strip()
    if r.get("generalizavel") is not True or not pergunta or not resposta:
        return None
    lista = [x for x in base if x and x.get("id") is not None]
    ex = next((x for x in lista if str(x["id"]) == C.js_str(r.get("idExistente"))), None) if r.get("idExistente") is not None else None
    return {"pergunta": pergunta, "resposta": resposta, "kbIdExistente": ex["id"] if ex else None}


def _aprender(b: dict):
    """Ramo 'Ler base (aprendizado)' — roda depois da resposta ao painel (como no n8n)."""
    try:
        base = T.get("BASE_CONHECIMENTO")
        j = preparar_aprendizado(b, base)
        if not j:
            return
        a = interpretar_aprendizado(gemini.gerar_texto(P.montar("IA - Extrair aprendizado", j), 0), base)
        if not a:
            return
        if a["kbIdExistente"] is not None:
            T.update("BASE_CONHECIMENTO", {"id": a["kbIdExistente"]},
                     {"pergunta": a["pergunta"], "resposta": a["resposta"], "atualizadoEm": C.agora_iso()})
        else:
            T.insert("BASE_CONHECIMENTO", {"pergunta": a["pergunta"], "resposta": a["resposta"], "usos": 0,
                                           "criadoEm": C.agora_iso(), "atualizadoEm": C.agora_iso()})
    except Exception:  # noqa: BLE001
        log.exception("Aprendizado do consultor")


# ===================================================================== fluxo
def _registrar(proc: dict, montar_resp: dict | None) -> tuple[dict, int]:
    """REGISTRAR (ou RESPONDER com resultado): intranet + planilha + fechar o card."""
    itens = preparar_resultado(proc)
    intra = Intranet()
    try:
        intra.login()
    except Exception:  # noqa: BLE001  (onError=continueRegularOutput)
        log.exception("Login intranet (consultor)")
    entradas, urls = [], []
    if itens[0].get("resultado") == "ADIADO":
        for p in itens:
            form = intra.abrir_form_alteracao(p.get("dataAdiamentoISO"), p.get("pedidoLider"))
            u = montar_url_consultor(form.get("data"), p)
            urls.append(u)
            entradas.append(intra.alterar_data(u["urlAlterar"]) if u.get("urlAlterar") else {"error": "URL de alteração inválida"})
    obs = montar_observacao(itens, entradas, urls)
    obs_int = []
    for o in obs:
        if o["temObservacao"] is True:
            obs_int.append(intra.aviso_entrega(o["pedidoLider"], o["clienteIntranet"], o["datEntrega"],
                                               "CONFIRMACAO DE DATA DE ENTREGA", o["observacao"], "AE"))
    try:
        linhas = planilha.ler_linhas()
    except Exception:  # noqa: BLE001
        log.exception("Ler planilha (consultor)")
        linhas = []
    loc = localizar_linha(obs, linhas)
    gravs = []
    for x in loc:
        if C.js_truthy(x.get("row_number")):
            gravs.append(planilha.atualizar("row_number", x["row_number"], {
                "CONFIRMADO": x["sheetG"], "MOTIVO": x["sheetH"], "DATA ENVIO CONF.": x["sheetI"]}))
    rs = resumo_registro(loc, gravs, obs_int, proc, montar_resp)
    try:
        T.update("AGUARDANDO_ENTREGA", {"id": rs["id"]}, {
            "status": "CONCLUIDO", "categoria": rs.get("categoria"), "resumoIA": rs["resumoIA"],
            "chatConsultor": rs["chatConsultor"], "respondidoEm": C.agora_iso(), "vigiaAte": rs["vigiaAte"],
            "dadosPedido": rs["dadosPedidoNovo"]})
    except Exception:  # noqa: BLE001
        log.exception("Finalizar pedido (consultor)")
    if proc.get("origemTardia") is True:
        try:
            T.update("SEM_CONFIRMACAO_DIARIO", {"pedidoLider": proc.get("semConfPedidoTardia"), "status": "RESPONDEU_DEPOIS"},
                     {"status": "RESPOSTA_TARDIA_TRATADA"})
        except Exception:  # noqa: BLE001
            log.exception("Marcar resposta tardia tratada (registro)")
    return {"ok": True, "acao": proc["acao"], "resultado": rs.get("resultado"), "planilha": rs["planilha"],
            "intranet": rs["intranet"], "avisos": rs["avisos"]}, 200


def _transferir(proc: dict) -> tuple[dict, int]:
    m = L.mapear_responsavel_transferencia(proc, listar_usuarios_todos())
    falhou = True
    if m["statusMapeamento"] == "OK" and m["userIdResponsavel"]:
        t = digisac.transferir_chamado(
            proc.get("contactId"), DEPARTAMENTO_CENTRAL, m["userIdResponsavel"],
            f"Pedido {C.js_str(proc.get('pedidoLider'))} - {C.js_str(proc.get('cliente'))}. Transferência solicitada pelo "
            f"consultor via chat da IA. Conversa: {proc['resumoChat']}")
        falhou = bool((t or {}).get("error"))
    if falhou:
        email.enviar(EMAIL_AVISOS, f"Ação manual necessária - pedido {C.js_str(proc.get('pedidoLider'))}",
                     f"<p>O consultor pediu transferência pelo chat da IA, mas não foi possível mapear o responsável.</p>"
                     f"<p>Pedido: {C.js_str(proc.get('pedidoLider'))}<br>Responsável cadastrado: {C.js_str(proc.get('responsavel'))}"
                     f"<br>Cliente: {C.js_str(proc.get('cliente'))}<br>Conversa: {proc['resumoChat']}</p>")
        digisac.enviar_mensagem(proc.get("contactId"), "Registrei sua solicitação para verificação interna.")
    else:
        digisac.enviar_mensagem(proc.get("contactId"), "Certo! Encaminhei seu atendimento ao responsável pelo seu pedido. "
                                                       "Ele dará continuidade por aqui.")
    ok = m["statusMapeamento"] == "OK"
    T.update("AGUARDANDO_ENTREGA", {"id": proc["id"]}, {
        "status": "TRANSFERIDO" if ok else "TRANSFERENCIA_MANUAL", "chatConsultor": proc["chatConsultor"],
        "resumoIA": str(C.js_or(proc.get("resumoIA"), "")) + (" | Transferido ao responsável (pedido do consultor)" if ok
                                                             else " | Transferência automática falhou; requer ação manual"),
        "respondidoEm": C.agora_iso()})
    return {"ok": True, "acao": proc["acao"]}, 200


def _responder(proc: dict) -> tuple[dict, int]:
    out = gemini.gerar_texto(P.montar("IA - Redigir resposta do consultor", proc), 0)
    mr = montar_resposta_cliente(proc, out)
    envio = digisac.enviar_mensagem(mr.get("contactId"), mr["respostaCliente"])
    if (envio or {}).get("error"):
        return {"ok": False, "erro": "Não consegui enviar a mensagem ao cliente pelo DigiSac. A consulta continua aguardando; "
                                     "tente novamente."}, 200
    T.update("AGUARDANDO_ENTREGA", {"id": mr["id"]}, {
        "status": "CONCLUIDO", "chatConsultor": mr["chatConsultor"],
        "resumoIA": str(C.js_or(mr.get("resumoIA"), "")) + " | Respondido pelo consultor via chat",
        "respondidoEm": C.agora_iso(), "vigiaAte": C.iso_local_mais(2)})
    if C.js_truthy(proc.get("resultado")):
        resp = _registrar(proc, mr)
    else:
        resp = ({"ok": True, "acao": proc["acao"]}, 200)
    threading.Thread(target=_aprender, args=(mr,), name="consultor-aprendizado", daemon=True).start()
    return resp


@gatilho("central-lider-consultor")
def consultor_chat(entrada, req):
    body = entrada.get("body") or {}
    linhas = T.get("AGUARDANDO_ENTREGA", {"id": body.get("id")}) if body.get("id") not in (None, "") else []
    proc = processar_acao(body, linhas[0] if linhas else {})
    if proc["erro"]:
        return {"ok": False, "erro": proc["erro"]}, 200
    if proc["acao"] == "REGISTRAR":
        return _registrar(proc, None)
    if proc["acao"] == "TRANSFERIR":
        return _transferir(proc)
    return _responder(proc)
