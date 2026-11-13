"""Fluxo 1 — contatos DigiSac, montagem das mensagens e agrupamento (nós Code da v28)."""
import re
from urllib.parse import unquote

from .. import comum as C
from ..integracoes.digisac import SERVICES, SERVICE_CRIACAO
from .f1_extracao import IGNORAR_NOME, registros_emails, EMAIL_TESTE

PLACEHOLDERS = ["01/01/2027"]


# ------------------------------------------------------------------ Montar e-mail ao consultor (reincidência)
MODO_TESTE_EMAIL_CONSULTOR = False  # v28: const MODO_TESTE = false
SETOR_ATENDENTE = "0104-CENTRAL DE RELACIONAMENTO"


def buscar_atendente(responsavel: str, regs: list[dict]) -> dict:
    tokens = [t for t in C.sem_acento(_limpa(responsavel)).upper().split(" ") if t and t not in IGNORAR_NOME]
    if not tokens:
        return {"email": None, "status": "SEM_RESPONSAVEL"}

    def confere(nome):
        tn = [x for x in nome.split(" ") if x]
        return all(any(x == t or (len(t) >= 4 and x.startswith(t)) for x in tn) for t in tokens)

    cand = [r for r in regs if SETOR_ATENDENTE in r["setor"] and confere(r["nome"])]
    nomes = C.unicos(c["nome"] for c in cand)
    emails = C.unicos(c["email"] for c in cand)
    if not emails:
        return {"email": None, "status": "NAO_ENCONTRADO"}
    if len(nomes) > 1:
        return {"email": None, "status": "AMBIGUO_NOMES: " + " / ".join(nomes)}
    if len(emails) == 1:
        return {"email": emails[0], "status": "OK"}
    partes = [p for p in nomes[0].split(" ") if p and p not in IGNORAR_NOME]
    primeiro, ultimo = partes[0].lower(), partes[-1].lower()
    pref = [e for e in emails if e.split("@")[0].startswith(primeiro + ".") and ultimo in e.split("@")[0]]
    return ({"email": pref[0], "status": "OK_NOME_REPETIDO"} if len(pref) == 1
            else {"email": None, "status": "AMBIGUO_EMAILS: " + " / ".join(emails)})


def _limpa(s) -> str:
    s = re.sub(r"<[^>]*>", " ", str(s or "")).replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def montar_emails_consultor_reincidencia(pedidos_tardia: list[dict], html_emails: str) -> list[dict]:
    vai = ["ESCALAR", "JA_ESCALADO"]
    vistos, itens = set(), []
    for p in pedidos_tardia:
        if p.get("acaoReincidencia") not in vai:
            continue
        k = C.n_ped(p.get("pedidoLider") or p.get("Pedido"))
        if k:
            if k in vistos:
                continue
            vistos.add(k)
        itens.append(p)
    itens.sort(key=lambda p: (0 if p.get("acaoReincidencia") == "ESCALAR" else 1,
                              int(C.n_ped(p.get("pedidoLider") or p.get("Pedido")) or 0)))
    if not itens:
        return []
    regs = registros_emails(html_emails, 5, 4, "setor")
    grupos: dict[str, list] = {}
    for p in itens:
        grupos.setdefault(str(p.get("RESPONSÁVEL") or "").strip() or "SEM RESPONSÁVEL", []).append(p)

    def num_pedido(p):
        bruto = str(p.get("Pedido") or "").strip()
        if bruto:
            return re.sub(r"^\((\d+)\)\s*", r"\1-", bruto)
        return "11-" + str(p["pedidoLider"]) if p.get("pedidoLider") else "-"

    def fmt_dia(iso):
        a = str(iso).split("-")
        return f"{a[2]}/{a[1]}" if len(a) >= 3 and a[2] and a[1] else iso

    def telefones(p):
        t = C.unicos(x for x in (str(p.get("telefone") or "").strip(), str(p.get("telefone2") or "").strip()) if x)
        return " / ".join(t) or "-"

    th = lambda t: f'<th style="border:1px solid #999;padding:4px 8px;background:#f2f2f2;font-size:12px;">{t}</th>'  # noqa: E731
    td = lambda t: f'<td style="border:1px solid #999;padding:4px 8px;font-size:12px;">{C.esc3(t)}</td>'  # noqa: E731
    saida = []
    for responsavel, lista in grupos.items():
        at = buscar_atendente(responsavel, regs)
        nome_fmt = C.capitalizar(responsavel.split()[0]) if responsavel.split() else responsavel
        linhas = "".join(f"""<tr>
    {td(num_pedido(p))}
    {td(p.get('Cliente') or p.get('clienteLider') or '-')}
    {td(telefones(p))}
    {td((p.get('cidadeEntrega') or '-') + '/' + (p.get('ufEntrega') or '-'))}
    {td(', '.join(fmt_dia(d) for d in (p.get('diasSemRetorno') or [])))}
    {td('Já encaminhado antes' if p.get('acaoReincidencia') == 'JA_ESCALADO' else '1º aviso')}
  </tr>""" for p in lista)
        aviso = (f'<p style="color:#c00;">[TESTE] destinatário real: {C.esc3(at["email"] or "não encontrado")} '
                 f'(responsável: {C.esc3(responsavel)}; busca: {C.esc3(at["status"])})</p>') if MODO_TESTE_EMAIL_CONSULTOR else ""
        nota = ('<p style="font-size:12px;color:#555;">"Já encaminhado antes": o pedido já tinha sido passado a você num dia '
                'anterior e continua sem confirmação na planilha.</p>\n') if any(p.get("acaoReincidencia") == "JA_ESCALADO" for p in lista) else ""
        html = f"""<div style="font-family:Arial,sans-serif;font-size:14px;">
{aviso}
<p>{C.saudacao()}, {C.esc3(nome_fmt)}. Tudo bem?</p>
<p>Os pedidos abaixo ficaram sem confirmar a data de entrega em 2 dias no fluxo automático e voltaram hoje na planilha para confirmação. O template não foi reenviado: por favor, tente contato com o cliente por outro meio (ligação, e-mail ou representante).</p>
<table style="border-collapse:collapse;font-family:Arial,sans-serif;">
<tr>{''.join(th(t) for t in ['Pedido', 'Cliente', 'Telefone(s)', 'Destino', 'Dias sem retorno', 'Situação'])}</tr>
{linhas}
</table>
{nota}<p>Obrigado!</p>
</div>"""
        para = EMAIL_TESTE if MODO_TESTE_EMAIL_CONSULTOR else (at["email"] or EMAIL_TESTE)
        prefixo = f"{'[TESTE] ' if MODO_TESTE_EMAIL_CONSULTOR else ''}{'' if at['email'] else '[SEM E-MAIL DO ATENDENTE] '}"
        nums = ", ".join(str(p.get("pedidoPlanilha") or p.get("pedidoLider")) for p in lista)
        saida.append({"para": para, "html": html, "atendente": responsavel, "emailAtendente": at["email"],
                      "status": at["status"],
                      "assunto": f"{prefixo}Pedidos sem confirmação há 2 dias - contato alternativo ({len(lista)}): {nums}"})
    return saida


# ------------------------------------------------------------------ Preparar Tentativas Digisac
def preparar_tentativas(p: dict) -> dict:
    def sem_celular(motivo):
        return {**p, "phone": None, "semCelularValido": True,
                "rota": {**(p.get("rota") or {}), "telefoneIdentificado": False, "semPendencia": False,
                         "status": "PENDENTE", "motivoPendencia": motivo}}
    tels = C.unicos(t for t in (C.normalizar_celular(p.get("telefone")), C.normalizar_celular(p.get("telefone2"))) if t)
    if not tels:
        return sem_celular("TELEFONE_FIXO_OU_INVALIDO")
    tent = []
    for tel in tels:
        k = C.chave_tel(tel)
        if not k:
            continue
        dig = re.sub(r"\D", "", tel)
        for sid in SERVICES:
            tent.append({"phone": f"%{dig[-8:]}", "phoneCompleto": tel, "serviceId": sid, "chave": k})
    if not tent:
        return sem_celular("TELEFONE_FIXO_OU_INVALIDO")
    return {**p, "phone": tels[0], "telefones": tels, "cpf": C.normalizar_cpf(p.get("cpf")), "tentativas": tent,
            "semCelularValido": False, "tentativaAtual": 0, "serviceCriacao": SERVICE_CRIACAO}


# ------------------------------------------------------------------ Verificar Busca Digisac
def verificar_busca(busca: dict, origem: dict) -> dict:
    erro = bool(busca.get("error"))
    lista = busca.get("data") if isinstance(busca.get("data"), list) else []
    contato = next((c for c in lista if C.chave_tel(((c or {}).get("data") or {}).get("number")) == origem.get("chaveBusca")), None)
    if not contato:
        return {**origem, "achou": False, "errosBusca": (origem.get("errosBusca") or 0) + (1 if erro else 0)}
    tent = (origem.get("tentativas") or [])
    atual = tent[origem.get("tentativaAtual", 0)] if origem.get("tentativaAtual", 0) < len(tent) else {}
    phone = C.normalizar_celular((contato.get("data") or {}).get("number")) or atual.get("phoneCompleto") or origem.get("phone")
    return {**origem, "achou": True, "contato": contato, "statusBusca": "ENCONTRADO",
            "contactId": contato.get("id"), "serviceId": contato.get("serviceId"), "phone": phone}


def nome_contato(p: dict) -> str:
    """internalName do 'Criar Contato'."""
    if p.get("cpf"):
        return f"{p['cpf']} - {p.get('clienteLider') or ''}".strip()
    return p.get("clienteLider") or "SEM NOME"


# ------------------------------------------------------------------ itens da página situacao_pedidos
def extrair_itens_saldo(html: str, pedido_lider) -> list[dict]:
    ident = f"(11)-{str(pedido_lider).strip()}"
    mapa = {}
    for linha in re.findall(r"<tr\b[^>]*>[\s\S]*?</tr>", html, re.I):
        if ident not in C.limpar(re.sub(r"<[^>]+>", " ", linha)):
            continue
        cel = [C.sem_tags(c) for c in re.findall(r"<td\b[^>]*>[\s\S]*?</td>", linha, re.I)]
        if len(cel) < 7:
            continue
        ped, situacao, data_ent, codigo, desc = cel[0], cel[2], cel[3], cel[5], cel[6]
        qtd = cel[7] if len(cel) > 7 else None
        if ident not in ped or not C.RE_DATA_BR.match(data_ent) or not codigo:
            continue
        mapa.setdefault(f"{codigo}|{data_ent}", {"codigoItem": codigo, "descricao": desc, "quantidade": qtd,
                                                 "dataEntrega": data_ent, "situacao": situacao})
    return list(mapa.values())


def _data_valida(d) -> bool:
    if not d or d in PLACEHOLDERS:
        return False
    try:
        return C.parse_br(d) >= C.agora().date()
    except (ValueError, TypeError):
        return False


RODAPE = ("Lembrando que se trata de uma data *prevista*. Se houver qualquer impedimento para receber, é só nos "
          "avisar por aqui.\n\nPodemos confirmar a data de entrega?")


def _base_saida(p: dict) -> dict:
    """Campos copiados com p.x no JS somem do JSON quando não existem (undefined); os com '?? null' ficam."""
    saida = {}
    for k in ("pedidoLider",):
        if k in p:
            saida[k] = p[k]
    saida["Pedido"] = p.get("Pedido") if p.get("Pedido") is not None else p.get("pedidoOriginal")
    for k in ("clienteLider", "RESPONSÁVEL", "referencia", "tipoMovel"):
        if k in p:
            saida[k] = p[k]
    saida.update({"phone": p.get("phone"), "telefones": p.get("telefones") or [], "cpf": p.get("cpf"),
                  "contactId": p.get("contactId"), "serviceId": p.get("serviceId"),
                  "statusBusca": p.get("statusBusca")})
    return saida


# ------------------------------------------------------------------ Montar Mensagem Soltos
def montar_mensagem_soltos(p: dict, html: str) -> dict:
    motivos = []
    if not p.get("phone"):
        motivos.append("TELEFONE_INVALIDO")
    if not p.get("contactId"):
        motivos.append("SEM_CONTATO_DIGISAC")
    itens = extrair_itens_saldo(html, p.get("pedidoLider")) or (p.get("entregaPorProduto") or [])
    pend = sorted((x for x in (p.get("datasCalculadas") or []) if _data_valida(x.get("calculada"))),
                  key=lambda x: C.data_num(x["calculada"]))
    if not p.get("datasCalculadas"):
        motivos.append("SEM_DATAS_CALCULADAS")
    elif not pend:
        motivos.append("TODAS_ENTREGAS_VENCIDAS")
    mapa = {x["original"]: x["calculada"] for x in pend}
    grupos: dict[str, list] = {}
    for it in itens:
        nova = mapa.get(it.get("dataEntrega"))
        if nova:
            grupos.setdefault(nova, []).append(it)
    entregas = sorted(({"data": d, "itens": its} for d, its in grupos.items()), key=lambda e: C.data_num(e["data"]))
    if pend and not entregas:
        motivos.append("SEM_ITENS_PEDIDO")
    parcial = len(entregas) > 1
    nome = C.primeiro_nome(p.get("clienteLider"))
    abertura = f"{f'Olá, {nome}!' if nome else 'Olá!'} Aqui é da *Líder*."
    mensagem = None
    if not motivos:
        if not parcial:
            linhas = [abertura, "", f"A previsão de entrega do seu pedido *{p.get('pedidoLider')}* é *{entregas[0]['data']}*.",
                      "", "*Produtos do pedido:*", "\n".join(C.linha_item(i) for i in entregas[0]["itens"]), "", RODAPE]
        else:
            linhas = [abertura, "", f"Seu pedido *{p.get('pedidoLider')}* será entregue em mais de uma data, conforme a produção de cada item:",
                      "", "\n\n".join(f"📅 *{e['data']}*\n" + "\n".join(C.linha_item(i) for i in e["itens"]) for e in entregas),
                      "", RODAPE]
        mensagem = "\n".join(linhas)
    return {**_base_saida(p), "tipoMensagem": "PARCIAL" if parcial else "UNICA", "entregas": entregas,
            "qtdItens": len(itens), "mensagem": mensagem, "bloqueado": len(motivos) > 0,
            "motivosBloqueio": ", ".join(C.unicos(motivos))}


# ------------------------------------------------------------------ Montar Mensagem Planejados
VIDEO_URL = "/files/LIDER.mp4"
PREFIXOS_PROJETO = ["1AMBAN", "1AMCOZ", "1AMDES", "1AMGOU", "1AMSER", "1COORP", "1ESPAU", "1MOSPL", "1PROIN",
                    "1QUCAS", "1QUCLO", "1QUHOS", "1QUOFF", "1QUROU", "1QUSOL", "1SLEST", "1SLJAN", "1SLTEL"]
EXTENSOES_PROJETO = ["ZIP", "RAR", "7Z"]


def norm_codigo(c) -> str:
    return re.sub(r"\.+$", "", str(c or "").strip().upper())


def exige_projeto(codigo) -> bool:
    c = norm_codigo(codigo)
    return any(c.startswith(p) for p in PREFIXOS_PROJETO)


def indice_projetos(html: str) -> tuple[dict, bool]:
    arquivos = set()
    for m in re.finditer(r"""arquivo=([^"'&<>\s]+)""", html, re.I):
        try:
            nome = unquote(m.group(1), errors="strict")
        except UnicodeDecodeError:
            nome = m.group(1)
        arquivos.add(nome.strip().upper())
    idx: dict[str, list] = {}
    for arq in arquivos:
        m = re.match(r"^(\d+)-(\d+)-(.+?)-(\d+)-(\d{14})\.([A-Z0-9]+)$", arq)
        if not m or m.group(6) not in EXTENSOES_PROJETO:
            continue
        idx.setdefault(f"{int(m.group(1))}|{int(m.group(2))}|{norm_codigo(m.group(3))}", []).append(arq)
    valida = bool(re.search("arquivo=", html, re.I)) and len(arquivos) > 2
    return idx, valida


def linha_item_planejado(it: dict) -> str:
    """CORREÇÃO pedida em 13/11 (diverge da v28 de propósito): a v28 tirava todos os pontos da
    quantidade ("1.0" virava 10x). Agora usa a mesma leitura dos móveis soltos ("1.0" = 1, "2,00" = 2)."""
    return C.linha_item(it)


def _itens_ordem(html: str, pedido: str) -> list[dict]:
    texto = C.sem_tags(html)
    pm = re.search(r"PEDIDO:\s*(\d+)", texto, re.I)
    if not pm or int(pm.group(1)) != int(pedido or 0):
        return []
    mapa, data_atual = {}, None
    rx = re.compile(r'ENTREGA:\s*(?:<[^>]+>|\s)*(\d{2}/\d{2}/\d{4})|<td[^>]*width="150"[^>]*>([\s\S]*?)</td>\s*'
                    r'<td[^>]*width="50"[^>]*>([\s\S]*?)</td>\s*<td[^>]*>([\s\S]*?)</td>', re.I)
    for m in rx.finditer(html):
        if m.group(1):
            data_atual = m.group(1)
            continue
        codigo = C.sem_tags(m.group(2))
        if not re.match(r"^[0-9A-Z][0-9A-Z.\-]{4,}$", codigo, re.I) or not data_atual:
            continue
        mapa.setdefault(f"{codigo}|{data_atual}", {"codigoItem": codigo, "descricao": C.sem_tags(m.group(4)),
                                                  "quantidade": C.sem_tags(m.group(3)), "dataEntrega": data_atual,
                                                  "situacao": None})
    return list(mapa.values())


def montar_mensagem_planejados(p: dict, html: str, idx_proj: dict, lista_valida: bool) -> dict:
    ano = lambda d: int(str(d).split("/")[2]) if len(str(d).split("/")) > 2 and str(d).split("/")[2].isdigit() else 0  # noqa: E731
    absurda = lambda d: ano(d) >= 2040  # noqa: E731
    pedido = str(p.get("pedidoLider")).strip()
    itens_link, valida = [], False
    if re.search(r"Saldo de pedidos entre os dias", html, re.I):
        valida, itens_link = True, extrair_itens_saldo(html, pedido)
    elif re.search(r"Ordem de Expedi", html, re.I):
        valida, itens_link = True, _itens_ordem(html, pedido)
    planej = [it for it in itens_link if re.search("PLANEJAD", f"{it['codigoItem']} {it['descricao']}", re.I)
              or exige_projeto(it["codigoItem"])]
    codigos = C.unicos(norm_codigo(it["codigoItem"]) for it in itens_link if exige_projeto(it["codigoItem"]))
    try:
        num_ped = int(pedido)
    except ValueError:
        num_ped = pedido
    proj = [{"codigoItem": c, "postado": bool(idx_proj.get(f"11|{num_ped}|{c}")), "arquivos": idx_proj.get(f"11|{num_ped}|{c}", [])}
            for c in codigos]
    sem_proj = [x["codigoItem"] for x in proj if not x["postado"]]
    motivos = []
    if not p.get("phone"):
        motivos.append("TELEFONE_INVALIDO")
    if not p.get("contactId"):
        motivos.append("SEM_CONTATO_DIGISAC")
    if not valida:
        motivos.append("PAGINA_SITUACAO_INVALIDA")
    if valida and not itens_link:
        motivos.append("ITENS_NAO_LOCALIZADOS")
    tem_absurda = any(absurda(it["dataEntrega"]) for it in planej) or any(
        absurda(d) for d in [*(p.get("datasEntrega") or []), p.get("entregaLider")] if d)
    falta = len(sem_proj) > 0
    if not tem_absurda and codigos and not lista_valida:
        motivos.append("LISTA_PROJETOS_INDISPONIVEL")
    primeira = len(planej) == 0 or tem_absurda or falta
    crit = []
    if not planej:
        crit.append("SEM_ITENS_PLANEJADOS")
    if tem_absurda:
        crit.append("DATA_FICTICIA")
    if falta:
        crit.append(f"PROJETO_NAO_POSTADO ({', '.join(sem_proj)})")
    nome = C.primeiro_nome(p.get("clienteLider"))
    saud = f"Olá, {nome}!" if nome else "Olá!"
    entregas, mensagem = [], None
    if primeira:
        if not motivos:
            mensagem = "\n".join([
                saud, "",
                f"O seu pedido nº *{p.get('pedidoLider')}* está em nossas mãos e já está sendo cuidadosamente desenvolvido. Nesse momento, nossos designers estão finalizando os detalhes do seu projeto personalizado para garantir que seus móveis planejados sejam perfeitos para o seu ambiente.",
                "",
                "Para que possamos encaminhar os projetos finais para a fábrica, precisaremos das medidas definitivas do local de instalação. Isso garantirá que a fabricação e a montagem sejam realizadas com precisão. Após a aprovação final do projeto e a liberação para a fábrica, o prazo de entrega será definido de acordo com o calendário vigente de postagens.",
                "",
                "Dessa forma, o prazo poderá variar conforme a data em que o pedido for efetivamente postado para produção, seguindo a tabela de prazos da fábrica. Assim que o pedido for postado, entraremos em contato novamente para informar a previsão de entrega de acordo com o prazo correspondente à data de postagem.",
                "",
                "Nossa equipe também fará contato com antecedência para agendar a medição do ambiente.",
                "",
                "Pedimos, por gentileza, que confirme o recebimento da mensagem anterior. Ficamos no aguardo da sua confirmação."])
    else:
        mapa = {x["original"]: x["calculada"] for x in (p.get("datasCalculadas") or [])}
        grupos: dict[str, list] = {}
        for it in planej:
            nova = mapa.get(it["dataEntrega"])
            if not nova:
                motivos.append("DATA_ITEM_SEM_CALCULO")
                continue
            if not _data_valida(nova):
                continue
            grupos.setdefault(nova, []).append(it)
        entregas = sorted(({"data": d, "itens": its} for d, its in grupos.items()), key=lambda e: C.data_num(e["data"]))
        if not entregas:
            motivos.append("TODAS_ENTREGAS_VENCIDAS")
        if not motivos:
            abertura = f"{saud} Aqui é da *Líder*."
            if len(entregas) == 1:
                mensagem = "\n".join([abertura, "", f"A previsão de entrega dos seus móveis planejados do pedido *{p.get('pedidoLider')}* é *{entregas[0]['data']}*.",
                                      "", "*Produtos do pedido:*", "\n".join(linha_item_planejado(i) for i in entregas[0]["itens"]), "", RODAPE])
            else:
                mensagem = "\n".join([abertura, "", f"Seu pedido *{p.get('pedidoLider')}* será entregue em mais de uma data:", "",
                                      "\n\n".join(f"\U0001F4C5 *{e['data']}*\n" + "\n".join(linha_item_planejado(i) for i in e["itens"]) for e in entregas),
                                      "", RODAPE])
    datas_sist = [*(p.get("datasEntrega") or []), p.get("entregaLider")]
    return {**_base_saida(p), "tipoMensagem": "PRIMEIRA_CONFIRMACAO" if primeira else "SEGUNDA_CONFIRMACAO",
            "entregaLider": p.get("entregaLider"), "datasEntrega": p.get("datasEntrega") or [],
            "dataSistema": next((d for d in datas_sist if d and absurda(d)), None) or p.get("entregaLider"),
            "criteriosPrimeiraConfirmacao": ", ".join(crit), "anexoUrl": VIDEO_URL if primeira else None,
            "entregas": entregas, "mensagem": mensagem, "qtdItensLink": len(itens_link),
            "qtdItensPlanejados": len(planej), "projetosPorItem": proj, "itensSemProjeto": sem_proj,
            "bloqueado": len(motivos) > 0, "motivosBloqueio": ", ".join(C.unicos(motivos))}


# ------------------------------------------------------------------ Agrupar pedidos do mesmo cliente
AGRUPAVEL = ["UNICA", "PARCIAL", "SEGUNDA_CONFIRMACAO"]


def agrupar_pedidos(itens: list[dict], tardias: list[str]) -> list[dict]:
    def entregas_ok(j):
        ent = j.get("entregas")
        return isinstance(ent, list) and len(ent) > 0 and all(
            C.RE_DATA_BR.match(str((e or {}).get("data") or "")) and isinstance(e.get("itens"), list) and e["itens"]
            and all(str((it or {}).get("descricao") or "").strip() for it in e["itens"]) for e in ent)

    chave = lambda j: str(j.get("contactId") or "").strip()  # noqa: E731

    def pode(j):
        return (not j.get("bloqueado") and bool(str(j.get("mensagem") or "").strip()) and bool(chave(j))
                and str(j.get("tipoMensagem") or "") in AGRUPAVEL and C.n_ped(j.get("pedidoLider")) not in tardias
                and entregas_ok(j))

    grupos: dict[str, list[int]] = {}
    for idx, j in enumerate(itens):
        if not pode(j):
            continue
        g = grupos.setdefault(chave(j), [])
        if not any(C.n_ped(itens[i].get("pedidoLider")) == C.n_ped(j.get("pedidoLider")) for i in g):
            g.append(idx)
    saida = [dict(j) for j in itens]
    for idxs in grupos.values():
        if len(idxs) < 2:
            continue
        idxs.sort(key=lambda i: int(C.n_ped(itens[i].get("pedidoLider")) or 0))
        mj = [itens[i] for i in idxs]
        principal = mj[0]
        membros = [{"pedidoLider": str(j.get("pedidoLider")), "Pedido": j.get("Pedido"), "clienteLider": j.get("clienteLider"),
                    "RESPONSÁVEL": j.get("RESPONSÁVEL"), "tipoMovel": j.get("tipoMovel"), "tipoMensagem": j.get("tipoMensagem"),
                    "entregas": [{"data": e["data"], "itens": [{"descricao": x.get("descricao"), "quantidade": x.get("quantidade")}
                                                               for x in e["itens"]]} for e in j["entregas"]],
                    "dataSistema": j.get("dataSistema"), "entregaLider": j.get("entregaLider")} for j in mj]
        todas = sorted(C.unicos(e["data"] for m in membros for e in m["entregas"]), key=C.data_num)
        uma = len(todas) == 1
        peds = [f"*{m['pedidoLider']}*" for m in membros]
        rotulo = lambda m: f"Pedido {m['pedidoLider']}{' (móveis planejados)' if m['tipoMovel'] == 'Planejados' else ''}"  # noqa: E731
        abertura = str(principal.get("mensagem")).split("\n")[0].strip() or "Olá! Aqui é da *Líder*."
        if uma:
            corpo = [f"A previsão de entrega dos seus pedidos {C.lista_txt(peds)} é *{todas[0]}*.", "",
                     "\n\n".join(f"*Produtos do {re.sub(r'^Pedido', 'pedido', rotulo(m))}:*\n"
                                 + "\n".join(C.linha_item(i) for e in m["entregas"] for i in e["itens"]) for m in membros)]
        else:
            corpo = [f"Seus pedidos {C.lista_txt(peds)} têm as seguintes previsões de entrega:", "",
                     "\n\n".join(f"📦 *{rotulo(m)}*\n" + "\n".join(
                         f"📅 *{e['data']}*\n" + "\n".join(C.linha_item(i) for i in e["itens"])
                         for e in sorted(m["entregas"], key=lambda e: C.data_num(e["data"]))) for m in membros)]
        rodape = (RODAPE if uma else
                  "Lembrando que se trata de datas *previstas*. Se houver qualquer impedimento para receber, é só nos "
                  "avisar por aqui.\n\nPodemos confirmar as datas de entrega?")
        mensagem = "\n".join([abertura, "", *corpo, "", rodape])
        saida[idxs[0]] = {**principal, "mensagemIndividual": principal.get("mensagem"), "mensagem": mensagem,
                          "tipoMensagem": "AGRUPADA", "tipoMensagemOriginal": principal.get("tipoMensagem"),
                          "pedidosGrupo": membros, "qtdPedidosGrupo": len(membros)}
        # entregas do principal: para cada data, os itens de cada membro com essa data
        # (m.entregas.find(e => e.data === data)?.itens no JS)
        saida[idxs[0]]["entregas"] = [{"data": d, "itens": [x for m in membros
                                                           for x in (next((e["itens"] for e in m["entregas"] if e["data"] == d), []))]}
                                      for d in todas]
        for i in idxs[1:]:
            saida[i] = {**itens[i], "agrupadoEm": str(principal.get("pedidoLider")),
                        "pedidosGrupoNumeros": [m["pedidoLider"] for m in membros]}
    return saida
