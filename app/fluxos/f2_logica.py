"""Fluxo 2 (resposta do cliente no DigiSac) — funções puras, uma por nó Code da v28."""
import re
from datetime import date, timedelta

from .. import comum as C

# ===================================================================== entrada
def filtrar_mensagem(entrada: dict) -> dict | None:
    """Nó 'Filtrar Mensagem'."""
    body = entrada.get("body") or entrada
    data = body.get("data") or body if isinstance(body, dict) else {}
    if data.get("isFromMe") is True:
        return None
    if str(data.get("type") or "").lower() in ("ticket", "comment"):
        return None
    texto = str(((data.get("data") or {}).get("text") if isinstance(data.get("data"), dict) else None)
                or data.get("text") or "").strip()
    agora = C.agora_ms()
    saida = {k: data[k] for k in ("contactId", "serviceId") if k in data}   # undefined some do JSON
    return {**saida, "messageId": data.get("id") or f"sem-id-{agora}", "ts": agora,
            "text": texto or "[mensagem sem texto: áudio, imagem ou arquivo]"}


def _ord_key(r):
    return (float(r.get("ts") or 0), str(r.get("messageId")))


def agrupar_mensagens(me: dict, linhas_tabela: list[dict]) -> dict | None:
    """Nó 'Agrupar mensagens do cliente'. None = outra execução responde."""
    janela = 5 * 60 * 1000
    hist_max = 14
    me_ts = float(me.get("ts") or 0) or C.agora_ms()
    linhas = sorted((r for r in linhas_tabela if r and not r.get("error")
                     and str(r.get("contactId") or "") == str(me.get("contactId"))
                     and str(r.get("texto") or "").strip() != ""), key=_ord_key)
    me_id = str(me.get("messageId") or "")
    if me_id and not me_id.startswith("sem-id-"):
        if any(str(r.get("papel") or "").upper() == "CLIENTE" and str(r.get("messageId")) == me_id
               and float(r.get("ts") or 0) < me_ts for r in linhas):
            return None
    vistos, filtradas = set(), []
    for r in linhas:
        if str(r.get("papel") or "").upper() != "CLIENTE":
            filtradas.append(r)
            continue
        k = str(r.get("messageId") or "")
        if not k or k.startswith("sem-id-"):
            filtradas.append(r)
            continue
        if k in vistos:
            continue
        vistos.add(k)
        filtradas.append(r)
    linhas = filtradas
    marcas = [r for r in linhas if str(r.get("papel") or "").upper() == "RECOMECO" and float(r.get("ts") or 0) <= me_ts]
    corte_rec = float(marcas[-1]["ts"]) if marcas else 0
    linhas = [r for r in linhas if str(r.get("papel") or "").upper() != "RECOMECO" and float(r.get("ts") or 0) > corte_rec]
    do_cliente = [r for r in linhas if r.get("papel") == "CLIENTE"]
    mais_nova = do_cliente[-1] if do_cliente else None
    if mais_nova and str(mais_nova.get("messageId")) != str(me.get("messageId")) \
            and _ord_key(mais_nova) > (me_ts, str(me.get("messageId"))):
        return None
    bots = [r for r in linhas if r.get("papel") == "BOT" and float(r.get("ts") or 0) <= me_ts]
    ultimo_bot = float(bots[-1]["ts"]) if bots else 0
    corte = max(ultimo_bot, me_ts - janela)
    grupo = [r for r in do_cliente if corte < float(r.get("ts") or 0) <= me_ts]
    if not any(str(r.get("messageId")) == str(me.get("messageId")) for r in grupo):
        grupo.append({"texto": me.get("text"), "ts": me_ts, "messageId": me.get("messageId")})
    grupo.sort(key=_ord_key)
    historico = "\n".join(
        f"{'Líder' if r.get('papel') == 'BOT' else 'Cliente'}: {re.sub(r'\s+', ' ', str(r.get('texto'))).strip()[:600]}"
        for r in [r for r in linhas if float(r.get("ts") or 0) <= corte][-hist_max:])
    return {**me, "text": "\n".join(str(r.get("texto")).strip() for r in grupo),
            "qtdMensagensAgrupadas": len(grupo), "historico": historico}


def escolher_linha(msg: dict, linhas: list[dict]) -> list[dict]:
    """Nó 'Escolher Linha'."""
    agora = C.agora_ms()

    def passou(r):
        t = C.iso_ms(r.get("enviadoEm"))
        return not t or (agora - t) > 15000

    extra = {"textoCliente": msg.get("text"), "historicoConversa": msg.get("historico") or ""}
    aguardando = [r for r in linhas if r.get("status") == "AGUARDANDO" and passou(r)]
    if aguardando:
        return [{**r, "fluxo": "TEMPLATE", **extra} for r in aguardando]
    if any(r.get("status") == "AGUARDANDO" for r in linhas):
        return []
    chave = lambda r: str(r.get("respondidoEm") or r.get("enviadoEm") or "")  # noqa: E731
    for status, fluxo in (("AGUARDANDO_DECISAO_RESPONSAVEL", "DECISAO_RESPONSAVEL"), ("AGUARDANDO_CONSULTOR", "CONSULTOR_MSG")):
        l = sorted((r for r in linhas if r.get("status") == status), key=chave, reverse=True)
        if l:
            return [{**l[0], "fluxo": fluxo, **extra}]
    env = sorted((r for r in linhas if r.get("status") == "DATA_ENVIADA"), key=lambda r: str(r.get("enviadoEm") or ""), reverse=True)
    if env:
        return [{**env[0], "fluxo": "IA", **extra}]
    vig = sorted((r for r in linhas if r.get("status") == "CONCLUIDO" and r.get("vigiaAte") and C.iso_ms(r["vigiaAte"]) > agora),
                 key=lambda r: str(r.get("vigiaAte")), reverse=True)
    if vig:
        return [{**vig[0], "fluxo": "VIGILANCIA", **extra}]
    return []


# ===================================================================== datas no formato do JS
def parse_br(s, estrito=True):
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", str(s or ""))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


# ===================================================================== Preparar contexto IA
def preparar_contexto(j: dict) -> dict:
    limite_dias = 130
    datas = re.findall(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\b", str(j.get("mensagem") or ""))
    dp = C.loads(j.get("dadosPedido") or "{}", {}) or {}
    membros = dp.get("pedidosGrupo") if isinstance(dp.get("pedidosGrupo"), list) and len(dp["pedidosGrupo"]) > 1 else None
    datas_grupo = sorted(d for d in (parse_br((e or {}).get("data")) for m in (membros or []) for e in (m.get("entregas") or [])) if d)
    registro = dp.get("registroContato") or None
    registrada = parse_br(registro.get("dataEntrega")) if registro else None
    prevista = registrada or ((datas_grupo[0] if datas_grupo else None) if membros else next((d for d in map(parse_br, datas) if d), None))
    limite = prevista + timedelta(days=limite_dias) if prevista else None
    hoje = C.agora()
    if registrada:
        ctx_prev = f"{fmt(registrada)} (data já registrada na intranet{' para todos os pedidos da mensagem' if membros else ''})"
    elif membros:
        ctx_prev = "; ".join(f"pedido {m.get('pedidoLider')}: {', '.join(str(e.get('data')) for e in (m.get('entregas') or []))}"
                             for m in membros) + " (mensagem única: a resposta do cliente vale para todos esses pedidos)"
    else:
        ctx_prev = fmt(prevista) if prevista else "não identificada"
    if registro:
        res = registro.get("resultado") or registro.get("categoria") or "registrado"
        ctx_reg = (f"O contato deste pedido JÁ FOI REGISTRADO na planilha e na intranet ({res}"
                   f"{', data ' + registro['dataEntrega'] if registro.get('dataEntrega') else ''}). "
                   "Não existe novo registro: só interprete a fala.")
    else:
        ctx_reg = "Ainda não registrado."
    return {**j, "ctxHoje": f"{hoje.strftime('%d/%m/%Y')} ({DIAS_SEMANA[hoje.weekday()]})", "ctxPrevista": ctx_prev,
            "ctxLimite": fmt(limite) if limite else "não identificada", "ctxRegistro": ctx_reg,
            "ctxHistorico": str(j.get("historicoConversa") or "")[-4000:] or "(sem mensagens anteriores registradas)"}


# ===================================================================== decisão do responsável / chat
def interpretar_decisao_responsavel(j: dict) -> dict:
    t = re.sub(r"\s+", " ", C.sem_acento(j.get("textoCliente") or "").lower()).strip()
    nao = bool(re.search(r"\b(nao|nem|n)\b|pode deixar|deixa (pra la|quieto|assim)|dispens|sem necessidade|tudo certo assim|esta bom assim|ta bom assim", t))
    sim = bool(re.search(r"\b(sim|quero|pode( sim| encaminhar| passar)?|por favor|encaminh|claro|ok|beleza|isso|aceito|gostaria|prefiro|manda|com certeza)\b", t))
    decisao = "AMBIGUA"
    if nao and not re.match(r"^(sim|pode sim)\b", t):
        decisao = "NAO"
    elif sim:
        decisao = "SIM"
    return {**j, "decisaoResponsavel": decisao}


def _chat(j) -> list:
    c = C.loads(j.get("chatConsultor") or "[]", [])
    return c if isinstance(c, list) else []


def anexar_mensagem_chat(j: dict) -> dict:
    chat = _chat(j)
    chat.append({"role": "cliente", "texto": str(j.get("textoCliente") or ""), "ts": C.agora_iso_utc()})
    return {"id": j.get("id"), "chatConsultor": C.dumps(chat)}


def interpretar_classificacao_vigilancia(linha: dict, resp: dict) -> dict:
    bruto = str(resp.get("text") if resp.get("text") is not None else resp.get("output") or "").strip()
    r = C.loads(re.sub(r"```json|```", "", bruto).strip(), {}) or {}
    tipo = str(r.get("tipo") or "").upper() if isinstance(r, dict) else ""
    if tipo not in ("DUVIDA", "SEM_ACAO", "REGRA"):
        tipo = "DUVIDA"
    if re.match(r"^\[mensagem sem texto", str(linha.get("textoCliente") or ""), re.I):
        tipo = "DUVIDA"
    return {**linha, "vigTipo": tipo, "vigResumo": str((r.get("resumo") if isinstance(r, dict) else "") or "")}


def mapear_responsavel_transferencia(row: dict, respostas_usuarios: list) -> dict:
    norm = lambda s: C.sem_acento(s).strip().upper()  # noqa: E731
    ignore = ["DE", "DA", "DO", "DAS", "DOS", "E"]
    toks = [x for x in re.split(r"\s+", norm(row.get("responsavel"))) if x and x not in ignore]
    vistos, users = set(), []
    for r in respostas_usuarios:
        for u in (r.get("data") if isinstance(r.get("data"), list) else [r]):
            if not u or not u.get("id") or not u.get("name") or u["id"] in vistos:
                continue
            vistos.add(u["id"])
            users.append(u)
    cand = [u for u in users if all(any(x == t or (len(t) >= 4 and x.startswith(t)) for x in re.split(r"\s+", norm(u["name"])))
                                    for t in toks)] if toks else []
    if len(cand) != 1:
        return {**row, "userIdResponsavel": "", "statusMapeamento": "AMBIGUO" if cand else "NAO_ENCONTRADO",
                "candidatos": [x["name"] for x in cand]}
    return {**row, "userIdResponsavel": cand[0]["id"], "statusMapeamento": "OK", "nomeResponsavel": cand[0]["name"]}


# ===================================================================== base de conhecimento
def montar_baseTexto(base: list[dict]) -> tuple[str, bool]:
    lista = [r for r in base if r and r.get("id") is not None and r.get("pergunta") and r.get("resposta")][-200:]
    return "\n\n".join(f"[ID {r['id']}]\nPergunta: {r['pergunta']}\nResposta: {r['resposta']}" for r in lista), len(lista) == 0


def interpretar_resposta_base(resp: dict, base: list[dict]) -> dict:
    bruto = str(resp.get("text") if resp.get("text") is not None else resp.get("output") or "").strip()
    r = C.loads(re.sub(r"```json|```", "", bruto).strip(), {}) or {}
    if not isinstance(r, dict):
        r = {}
    entrada = next((x for x in base if x and x.get("id") is not None and str(x["id"]) == str(r.get("id"))), None)
    texto = str(r.get("resposta") or "").strip()
    usar = r.get("encontrou") is True and bool(entrada) and bool(texto)
    return {"usarBase": usar, "kbId": entrada["id"] if usar else None,
            "kbUsos": int(float(entrada.get("usos") or 0)) if usar else 0, "respostaBase": texto}


# ===================================================================== Normalizar Categoria
CATEGORIAS = ["ACEITA", "ACEITA_PEDE_ADIANTAR", "PEDE_ADIAR", "DUVIDA_ADIAMENTO", "NAO_ACEITA",
              "ACEITA_CONTATO_RESPONSAVEL", "RECUSA_CONTATO_RESPONSAVEL", "OUTRO"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]
OFERTA_RESPONSAVEL = ("Você gostaria que eu encaminhasse o atendimento ao responsável pelo seu pedido para combinar "
                      "uma alternativa com você?")
AVISO_ARMAZENAGEM = ("Lembrando que, caso o pedido fique pronto antes da nova data, ele poderá ficar armazenado em nosso "
                     "estoque por até *30 dias*. Após esse prazo, será cobrada uma taxa de armazenamento.")
TXT_NAO_ACEITA = ("Entendo. A data que informamos é a previsão que consta atualmente no sistema. Se foi combinada outra "
                  "data com o vendedor, peço que procure o mesmo para verificar a data de entrega.")


def _feriado(d: date) -> bool:
    """Lista do nó Normalizar Categoria (sem Sexta-feira Santa)."""
    return (d.month, d.day) in {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}


def _util(d: date) -> bool:
    return d.weekday() < 5 and not _feriado(d)


def _proximo_util(d: date) -> date:
    while not _util(d):
        d += timedelta(days=1)
    return d


def _anterior_util(d: date) -> date:
    while not _util(d):
        d -= timedelta(days=1)
    return d


def js_number(v, existe=True):
    """Number(v) do JS; None quando o resultado não é finito (NaN). undefined -> NaN; null/'' -> 0."""
    if not existe:
        return None
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def _num(v):
    try:
        x = float(v)
        return x if x == x and x not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def normalizar_categoria(linha: dict, out: dict, base_resp: dict | None) -> dict:
    out = out or {}
    dp = C.loads(linha.get("dadosPedido") or "{}", {}) or {}
    membros = dp.get("pedidosGrupo") if isinstance(dp.get("pedidosGrupo"), list) and len(dp["pedidosGrupo"]) > 1 else None
    reg_ant = dp.get("registroContato") or None
    cat_orig = str(out.get("categoria") if out.get("categoria") is not None else "OUTRO").strip().upper()
    categoria = cat_orig if cat_orig in CATEGORIAS else "OUTRO"
    confianca = js_number(out.get("confianca"), "confianca" in out)
    if confianca is not None and confianca < 0.5:
        categoria = "OUTRO"

    datas_msg = re.findall(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\b", str(linha.get("mensagem") or ""))
    datas_grupo = sorted(d for d in (parse_br((e or {}).get("data")) for m in (membros or []) for e in (m.get("entregas") or [])) if d)
    registrada = parse_br(reg_ant.get("dataEntrega")) if reg_ant else None
    prevista = registrada or ((datas_grupo[0] if datas_grupo else None) if membros else next((d for d in map(parse_br, datas_msg) if d), None))
    prevista_max = registrada or ((datas_grupo[-1] if datas_grupo else None) if membros else prevista)
    diferentes = bool(membros and prevista and prevista_max and prevista_max > prevista)
    data_max = prevista + timedelta(days=130) if prevista else None
    primeiro = _proximo_util(prevista_max + timedelta(days=1)) if prevista_max else None
    este = "estes pedidos" if membros else "este pedido"
    pedidos_grupo = [str(m.get("pedidoLider")) for m in membros] if membros else [str(linha.get("pedidoLider") or "")]
    pedidos_txt = C.lista_txt(pedidos_grupo) if len(pedidos_grupo) > 1 else pedidos_grupo[0]
    ultimo = _anterior_util(data_max) if data_max else None
    B = lambda d: f"*{fmt(d)}*"  # noqa: E731
    ja_avisou = bool(re.search("armazenad|armazenamento", str(linha.get("historicoConversa") or ""), re.I))
    aviso_arm = "" if ja_avisou else f"\n\n{AVISO_ARMAZENAGEM}"
    janela = f"Consigo reagendar para qualquer dia útil entre {B(primeiro)} e {B(ultimo)}." if (primeiro and ultimo) else ""

    data_sol = parse_br(out.get("dataSolicitada"))
    mm = re.match(r"^(\d{1,2})/(\d{4})$", str(out.get("mesSolicitado") or ""))
    mes_sol = {"mes": int(mm.group(1)), "ano": int(mm.group(2))} if mm else None
    falas_lider = [l for l in str(linha.get("historicoConversa") or "").split("\n") if l.startswith("Líder:")][-4:]
    vezes = len([l for l in falas_lider if re.search(r"qual (data|dia)|preciso do dia exato|me (diga|informe|mande) o dia", l, re.I)])

    if prevista and ultimo:
        txt_duvida = (f"Pode sim! Caso precise, é só nos avisar por aqui com a nova data. Conseguimos reagendar a entrega "
                      f"para qualquer dia útil até {B(ultimo)}.{aviso_arm}\n\n"
                      + ("Por enquanto, podemos manter as previsões de entrega informadas?" if diferentes
                         else f"Por enquanto, podemos manter a previsão de entrega para {B(prevista)}?"))
    else:
        txt_duvida = (f"Pode sim! Caso precise, é só nos avisar por aqui com a nova data que verificamos para você.{aviso_arm}"
                      "\n\nPor enquanto, podemos manter a data prevista?")
    respostas = {
        "ACEITA": ("Perfeito, obrigado pela confirmação! Qualquer novidade, avisamos por aqui.", "CONCLUIDO"),
        "ACEITA_PEDE_ADIANTAR": ("Entendo! No momento, não conseguimos solicitar a antecipação da entrega por este atendimento. "
                                 "A data informada é a previsão registrada no sistema. Se houver alguma atualização, avisaremos você por aqui.",
                                 "CONCLUIDO"),
        "PEDE_ADIAR": (None, "DATA_ENVIADA"),
        "DUVIDA_ADIAMENTO": (txt_duvida, "DATA_ENVIADA"),
        "NAO_ACEITA": (TXT_NAO_ACEITA, "CONCLUIDO"),
        "ACEITA_CONTATO_RESPONSAVEL": (None, "ESCALADO"),
        "RECUSA_CONTATO_RESPONSAVEL": ("Tudo bem! Não vou encaminhar o atendimento neste momento. Se mudar de ideia, é só nos avisar por aqui.",
                                       "CONCLUIDO"),
        "OUTRO": (None, "AGUARDANDO_CONSULTOR"),
    }
    adiar_entre = False
    if categoria == "PEDE_ADIAR" and data_sol and prevista:
        if diferentes:
            if data_sol < prevista:
                categoria = "NAO_ACEITA"
            elif data_sol <= prevista_max:
                adiar_entre = True
        elif fmt(data_sol) == fmt(prevista):
            categoria = "ACEITA"
        elif data_sol < prevista:
            categoria = "NAO_ACEITA"

    resposta_fixa, status_final = respostas[categoria]
    escalar = status_final == "ESCALADO"
    adiamento_valido, motivo_adiamento, tipo_resposta = False, "", categoria

    if categoria == "PEDE_ADIAR":
        if data_sol and not prevista:
            motivo_adiamento = "Não consegui confirmar a data prevista atual no registro do pedido."
            resposta_fixa = f"Não consegui validar automaticamente a data solicitada. {OFERTA_RESPONSAVEL}"
            status_final, tipo_resposta = "AGUARDANDO_DECISAO_RESPONSAVEL", "ADIAR_SEM_PREVISTA"
        elif data_sol and adiar_entre:
            motivo_adiamento = f"Os pedidos têm previsões diferentes ({fmt(prevista)} a {fmt(prevista_max)}) e a data pedida fica entre elas."
            resposta_fixa = (f"Seus pedidos têm previsões de entrega diferentes (de {B(prevista)} a {B(prevista_max)}), então não "
                             f"consigo reagendar todos para {B(data_sol)} por aqui. {OFERTA_RESPONSAVEL}")
            status_final, tipo_resposta = "AGUARDANDO_DECISAO_RESPONSAVEL", "ADIAR_GRUPO_DATAS_DIFERENTES"
        elif data_sol:
            if data_sol > data_max:
                motivo_adiamento = f"O limite para adiamento é {fmt(ultimo)}."
                resposta_fixa = (f"Entendo que essa data seria melhor para você, mas o prazo máximo para reagendar {este} é "
                                 f"{B(ultimo)}. {OFERTA_RESPONSAVEL}")
                status_final, tipo_resposta = "AGUARDANDO_DECISAO_RESPONSAVEL", "ADIAR_ALEM_LIMITE"
            else:
                util = _proximo_util(data_sol)
                if util > data_max:
                    motivo_adiamento = (f"A data cai em fim de semana/feriado e não há dia útil disponível dentro do limite "
                                        f"de {fmt(ultimo)}.")
                    resposta_fixa = (f"Essa data cai em fim de semana/feriado e o próximo dia útil já passa do limite de "
                                     f"{B(ultimo)}. {OFERTA_RESPONSAVEL}")
                    status_final, tipo_resposta = "AGUARDANDO_DECISAO_RESPONSAVEL", "ADIAR_SEM_DIA_UTIL"
                else:
                    data_sol = util
                    adiamento_valido, tipo_resposta = True, "ADIAR_VALIDO"
        elif mes_sol and prevista:
            nome_mes = MESES[mes_sol["mes"] - 1] if 1 <= mes_sol["mes"] <= 12 else "esse mês"
            try:
                ini = date(mes_sol["ano"], mes_sol["mes"], 1)
                fim = (date(mes_sol["ano"] + (mes_sol["mes"] // 12), mes_sol["mes"] % 12 + 1, 1) - timedelta(days=1))
            except ValueError:
                ini = fim = None
            if ini is None:
                pass
            elif fim <= prevista:
                categoria, resposta_fixa, status_final, tipo_resposta = "NAO_ACEITA", TXT_NAO_ACEITA, "CONCLUIDO", "MES_ANTES_DA_PREVISTA"
            elif ini > ultimo:
                motivo_adiamento = f"O limite para adiamento é {fmt(ultimo)}."
                resposta_fixa = (f"Entendo! O prazo máximo para reagendar {este} é {B(ultimo)}, então não consigo deixar a "
                                 f"entrega para {nome_mes} por aqui. {OFERTA_RESPONSAVEL}")
                status_final, tipo_resposta = "AGUARDANDO_DECISAO_RESPONSAVEL", "MES_ALEM_LIMITE"
            else:
                de = primeiro if ini < primeiro else _proximo_util(ini)
                ate = ultimo if fim > ultimo else _anterior_util(fim)
                if membros and de > ate:
                    resposta_fixa = (f"Entendo! Em {nome_mes} não tenho um dia disponível para reagendar todos os seus pedidos "
                                     f"por aqui. {OFERTA_RESPONSAVEL}")
                    status_final, tipo_resposta = "AGUARDANDO_DECISAO_RESPONSAVEL", "MES_SEM_DIA_GRUPO"
                else:
                    inteiro = (de - ini).days <= 3 and (fim - ate).days <= 3
                    resposta_fixa = (f"Claro! Qual dia de {nome_mes} fica melhor para você? "
                                     + ("Pode ser qualquer dia útil do mês." if inteiro else f"Em {nome_mes}, consigo agendar de {B(de)} até {B(ate)}.")
                                     + aviso_arm)
                    status_final, tipo_resposta = "DATA_ENVIADA", "PEDIR_DIA_DO_MES"
        elif vezes >= 2:
            resposta_fixa = ("Para não te deixar esperando, posso pedir para o responsável pelo seu pedido falar com você e "
                             "combinar a melhor data. Pode ser?")
            status_final, tipo_resposta = "AGUARDANDO_DECISAO_RESPONSAVEL", "OFERECER_RESPONSAVEL"
        elif vezes == 1:
            ex = _proximo_util(primeiro + timedelta(days=14)) if primeiro else None
            resposta_fixa = (f"Para eu conseguir registrar, preciso do dia exato. Pode me mandar no formato dia/mês/ano"
                             f"{f', por exemplo {B(ex)}' if ex else ''}? {janela}").strip() + aviso_arm
            status_final, tipo_resposta = "DATA_ENVIADA", "PEDIR_DATA_NOVAMENTE"
        else:
            resposta_fixa = f"Podemos verificar, sim! Para qual data você gostaria de reagendar a entrega? {janela}".strip() + aviso_arm
            status_final, tipo_resposta = "DATA_ENVIADA", "PEDIR_DATA"
        if not adiamento_valido and not motivo_adiamento and categoria == "PEDE_ADIAR":
            motivo_adiamento = "DATA_NAO_INFORMADA"
        escalar = False

    fora = out.get("foraDaRegra") is True or str(out.get("foraDaRegra") if out.get("foraDaRegra") is not None else "").strip().lower() == "true"
    assunto_fora = str(out.get("assuntoFora") or "").strip()
    base_respondeu = bool(fora and base_resp and base_resp.get("usarBase") is True and str(base_resp.get("respostaBase") or "").strip())
    consultar = categoria == "OUTRO"
    usou_base = False

    def ao_consultor(tipo):
        nonlocal categoria, resposta_fixa, status_final, tipo_resposta, adiamento_valido, escalar, consultar
        categoria, resposta_fixa, status_final = "OUTRO", None, "AGUARDANDO_CONSULTOR"
        tipo_resposta, adiamento_valido, escalar, consultar = tipo, False, False, True

    if fora:
        if base_respondeu and categoria in ("ACEITA", "ACEITA_PEDE_ADIANTAR"):
            resposta_fixa = f"{str(base_resp['respostaBase']).strip()}\n\nE obrigado pela confirmação!"
            status_final, tipo_resposta, usou_base, consultar, escalar = "CONCLUIDO", "FORA_DA_REGRA_BASE_CONFIRMOU", True, False, False
        elif base_respondeu and categoria == "OUTRO":
            resposta_fixa = str(base_resp["respostaBase"]).strip()
            status_final = str(linha.get("status") or "DATA_ENVIADA")
            tipo_resposta, usou_base, consultar, escalar = "FORA_DA_REGRA_BASE", True, False, False
            categoria = str(linha.get("categoria") or "")
        else:
            ao_consultor("FORA_DA_REGRA")

    if reg_ant:
        if not consultar and not usou_base and categoria in ("PEDE_ADIAR", "NAO_ACEITA"):
            ao_consultor("ALTERAR_REGISTRO")
        if not consultar:
            if categoria == "ACEITA" and not usou_base:
                resposta_fixa, tipo_resposta = None, "JA_REGISTRADO"
            if status_final == "DATA_ENVIADA":
                status_final = "CONCLUIDO"
            adiamento_valido = False
        categoria = str(linha.get("categoria") or categoria)

    resumo = " | ".join(x for x in (str(out.get("resumo") or "").strip(), str(out.get("intencao") or "").strip()) if x)
    return {**linha, "categoria": categoria, "categoriaIA": cat_orig, "confiancaIA": confianca,
            "tipoResposta": tipo_resposta, "resumoIA": resumo,
            "dataSolicitada": fmt(data_sol) if data_sol else None,
            "dataPrevistaOriginal": fmt(prevista) if prevista else None,
            "dataMaximaAdiamento": fmt(ultimo) if ultimo else None,
            "adiamentoValido": adiamento_valido, "motivoAdiamento": motivo_adiamento, "respostaFixa": resposta_fixa,
            "temResposta": bool(resposta_fixa), "statusFinal": status_final, "escalar": escalar, "consultar": consultar,
            "foraDaRegra": fora, "assuntoFora": assunto_fora, "usouBase": usou_base,
            "kbIdUsado": base_resp.get("kbId") if usou_base else None, "registroAnterior": reg_ant,
            "pedidosGrupo": pedidos_grupo, "pedidosTexto": pedidos_txt, "grupoPedidos": membros,
            "dataPrevistaMaxima": fmt(prevista_max) if prevista_max else None}


# ===================================================================== anti-repetição (saída)
def norm_rep(t) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_~]", "", str(t or ""))).strip().lower()


def anti_repeticao(originais: list[dict], linhas_tabela: list[dict], texto_do_envio) -> list[dict]:
    """Nós 'Anti-repetição: pode enviar? (...)'. Devolve só os itens que podem ser enviados."""
    agora = C.agora_ms()
    vistas, todas = set(), []
    for r in linhas_tabela:
        if not r or r.get("error") or not r.get("papel"):
            continue
        k = f"{r.get('id', '')}|{r.get('messageId')}|{r.get('ts')}|{r.get('papel')}"
        if k in vistas:
            continue
        vistas.add(k)
        todas.append(r)
    todas.sort(key=lambda r: float(r.get("ts") or 0))
    juntos = " ".join(x for x in (norm_rep(texto_do_envio(o)) for o in originais) if x)
    saida = []
    for o in originais:
        contato = str(o.get("contactId") or "")
        linhas = [r for r in todas if str(r.get("contactId") or "") == contato]
        marcas = [r for r in linhas if str(r["papel"]).upper() == "RECOMECO"]
        corte = float(marcas[-1]["ts"]) if marcas else 0
        linhas = [r for r in linhas if float(r.get("ts") or 0) > corte]
        bots = [r for r in linhas if str(r["papel"]).upper() == "BOT"]
        clientes = [r for r in linhas if str(r["papel"]).upper() == "CLIENTE"]
        ultimo_bot = bots[-1] if bots else None
        ultimo_cli = float(clientes[-1]["ts"]) if clientes else 0
        texto = norm_rep(texto_do_envio(o))
        motivo = None
        if texto and ultimo_bot and agora - float(ultimo_bot.get("ts") or 0) < 24 * 3600 * 1000:
            ant = norm_rep(ultimo_bot.get("texto"))
            if ant == texto or (len(originais) > 1 and ant == juntos):
                motivo = "MENSAGEM_REPETIDA"
        if not motivo:
            depois = len([r for r in bots if float(r.get("ts") or 0) > ultimo_cli and agora - float(r.get("ts") or 0) < 30 * 60 * 1000])
            if depois >= 1:
                motivo = "RESPOSTAS_DEMAIS"
        if not motivo and texto and any(norm_rep(texto_do_envio(s)) == texto for s in saida):
            motivo = "MENSAGEM_REPETIDA"
        if motivo:
            import logging
            logging.getLogger("central").info("[anti-repetição] envio bloqueado contato %s: %s", contato, motivo)
            continue
        saida.append(o)
    return saida


def texto_confirmacao_adiamento(ok: bool, dt) -> str:
    """Texto que 'Preparar registro da resposta' grava para o envio do adiamento."""
    return (f"Conseguimos atualizar a previsão de entrega para {dt}." if ok else
            f"Recebi o pedido para adiar para {dt}, mas não consegui registrar no sistema. Ofereci encaminhar ao responsável.")


def msg_confirmacao_adiamento(ok: bool, n: dict) -> str:
    """Texto enviado ao cliente no nó 'Enviar Confirmação Adiamento'."""
    if ok:
        alvo = (f"dos seus pedidos *{n.get('pedidosTexto')}*" if len(n.get("pedidosGrupo") or []) > 1 else "do seu pedido")
        return (f"Conseguimos atualizar a previsão de entrega {alvo} para *{n.get('dataSolicitada')}*. Essa data considera "
                "dias úteis e feriados nacionais.\n\nLembrando que, caso o pedido fique pronto antes dessa data, ele poderá "
                "ficar armazenado em nosso estoque por até *30 dias*. Após esse prazo, será cobrada uma taxa de armazenamento."
                "\n\nSe houver nova atualização, avisaremos por aqui.")
    return (f"Recebi o seu pedido para adiar a entrega para *{n.get('dataSolicitada')}*, mas não consegui registrar a alteração "
            "automaticamente no sistema. Você gostaria que eu encaminhasse o atendimento ao responsável para concluir esse ajuste com você?")


# ===================================================================== adiamento
def expandir_adiamento(n: dict) -> list[dict]:
    membros = n.get("grupoPedidos") if isinstance(n.get("grupoPedidos"), list) and len(n["grupoPedidos"]) > 1 else None
    if not membros:
        return [dict(n)]
    saida = []
    for m in membros:
        datas = sorted((e.get("data") for e in (m.get("entregas") or []) if e.get("data")), key=C.data_num)
        saida.append({**n, "pedidoPrincipal": n.get("pedidoLider"), "pedidoLider": str(m.get("pedidoLider")),
                      "dataPrevistaOriginal": datas[0] if datas else n.get("dataPrevistaOriginal")})
    return saida


def montar_url_adiamento(html: str, p: dict, base: str) -> dict:
    from ..integracoes.intranet import url_com_query
    itens = []
    for tag in re.findall(r"<input\b[^>]*>", html, re.I):
        if not re.search(r"""name\s*=\s*["']?item\[\]["']?""", tag, re.I):
            continue
        v = re.search(r"""value\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag, re.I)
        if v:
            itens.append((v.group(1) if v.group(1) is not None else v.group(2) if v.group(2) is not None else v.group(3) or "").replace("&amp;", "&"))
    itens = C.unicos(itens)
    if not itens:
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html)).strip()
        return {"urlAlterar": None, "qtdItens": 0, "dataISO": None, "pedidoLider": p.get("pedidoLider"),
                "erroAdiamento": f"Não encontrei os itens do formulário para o pedido {p.get('pedidoLider')}. Resposta: {txt[:250]}"}
    iso = "-".join(reversed(p["dataSolicitada"].split("/")))
    obs = (f"ADIAMENTO SOLICITADO PELO CLIENTE: data alterada de {p.get('dataPrevistaOriginal')} para "
           f"{p.get('dataSolicitada')}. Resposta: {p.get('textoCliente')}")
    params = [("data", iso), ("cod_empresa", "11"), ("pedido", p.get("pedidoLider")), ("motivo", "SOLICITACAO DO CLIENTE"),
              ("agendamento", ""), ("observacao", obs), ("opcao[]", "A"), *[("item[]", i) for i in itens]]
    return {"urlAlterar": url_com_query(f"{base}/vdp/altera_data_entrega2.php", params), "qtdItens": len(itens),
            "dataISO": iso, "pedidoLider": p.get("pedidoLider")}


def confirmar_alteracao(n: dict, resultados_brutos: list[tuple[dict, dict, dict]]) -> dict:
    """resultados_brutos: lista de (montar, alvo, resposta_http)."""
    res = []
    for montar, alvo, j in resultados_brutos:
        ok = bool(montar.get("urlAlterar")) and not j.get("error")
        res.append({"pedidoLider": str(montar.get("pedidoLider") if montar.get("pedidoLider") is not None else alvo.get("pedidoLider") or n.get("pedidoLider")),
                    "ok": ok, "resposta": re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(j.get("data") or ""))).strip()[:400],
                    "erro": None if ok else (montar.get("erroAdiamento") or str(j.get("error") or "falha ao alterar na intranet"))})
    tudo_ok = len(res) > 0 and all(r["ok"] for r in res)
    varios = len(res) > 1
    erros = [f"pedido {r['pedidoLider']}: {r['erro']}" if varios else r["erro"] for r in res if not r["ok"]]
    return {**n, "resultadoIntranet": (" | ".join(f"{r['pedidoLider']}: {r['resposta']}" for r in res)[:800] if varios
                                       else (res[0]["resposta"] if res else "")),
            "alteracaoDataConcluida": tudo_ok,
            "erroAdiamento": None if tudo_ok else (" | ".join(erros) or "falha ao alterar na intranet"),
            "resultadosAdiamento": res}


# ===================================================================== planilha / registro único / intranet
def classificar_resposta_sheet(n: dict, alteracao_ok: bool = True) -> list[dict]:
    cat = n.get("categoria") or ""
    pid = str(n.get("pedidoLider") or "").strip()
    pedido_sheet = f"11-{pid}"
    dp = C.loads(n.get("dadosPedido") or "{}", {}) or {}
    orig = dp.get("Pedido") if dp.get("Pedido") is not None else dp.get("pedidoOriginal")
    if orig:
        pedido_sheet = str(orig).strip()
    adiamento_ok = cat == "PEDE_ADIAR" and n.get("adiamentoValido") is True and bool(n.get("dataSolicitada")) and alteracao_ok
    deve, g, h, i = False, "", "", ""
    if cat in ("ACEITA", "ACEITA_PEDE_ADIANTAR") or adiamento_ok:
        deve, g, h, i = True, "SIM", "CONFIRMADO", C.carimbo_br()
    elif cat == "NAO_ACEITA":
        deve, g, h, i = True, "SIM", "CLIENTE NÃO CONCORDA", C.carimbo_br()
    ja = False
    if deve and dp.get("registroContato"):
        ja, deve, g, h, i = True, False, "", "", ""
    membros = dp.get("pedidosGrupo") if isinstance(dp.get("pedidosGrupo"), list) and len(dp["pedidosGrupo"]) > 1 else None
    if membros:
        return [{"deveAtualizar": deve, "sheetG": g, "sheetH": h, "sheetI": i, "jaRegistrado": ja,
                 "pedidoSheet": str(m.get("Pedido") if m.get("Pedido") is not None else f"11-{m.get('pedidoLider')}").strip(),
                 "pedidoLider": str(m.get("pedidoLider") or "").strip(), "categoria": cat, "membro": m, "pedidoPrincipal": pid}
                for m in membros]
    return [{"deveAtualizar": deve, "jaRegistrado": ja, "sheetG": g, "sheetH": h, "sheetI": i, "pedidoSheet": pedido_sheet,
             "pedidoLider": pid, "categoria": cat}]


def localizar_linhas_sheet(alvos: list[dict], rows: list[dict]) -> list[dict]:
    rows = [r for r in rows if r.get("row_number") is not None]
    saida, faltando = [], []
    for cls in alvos:
        alvo = C.n_ped(cls["pedidoSheet"])
        achadas = [r for r in rows if C.n_ped(r.get("Pedido")) == alvo]
        if len(achadas) > 1:
            exata = [r for r in achadas if str(r.get("Pedido")).strip() == cls["pedidoSheet"]]
            if exata:
                achadas = exata
        if not achadas:
            faltando.append(cls["pedidoSheet"])
            continue
        saida.append({**cls, "row_number": achadas[0]["row_number"]})
    if not saida:
        raise ValueError(f"Pedido {', '.join(faltando)} não encontrado na planilha para gravar a resposta do cliente.")
    if faltando:
        for s in saida:
            s["pedidosForaDaPlanilha"] = faltando
    return saida


def montar_registro_unico(n: dict, cls: dict) -> dict | None:
    dp = C.loads(n.get("dadosPedido") or "{}", {}) or {}
    if dp.get("registroContato"):
        return None
    data_ent = (n["dataSolicitada"] if (n.get("categoria") == "PEDE_ADIAR" and n.get("adiamentoValido") is True and n.get("dataSolicitada"))
                else (n.get("dataPrevistaOriginal") or ""))
    dp["registroContato"] = {"em": C.agora_iso_utc(), "origem": "IA", "categoria": n.get("categoria"), "resultado": cls.get("sheetH"),
                             "dataEntrega": data_ent,
                             "pedidos": [str(x) for x in n["pedidosGrupo"]] if n.get("pedidosGrupo") else [str(n.get("pedidoLider"))]}
    return {"id": n.get("id"), "dadosPedido": C.dumps(dp)}


def _data_intranet(valor) -> str:
    s = str(valor or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:$|T)", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", s)
    if m:
        try:
            date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return ""
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return ""


def montar_observacoes_contato(n0: dict, localizados: list[dict], tipo_linha=None) -> list[dict]:
    cat = n0.get("categoria") or ""
    dp0 = C.loads(n0.get("dadosPedido") or "{}", {}) or {}

    def montar(n, dp):
        pedido = str(n.get("pedidoLider") if n.get("pedidoLider") is not None else dp.get("pedidoLider") or "").strip()
        cliente = ""
        for v in (dp.get("clienteLider"), dp.get("Cliente"), dp.get("cliente"), n.get("clienteLider"), n.get("cliente")):
            if v is not None:
                cliente = str(v).strip()
                break
        datas_inf = [e.get("data") for e in dp["entregas"] if e.get("data")] if isinstance(dp.get("entregas"), list) else []
        if not datas_inf and isinstance(n.get("entregas"), list):
            datas_inf = [e if isinstance(e, str) else (e or {}).get("data") for e in n["entregas"]]
            datas_inf = [x for x in datas_inf if x]
        if not datas_inf and n.get("dataPrevistaOriginal"):
            datas_inf.append(n["dataPrevistaOriginal"])
        datas = " E ".join(datas_inf)
        dat = _data_intranet(datas_inf[0] if datas_inf else "")
        obs = ""
        tipo = str(n.get("tipoMensagem") or dp.get("tipoMensagem") or "")
        if not tipo and tipo_linha:
            tipo = str(tipo_linha or "")
        if tipo == "PRIMEIRA_CONFIRMACAO":
            if cat in ("ACEITA", "ACEITA_PEDE_ADIANTAR"):
                dat = _data_intranet(dp.get("dataSistema") or dp.get("entregaLider") or "01/12/2040")
                obs = ("CLIENTE CONTATADO VIA WHATSAPP (1A CONFIRMACAO - PLANEJADOS) E CONFIRMOU O RECEBIMENTO DA MENSAGEM. "
                       "PRAZO DE ENTREGA SERA INFORMADO APOS A POSTAGEM DO PROJETO.")
        elif cat == "ACEITA":
            obs = f"CLIENTE CONTATADO VIA WHATSAPP E CONFIRMOU A DATA DE ENTREGA {datas}."
        elif cat == "ACEITA_PEDE_ADIANTAR":
            obs = (f"CLIENTE CONTATADO VIA WHATSAPP E CONFIRMOU A DATA DE ENTREGA {datas}, PORÉM SOLICITOU ANTECIPAR A ENTREGA. "
                   "CLIENTE ORIENTADO QUE A DATA É A PREVISÃO REGISTRADA NO SISTEMA.")
        elif cat == "PEDE_ADIAR" and n.get("adiamentoValido") is True and n.get("dataSolicitada"):
            dat = _data_intranet(n["dataSolicitada"])
            obs = (f"CLIENTE CONTATADO VIA WHATSAPP E SOLICITOU ADIAMENTO DA ENTREGA DE {n.get('dataPrevistaOriginal') or datas} "
                   f"PARA {n['dataSolicitada']}. PRAZO ALTERADO NO SISTEMA.")
        elif cat == "NAO_ACEITA":
            obs = f"CLIENTE CONTATADO VIA WHATSAPP E NÃO ACEITA A DATA DE ENTREGA {datas}."
        if not obs or not pedido or not dat:
            return None
        return {"pedidoLider": pedido, "clienteLider": C.sem_acento(cliente), "datEntrega": dat,
                "status": "CONFIRMACAO DE DATA DE ENTREGA", "tipoInformacao": "AE",
                "observacao": C.sem_acento(obs).upper()}

    saida = []
    for cls in localizados:
        n, dp = n0, dp0
        m = cls.get("membro")
        if m:
            datas_m = sorted((e.get("data") for e in (m.get("entregas") or []) if e.get("data")), key=C.data_num)
            n = {**n0, "pedidoLider": m.get("pedidoLider"), "tipoMensagem": m.get("tipoMensagem"), "entregas": m.get("entregas"),
                 "dataPrevistaOriginal": datas_m[0] if datas_m else n0.get("dataPrevistaOriginal")}
            dp = {**dp0, "pedidoLider": m.get("pedidoLider"),
                  "clienteLider": m.get("clienteLider") if m.get("clienteLider") is not None else dp0.get("clienteLider"),
                  "entregas": m.get("entregas"), "tipoMensagem": m.get("tipoMensagem"), "dataSistema": m.get("dataSistema"),
                  "entregaLider": m.get("entregaLider")}
        o = montar(n, dp)
        if o:
            saida.append(o)
    return saida


# ===================================================================== chat com o consultor
def montar_chat_consultor(n: dict) -> dict:
    chat = _chat(n)
    ts = C.agora_iso_utc()
    chat.append({"role": "cliente", "texto": str(n.get("textoCliente") or ""), "ts": ts})
    grupo = len(n.get("pedidosGrupo") or []) > 1
    quem = f"{n.get('cliente') or ''} ({'pedidos ' + str(n.get('pedidosTexto')) + ', mensagem única' if grupo else 'pedido ' + str(n.get('pedidoLider'))})"
    reg = n.get("registroAnterior") or None
    quando = ""
    if reg and reg.get("em"):
        ms = C.iso_ms(reg["em"])
        if ms:
            from datetime import datetime
            quando = datetime.fromtimestamp(ms / 1000, C.TZ).strftime("%d/%m/%Y, %H:%M:%S")
    if n.get("tipoResposta") == "ALTERAR_REGISTRO":
        linhas = [f"O cliente {quem} escreveu de novo depois que o contato já foi registrado na planilha e na intranet "
                  f"({(reg.get('resultado') or reg.get('categoria')) if reg else 'registrado'}"
                  f"{', data ' + reg['dataEntrega'] if reg and reg.get('dataEntrega') else ''}{', em ' + quando if quando else ''}).",
                  f"Agora o cliente: {n['resumoIA']}" if n.get("resumoIA") else "",
                  "O registro é feito uma vez só: não alterei a data nem gravei nada de novo. Escreva a orientação e eu passo ao cliente, ou solicite a transferência."]
    elif n.get("tipoResposta") == "FORA_DA_REGRA":
        linhas = [f"O cliente {quem} trouxe um assunto que não está nas regras da automação nem na base de conhecimento.",
                  f"Assunto: {n['assuntoFora']}" if n.get("assuntoFora") else "",
                  f"Resumo: {n['resumoIA']}" if n.get("resumoIA") else "",
                  (f"O contato já estava registrado ({reg.get('resultado') or reg.get('categoria')}"
                   f"{', data ' + reg['dataEntrega'] if reg.get('dataEntrega') else ''}); não gravo de novo.") if reg
                  else "Não respondi o cliente e não registrei nada na planilha nem na intranet.",
                  "Escreva a orientação e eu passo ao cliente (ela também fica salva para eu responder sozinha em casos parecidos). Se for um caso mais sério, solicite a transferência."]
    else:
        linhas = [f"Não consegui entender a resposta do cliente {quem}.",
                  f"Resumo: {n['resumoIA']}" if n.get("resumoIA") else "",
                  "O que devo fazer? Se for algo tranquilo, escreva a orientação e eu passo ao cliente. Se for um caso mais sério, solicite a transferência."]
    chat.append({"role": "ia", "tipo": "pergunta", "texto": "\n".join(x for x in linhas if x), "ts": ts})
    return {"id": n.get("id"), "pedidoLider": n.get("pedidoLider"), "contactId": n.get("contactId"), "cliente": n.get("cliente"),
            "chatConsultor": C.dumps(chat)}


def montar_duvida_vigilancia(n: dict) -> dict:
    ts = C.agora_iso_utc()
    chat = _chat(n)
    chat.append({"role": "cliente", "texto": str(n.get("textoCliente") or ""), "ts": ts})
    pergunta = "\n".join(x for x in [
        f"O cliente {n.get('cliente') or ''} (pedido {n.get('pedidoLider')}) escreveu depois de confirmar a entrega e parece ter uma dúvida.",
        f"Resumo: {n['vigResumo']}" if n.get("vigResumo") else "",
        "Não encontrei essa resposta na minha base. O que devo responder? Escreva a orientação e eu passo ao cliente; ela também fica salva para eu responder sozinha em casos parecidos. Se for algo mais sério, solicite a transferência."] if x)
    chat.append({"role": "ia", "tipo": "pergunta", "texto": pergunta, "ts": ts})
    return {"id": n.get("id"), "pedidoLider": n.get("pedidoLider"), "contactId": n.get("contactId"), "cliente": n.get("cliente"),
            "chatConsultor": C.dumps(chat)}


def registrar_resposta_automatica(j: dict) -> dict:
    ts = C.agora_iso_utc()
    chat = _chat(j)
    chat.append({"role": "cliente", "texto": str(j.get("textoCliente") or ""), "ts": ts})
    chat.append({"role": "ia", "tipo": "envio", "texto": "Resposta automática (base de conhecimento): " + str(j.get("respostaBase")), "ts": ts})
    return {"id": j.get("id"), "chatConsultor": C.dumps(chat), "kbId": j.get("kbId"), "kbUsos": j.get("kbUsos")}
