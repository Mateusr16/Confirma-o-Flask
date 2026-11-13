"""Fluxo 1 — funções puras de leitura do HTML da intranet e de cálculo (sem I/O).

Cada função corresponde a um nó Code da v28 e mantém o mesmo nome no docstring.
"""
import math
import re

from .. import comum as C

UFS_VALIDAS = ["MG", "RJ", "SP", "ES", "BA", "DF"]

RESPONSAVEIS_PLANEJADOS = ["ALISSON", "BRENDA COSTA", "LUANA", "MIRINHA", "MARIA LUIZA", "QUEZIA"]
RESPONSAVEIS_SOLTOS = ["BRENDA SOUSA", "DANIELA", "JOYCE", "MARIANA", "RAYNNER", "PEDRO", "NICOLE", "TATIANA"]


# ------------------------------------------------------------------ Preparar Pedido
def preparar_pedido(linha: dict) -> dict:
    pedido_original = str(linha.get("Pedido") or "").strip()
    grupos = re.findall(r"\d+", pedido_original)
    if not grupos:
        return {**linha, "pedidoOriginal": pedido_original, "pedido": None,
                "erro": "Não foi possível identificar o número do pedido"}
    return {**linha, "pedidoOriginal": pedido_original, "pedido": grupos[-1][-7:]}


# ------------------------------------------------------------------ Extrair Dados Pedido
def _limpar_html(t) -> str:
    t = re.sub(r"<br\s*/?>", " ", str(t or ""), flags=re.I)
    return C.limpar(re.sub(r"<[^>]+>", " ", t))


def html_eh_tela_login(html: str) -> bool:
    return bool(re.search(r"""name=["']?senha["']?""", html, re.I) and
                re.search(r"""name=["']?usuario["']?""", html, re.I))


def extrair_dados_pedido(html: str, planilha: dict) -> dict:
    responsavel = planilha.get("RESPONSÁVEL") or None
    pedido_planilha = planilha.get("Pedido")
    cliente_planilha = planilha.get("Cliente")
    motivo_planilha = str(planilha.get("MOTIVO") or "").strip()
    confirmado_planilha = str(planilha.get("CONFIRMADO") or "").strip()
    pedido_fallback = planilha.get("pedido") or (
        re.sub(r"\D", "", str(pedido_planilha))[-7:] if pedido_planilha else None)

    texto = _limpar_html(html)

    m = re.search(r"PEDIDO:\s*(\d+)", texto, re.I)
    pedido_lider = m.group(1) if m else pedido_fallback

    cancelado_intranet = "CANCELADO" in texto
    nao_localizado = (not cancelado_intranet) and (not m or len(texto) < 60)
    eh_cancelado = cancelado_intranet or nao_localizado
    motivo_cancel = "PEDIDO CANCELADO" if cancelado_intranet else ("PEDIDO NÃO LOCALIZADO NA INTRANET" if nao_localizado else None)
    status_cancel = "PEDIDO_CANCELADO" if cancelado_intranet else ("PEDIDO_NAO_LOCALIZADO" if nao_localizado else None)

    m_dp = re.search(r"PEDIDO:\s*\d+\s*/\s*\d+\s*(\d{2}/\d{2}/\d{4})", texto, re.I)
    data_pedido = m_dp.group(1) if m_dp else None

    m_ent = re.search(r"ENTREGA:\s*(\d{2}/\d{2}/\d{4})", texto, re.I)
    entrega_lider = m_ent.group(1) if m_ent else None
    datas_entrega = re.findall(r"ENTREGA:\s*(\d{2}/\d{2}/\d{4})", texto, re.I)

    m_sit = re.search(r"Sit\.\s*:\s*([A-Z])", texto, re.I)
    situacao = "CANCELADO" if eh_cancelado else (m_sit.group(1) if m_sit else None)

    observacao, dias_adic = None, 0
    m_obs = re.search(r"<font[^>]*>\s*(CONSIDERAR\s+MAIS\s+(\d+)\s+DIAS\s+ÚTEIS[^<]*)</font>", html, re.I)
    if m_obs:
        observacao = _limpar_html(m_obs.group(1))
        dias_adic = int(m_obs.group(2))

    m_cli = re.search(r"Sit\.\s*:\s*[A-Z]\s+(.+?)\s+(\d{10,20})(?=\s|$)", texto, re.I)
    cliente_lider = m_cli.group(1).strip() if m_cli else (cliente_planilha or None)
    cpf = m_cli.group(2) if m_cli else None

    telefones = C.unicos(t for t in re.findall(r"\b\d{10,11}\b", texto) if t != cpf)
    telefone = telefones[0] if telefones else None
    telefone2 = telefones[1] if len(telefones) > 1 else None

    m_ref = re.search(r"([A-ZÀ-Ú][A-ZÀ-Ú\s.']+?)\s*\(\s*([A-ZÀ-Ú][A-ZÀ-Ú0-9\s.\-']*?)\s*\)(?=\s*NATUREZA)", texto)
    referencia = f"{C.limpar(m_ref.group(1))} ({C.limpar(m_ref.group(2))})" if m_ref else None

    endereco = bairro = cidade = uf = cep = None
    m_end = re.search(r"<b>\s*ENTREGA\s*</b>\s*:\s*([\s\S]*?)<br\s*/?>", html, re.I)
    if m_end:
        end_txt = _limpar_html(m_end.group(1))
        partes = re.match(r"^(.+?)\s*-\s*([^,]+?)\s*,\s*(.+?)\s*-\s*([A-Z]{2})\s*\.?\s*$", end_txt, re.I)
        if partes:
            endereco, bairro, cidade, uf = (C.limpar(partes.group(i)) for i in range(1, 5))
        else:
            endereco = end_txt
    else:
        linhas = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html, re.I)
        linhas_td = [[_limpar_html(c) for c in re.findall(r"<td[^>]*>([\s\S]*?)</td>", l, re.I)] for l in linhas]
        idx = -1
        if cliente_lider:
            for i, cel in enumerate(linhas_td):
                if any(cliente_lider.upper() in c.upper() for c in cel):
                    idx = i
                    break
        if idx >= 0:
            l_end = linhas_td[idx + 1] if idx + 1 < len(linhas_td) else []
            l_loc = linhas_td[idx + 2] if idx + 2 < len(linhas_td) else []
            endereco = (l_end[0] if len(l_end) > 0 else None) or None
            bairro = (l_end[1] if len(l_end) > 1 else None) or None
            cep = (l_loc[0] if len(l_loc) > 0 else None) or None
            cidade = (l_loc[1] if len(l_loc) > 1 else None) or None
            uf = (l_loc[2] if len(l_loc) > 2 else None) or None
            m_cep = re.search(r"\b\d{5}-?\d{3}\b", " ".join(l_loc))
            if m_cep:
                cep = m_cep.group(0)
            uf_ok = next((x for x in re.findall(r"\b([A-Z]{2})\b", " ".join(l_loc)) if x in UFS_VALIDAS), None)
            if uf_ok:
                uf = uf_ok

    return {
        "pedidoLider": pedido_lider, "pedidoCancelado": eh_cancelado,
        "motivoCancelamento": motivo_cancel, "statusCancelamento": status_cancel,
        "dataPedidoLider": data_pedido, "entregaLider": entrega_lider, "situacaoLider": situacao,
        "clienteLider": cliente_lider, "cpf": cpf, "datasEntrega": datas_entrega,
        "telefone": telefone, "telefone2": telefone2, "telefones": telefones,
        "referencia": referencia,
        "enderecoEntrega": endereco, "bairroEntrega": bairro, "cidadeEntrega": cidade,
        "ufEntrega": uf, "cepEntrega": cep,
        "observacaoEntrega": observacao, "diasAdicionaisLider": dias_adic,
        "RESPONSÁVEL": responsavel, "Pedido": pedido_planilha, "Cliente": cliente_planilha,
        "motivoPlanilha": motivo_planilha, "confirmadoPlanilha": confirmado_planilha,
    }


# ------------------------------------------------------------------ Preparar Verificação de Entrega
def preparar_verificacao_entrega(p: dict) -> dict:
    datas = C.unicos(str(d).strip() for d in (p.get("datasEntrega") or []) if d)
    hoje = C.hoje_num()
    validas = [n for n in (C.data_num(d) for d in datas) if n >= hoje]
    parcial = len(datas) > 1
    return {**p, "datasEntregaUnicas": datas, "possuiEntregaParcial": parcial, "datasValidas": validas,
            "quantidadeDatas": len(datas), "quantidadeDatasValidas": len(validas),
            "consultarEntregaPorProduto": parcial}


# ------------------------------------------------------------------ Verificar Entrega Realizada
def verificar_entrega_realizada(p: dict) -> dict:
    datas = [d for d in (p.get("datasEntrega") or [p.get("entregaLider")]) if d]
    mais_recente = max(C.data_num(d) for d in datas) if datas else None
    return {**p, "entregaJaPassou": mais_recente is not None and mais_recente < C.hoje_num()}


# ------------------------------------------------------------------ Preservar Dados Pedido
def preservar_dados_pedido(p: dict) -> dict:
    campos = ["pedidoLider", "dataPedidoLider", "entregaLider", "situacaoLider", "clienteLider",
              "telefone", "telefone2", "referencia", "enderecoEntrega", "bairroEntrega", "cidadeEntrega",
              "ufEntrega", "cepEntrega", "observacaoEntrega", "diasAdicionaisLider", "RESPONSÁVEL",
              "datasEntrega", "datasEntregaUnicas", "datasValidas"]
    return {**p, "dadosPedidoOriginal": {k: p.get(k) for k in campos}}


# ------------------------------------------------------------------ Extrair Entrega por Produto
def _linhas_saldo(html: str, identificador: str, min_cel: int = 7) -> list[list[str]]:
    saida = []
    for linha in re.findall(r"<tr\b[^>]*>[\s\S]*?</tr>", html, re.I):
        if identificador not in C.limpar(re.sub(r"<[^>]+>", " ", linha)):
            continue
        cel = [C.sem_tags(c) for c in re.findall(r"<td\b[^>]*>[\s\S]*?</td>", linha, re.I)]
        if len(cel) >= min_cel:
            saida.append(cel)
    return saida


def extrair_entrega_por_produto(html: str, pedido_original: dict) -> dict:
    pedido = {k: v for k, v in pedido_original.items() if k not in ("data", "dadosPedidoOriginal")}
    ident = f"(11)-{str(pedido.get('pedidoLider')).strip()}"
    produtos = []
    for cel in _linhas_saldo(html, ident):
        pedido_html, situacao, data_entrega = cel[0], cel[2], cel[3]
        codigo, descricao = cel[5], cel[6]
        quantidade = cel[7] if len(cel) > 7 else None
        op_nf = cel[9] if len(cel) > 9 else None
        if ident not in pedido_html or not C.RE_DATA_BR.match(data_entrega) or not codigo:
            continue
        produtos.append({"pedido": pedido_html, "dataEntrega": data_entrega, "codigoItem": codigo,
                         "descricao": descricao, "quantidade": quantidade or None,
                         "situacao": situacao or None, "opOuNf": op_nf or None})
    mapa = {}
    for p in produtos:
        mapa.setdefault(f"{p['codigoItem']}|{p['dataEntrega']}", p)
    entrega_por_produto = list(mapa.values())
    grupos: dict[str, list] = {}
    for p in entrega_por_produto:
        grupos.setdefault(p["dataEntrega"], []).append(p)
    datas_produto = sorted(grupos, key=lambda d: "".join(reversed(d.split("/"))))
    pagina_valida = bool(re.search(r"Saldo de pedidos entre os dias", html, re.I))
    sem_pendentes = pagina_valida and len(entrega_por_produto) == 0
    hoje = C.hoje_num()
    origem_datas = pedido.get("datasEntregaUnicas") or pedido.get("datasEntrega") or []
    datas_orig = C.unicos(d for d in origem_datas if d)
    parcial_vencida = len(datas_orig) > 0 and all(C.data_num(d) <= hoje for d in datas_orig)
    return {**pedido, "entregaPorProduto": entrega_por_produto, "entregaPorData": grupos,
            "datasProduto": datas_produto, "semProdutosPendentes": sem_pendentes,
            "entregaParcialVencida": parcial_vencida,
            "erroConsulta": None if pagina_valida else "PAGINA_SITUACAO_INVALIDA",
            "motivoExpedicao": ("SEM PRODUTOS PENDENTES (ENTREGA/RETIRADA JÁ REALIZADA)" if sem_pendentes
                                else "ENTREGA PARCIAL COM TODAS AS DATAS VENCIDAS" if parcial_vencida else None)}


# ------------------------------------------------------------------ Verificar Planejado Data Absurda
def verificar_planejado_data_absurda(p: dict) -> dict:
    resp = str(p.get("RESPONSÁVEL") or "").strip().upper()
    eh_plan = resp in RESPONSAVEIS_PLANEJADOS
    datas = C.unicos(d for d in [*(p.get("datasEntrega") or []), p.get("entregaLider")] if d)
    absurdas = [d for d in datas if _ano(d) >= 2030]
    return {**p, "ehPlanejado": eh_plan, "datasAbsurdas": absurdas, "pularBoleto": eh_plan and len(absurdas) > 0}


def _ano(d) -> int:
    try:
        return int(str(d).split("/")[2])
    except (IndexError, ValueError):
        return 0


# ------------------------------------------------------------------ Montar E-mail Expedição
def montar_email_expedicao(pedidos: list[dict]) -> dict:
    linhas = []
    for p in pedidos:
        cliente = p.get("clienteLider") if p.get("clienteLider") is not None else (p.get("cliente") or "")
        datas = p.get("datasEntregaUnicas")
        cidade = p.get("cidadeEntrega") or ""
        entrega = p.get("entregaLider") or ""
        linhas.append(f"""
    <tr>
      <td>{C.esc(f"11-{p.get('pedidoLider') or ''}")}</td>
      <td>{C.esc(cliente)}</td>
      <td>{C.esc(cidade)}</td>
      <td>{C.esc(entrega)}</td>
    </tr>""")
    corpo = "".join(linhas) or '<tr><td colspan="5">Nenhum pedido encontrado</td></tr>'
    html = f"""
  <p>Olá, equipe da expedição.</p>
  <p>Os pedidos abaixo já tiveram a entrega realizada ou os produtos foram retirados na loja pelo cliente. Favor faturar:</p>
  <table border="1" cellpadding="6" cellspacing="0"
    style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif">
    <thead>
      <tr>
        <th>Pedido</th>
        <th>Cliente</th>
        <th>Cidade</th>
        <th>Entrega</th>
      </tr>
    </thead>
    <tbody>
      {corpo}
    </tbody>
  </table>"""
    return {"assunto": f"Pedidos com entrega anterior a {C.hoje_br()} - faturar ({len(pedidos)})", "html": html}


# ------------------------------------------------------------------ Tratar Conferência Boleto
def tratar_conferencia_boleto(resp: dict, pedido: dict) -> dict:
    html = str(resp.get("data") or "")
    falha = bool(resp.get("error")) or len(html) < 50
    numero = f"11-{pedido.get('pedidoLider')}"
    ja_tratado = bool(re.search("BOLETO", str(pedido.get("motivoPlanilha") or ""), re.I))
    linhas = re.findall(r"""<tr[^>]*class=["'][^"']*pedido[^"']*["'][\s\S]*?</tr>""", html, re.I)
    achada = next((l for l in linhas if numero in l), None)
    analisar = bool(re.search("ANALISAR", achada, re.I)) if achada else False
    status = ("BOLETO_JA_TRATADO" if ja_tratado else "ERRO_CONSULTA" if falha
              else "NAO_ENCONTRADO" if not achada else "ANALISAR" if analisar else "OK")
    return {**pedido, "boleto": {"pedido": numero, "encontrado": bool(achada), "analisar": analisar,
                                 "jaTratado": ja_tratado, "status": status}}


# ------------------------------------------------------------------ Analisar 50% do Pedido
def _limpar_texto(h) -> str:
    t = re.sub(r"<[^>]*>", " ", str(h or ""))
    t = t.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t).strip()


def analisar_50(pedido: dict, htmls_boleto: list[str]) -> dict:
    numero = f"11-{pedido.get('pedidoLider')}"
    html = next((h for h in htmls_boleto if numero in h), "")
    erro = lambda motivo, **x: {**pedido, "pagamento50": {"status": "ERRO", "motivo": motivo, **x}}  # noqa: E731
    if not html:
        return erro("HTML_DO_PEDIDO_NAO_ENCONTRADO")
    pos = html.find(numero)
    if pos == -1:
        return erro("PEDIDO_NAO_ENCONTRADO_NO_HTML")
    ini = html.rfind("<tr", 0, pos)
    fim = html.find("</tr>", pos)
    linha_principal = html[ini:fim + 5] if ini != -1 else html[:fim + 5]
    texto_linha = _limpar_texto(linha_principal)
    celulas_pedido = [_limpar_texto(c) for c in re.findall(r"<td[\s\S]*?</td>", linha_principal, re.I)]
    valores = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", texto_linha)
    if not valores:
        return erro("VALOR_TOTAL_NAO_ENCONTRADO")
    total = C.valor_br(valores[0])
    minimo = total / 2
    prox = html.find('<tr class="fw-bold pedido"', fim)
    bloco = html[fim + 5: len(html) if prox == -1 else prox]
    parcelas = []
    for linha in re.findall(r"<tr[\s\S]*?</tr>", bloco, re.I):
        cels = re.findall(r"<td[\s\S]*?</td>", linha, re.I)
        if len(cels) < 10:
            continue
        dados = [_limpar_texto(c) for c in cels]
        valor = C.valor_br(dados[6])
        venc = dados[9]
        if not math.isnan(valor) and valor > 0 and C.RE_DATA_BR.match(venc):
            parcelas.append({"valor": valor, "vencimento": venc, "data": C.parse_br(venc), "celulas": dados})
    if not parcelas:
        return erro("NENHUMA_PARCELA_ENCONTRADA")
    parcelas.sort(key=lambda x: x["data"])
    acumulado, p50 = 0.0, None
    for p in parcelas:
        acumulado += p["valor"]
        if acumulado >= minimo:
            p50 = p
            break
    if p50 is None:
        return erro("50_PORCENTO_NAO_ATINGIDO", valorTotal=total, valorMinimo=minimo, acumulado=acumulado)
    return {**pedido, "pagamento50": {
        "status": "OK", "valorTotal": total, "valorMinimo": minimo, "valorAte50": acumulado,
        "percentualAtingido": round((acumulado / total) * 10000) / 100,
        "parcela50": {"valor": p50["valor"], "vencimento": p50["vencimento"]},
        "pedidoLinha": celulas_pedido,
        "parcelas": [{"celulas": p["celulas"], "destaque": p is p50} for p in parcelas]}}


# ------------------------------------------------------------------ Calcular Nova Data Boleto 50%
def calcular_nova_data_50(pedido: dict) -> dict:
    pg = pedido.get("pagamento50") or {}
    if pg.get("status") != "OK" or not (pg.get("parcela50") or {}).get("vencimento"):
        return {**pedido, "pagamento50": {**pg, "status": "ERRO", "motivo": "VENCIMENTO_50_NAO_ENCONTRADO"}}
    venc = pg["parcela50"]["vencimento"]
    nova = C.adicionar_dias_uteis(C.parse_br(venc), 10)
    return {**pedido, "pagamento50": {**pg, "vencimento50": venc, "novaDataEntrega": C.fmt_br(nova),
                                      "diasAdicionados": 10}}


# ------------------------------------------------------------------ Montar URL Alteração
def montar_url_alteracao(html_form: str, pedido: dict, base: str) -> dict:
    from ..integracoes.intranet import url_com_query
    itens = []
    for tag in re.findall(r"<input\b[^>]*>", html_form, re.I):
        if not re.search(r"""name\s*=\s*["']?item\[\]["']?""", tag, re.I):
            continue
        v = re.search(r"""value\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag, re.I)
        if v:
            itens.append((v.group(1) if v.group(1) is not None else v.group(2) if v.group(2) is not None
                          else v.group(3) or "").replace("&amp;", "&"))
    itens = C.unicos(itens)
    if not itens:
        texto = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html_form)).strip()
        return {"urlAlterar": None, "qtdItens": 0, "dataISO": None, "erroFormulario":
                (f"Nenhum item no formulário do pedido {pedido.get('pedidoLider')}. "
                 f"Tamanho da resposta: {len(html_form)}. Contém \"item[]\": {'true' if 'item[]' in html_form else 'false'}. "
                 f"Início do texto: {texto[:300]}")}
    pg = pedido["pagamento50"]
    data_iso = "-".join(reversed(pg["novaDataEntrega"].split("/")))
    obs = (f"PRAZO DE ENTREGA ALTERADO DE {pedido.get('entregaLider')} PARA {pg['novaDataEntrega']} "
           f"- VENCIMENTO BOLETO 50%: {pg.get('vencimento50')}")
    params = [("data", data_iso), ("cod_empresa", "11"), ("pedido", pedido.get("pedidoLider")),
              ("motivo", "PENDENCIA FINANCEIRA"), ("agendamento", ""), ("observacao", obs), ("opcao[]", "A"),
              *[("item[]", i) for i in itens]]
    return {"urlAlterar": url_com_query(f"{base}/vdp/altera_data_entrega2.php", params),
            "qtdItens": len(itens), "dataISO": data_iso}


# ------------------------------------------------------------------ Montar alerta 50% (falha)
def montar_alerta_50(itens: list[dict]) -> dict | None:
    if not itens:
        return None
    linhas = "".join(
        f"<tr><td>{C.esc3(p.get('Pedido') or ('11-' + str(p.get('pedidoLider'))))}</td>"
        f"<td>{C.esc3(p.get('clienteLider') or p.get('Cliente'))}</td><td>{C.esc3(p.get('RESPONSÁVEL'))}</td>"
        f"<td>{C.esc3((p.get('boleto') or {}).get('status'))}</td>"
        f"<td>{C.esc3((p.get('pagamento50') or {}).get('motivo') or 'desconhecido')}</td></tr>" for p in itens)
    return {"assunto": f"[AÇÃO MANUAL] Boleto 50% não calculado - {len(itens)} pedido(s)",
            "html": ("<p>Os pedidos abaixo estão com boleto em análise (ou a consulta de boletos falhou) e o fluxo não "
                     "conseguiu calcular a nova data de entrega. Eles foram bloqueados (PENDENCIA_BOLETO) e "
                     "<b>não receberam mensagem</b>. Favor verificar manualmente.</p>\n"
                     '<table border="1" cellpadding="5" style="border-collapse:collapse;font-family:Arial;font-size:12px">'
                     f"<tr><th>Pedido</th><th>Cliente</th><th>Responsável</th><th>Status boleto</th><th>Motivo</th></tr>{linhas}</table>")}


# ------------------------------------------------------------------ e-mails da intranet (inf/emails.php)
IGNORAR_NOME = ["DE", "DA", "DO", "DAS", "DOS", "E"]


def _limpar_email(s) -> str:
    s = re.sub(r"<[^>]*>", " ", str(s or ""))
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def _norm_email(s) -> str:
    return C.sem_acento(_limpar_email(s)).upper()


def registros_emails(html: str, min_td: int, col_extra: int, nome_extra: str) -> list[dict]:
    regs = []
    for linha in re.findall(r"<tr[\s\S]*?</tr>", html, re.I):
        tds = re.findall(r"<td[\s\S]*?</td>", linha, re.I)
        if len(tds) < min_td:
            continue
        email = _limpar_email(tds[2]).lower()
        if "@" not in email:
            continue
        regs.append({"nome": _norm_email(tds[0]), "email": email, nome_extra: _norm_email(tds[col_extra])})
    return regs


# ------------------------------------------------------------------ Montar E-mail (vendedor, boleto 50%)
EMAIL_TESTE = "mateus.oliveira@lider.design"
MODO_TESTE_EMAIL_VENDEDOR = True   # v28: const MODO_TESTE = true no nó "Montar E-mail"


def montar_email_vendedor(pedido: dict, html_emails: str, alteracao: dict) -> dict:
    pg = pedido["pagamento50"]
    referencia = str(pedido.get("referencia") or "")
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", referencia)
    nome_bruto = (m.group(1) if m else referencia).strip()
    nome_ref = _norm_email(nome_bruto)
    loja_ref = _norm_email(m.group(2) if m else "")
    tokens_ref = [t for t in nome_ref.split(" ") if t and t not in IGNORAR_NOME]

    def nome_confere(nome_email):
        te = [x for x in nome_email.split(" ") if x]
        return len(tokens_ref) > 0 and all(any(x == t or (len(t) >= 4 and x.startswith(t)) for x in te) for t in tokens_ref)

    def loja_confere(loja_email):
        return bool(loja_ref) and bool(loja_email) and (loja_email.startswith(loja_ref) or loja_ref.startswith(loja_email))

    regs = registros_emails(html_emails, 6, 3, "empresa")
    cand = [r for r in regs if nome_confere(r["nome"]) and loja_confere(r["empresa"])]
    match_por = "NOME_E_LOJA"
    if not cand:
        cand = [r for r in regs if nome_confere(r["nome"])]
        match_por = "SO_NOME"
    nomes = C.unicos(c["nome"] for c in cand)
    emails = C.unicos(c["email"] for c in cand)
    ambiguo = len(nomes) > 1
    email_vendedor = emails[0] if (not ambiguo and emails) else None
    nome_vendedor = C.capitalizar(nome_bruto.split()[0]) if nome_bruto else None

    def th(t, extra=""):
        return f'<th {extra} style="border:1px solid #999;padding:4px 6px;background:#f2f2f2;font-size:12px;">{C.esc3(t)}</th>'

    def td(t, destaque):
        return (f'<td style="border:1px solid #999;padding:4px 6px;font-size:12px;text-align:center;'
                f'{"background:#ffff00;font-weight:bold;" if destaque else ""}">{C.esc3(t)}</td>')

    cab_pedido = "".join(th(t) for t in ["Código Cliente", "Nome Cliente", "Data Inclusão", "Pedido", "Cód. Nat. Oper",
                                         "Representante", "Valor", "Situação", "Usuário"]) + th("Pedido", 'colspan="2"') + th("Entrega")
    linha_pedido = "".join(td(c, False) for c in (pg.get("pedidoLinha") or []))
    cab_parc = "".join(th(t) for t in ["Empresa", "Banco", "Agência", "Conta", "Cheque", "Tipo Doc", "Valor", "Saldo",
                                       "Emissão", "Vencimento", "Prorrogada", "Status"])
    linhas_parc = "".join(f"<tr>{''.join(td(c, p['destaque']) for c in p['celulas'])}</tr>" for p in (pg.get("parcelas") or []))
    tabela = (f'<table style="border-collapse:collapse;font-family:Arial,sans-serif;">\n'
              f"<tr>{cab_pedido}</tr><tr>{linha_pedido}</tr>\n<tr>{cab_parc}</tr>{linhas_parc}\n</table>")
    falha = alteracao.get("sucesso") is False
    aviso_falha = (f'<p style="color:#c00;font-weight:bold;">ATENÇÃO: o fluxo NÃO conseguiu alterar a data na intranet '
                   f'({C.esc3(alteracao.get("erro") or "erro desconhecido")}). Altere manualmente para '
                   f'{C.esc3(pg.get("novaDataEntrega"))}.</p>') if falha else ""
    aviso = aviso_falha + (
        f'<p style="color:#c00;">[TESTE] destinatário real: {C.esc3(email_vendedor or "não encontrado")} '
        f'(referência: {C.esc3(referencia)}; busca: {match_por}'
        f'{"; AMBÍGUO: " + C.esc3(" / ".join(nomes)) if ambiguo else ""})</p>' if MODO_TESTE_EMAIL_VENDEDOR else "")
    html = f"""<div style="font-family:Arial,sans-serif;font-size:14px;">
{aviso}
<p>{C.saudacao()}{', ' + C.esc3(nome_vendedor) if nome_vendedor else ''}. Tudo bem?</p>
<p>O pedido abaixo terá sua data prevista de entrega alterada em razão do vencimento do boleto referente aos 50% do pagamento, previsto para <b>{C.esc3(pg.get('vencimento50'))}</b>.</p>
<p>Dessa forma, a nova previsão de entrega será para <b>{C.esc3(pg.get('novaDataEntrega'))}</b>.</p>
<p>Gentileza, por favor, comunicar o cliente sobre essa atualização.</p>
<p>Agradeço desde já e, caso tenha qualquer dúvida, permaneço à disposição.</p>
<p>Obrigada!</p>
{tabela}
</div>"""
    para = EMAIL_TESTE if MODO_TESTE_EMAIL_VENDEDOR else (email_vendedor or EMAIL_TESTE)
    assunto = (f"{'[ALTERAR DATA MANUALMENTE] ' if falha else ''}{'[TESTE] ' if MODO_TESTE_EMAIL_VENDEDOR else ''}"
               f"{'' if email_vendedor else '[SEM E-MAIL DO VENDEDOR] '}Alteração de prazo de entrega - Pedido "
               f"{(pedido.get('boleto') or {}).get('pedido')}")
    return {**pedido, "email": {"para": para, "assunto": assunto, "html": html, "vendedor": nome_vendedor,
                                "emailVendedor": email_vendedor, "referencia": referencia,
                                "matchPor": match_por, "emailsEncontrados": emails}}


# ------------------------------------------------------------------ Verificar outlet
def _numero_outlet(t):
    m = re.search(r"-?\d[\d.,]*", str("" if t is None else t))
    if not m:
        return None
    s = re.sub(r"[.,]$", "", m.group(0))
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        n = float(s)
        return n if math.isfinite(n) else None
    except ValueError:
        return None


def verificar_outlet(p: dict, html: str) -> dict:
    lim = C.sem_tags
    linhas = re.findall(r"<tr\b[^>]*>[\s\S]*?</tr>", html, re.I)
    col = None
    for l in linhas:
        c = [C.sem_acento(lim(x)).upper() for x in re.findall(r"<td\b[^>]*>[\s\S]*?</td>", l, re.I)]
        i_qtd = next((i for i, x in enumerate(c) if x in ("QTDE", "QUANTIDADE")), -1)
        i_est = next((i for i, x in enumerate(c) if x in ("EST", "ESTOQUE")), -1)
        if "PEDIDO" in c and i_qtd >= 0 and i_est >= 0:
            col = {"pedido": c.index("PEDIDO"), "item": next((i for i, x in enumerate(c) if x.startswith("COD")), -1),
                   "qtd": i_qtd, "est": i_est, "prazo": next((i for i, x in enumerate(c) if x.startswith("PRAZO")), -1),
                   "desc": next((i for i, x in enumerate(c) if x.startswith("DESCRI")), -1)}
            break
    alvo = C.n_ped(p.get("pedidoLider"))
    itens = []
    if col and alvo:
        for l in linhas:
            c = [lim(x) for x in re.findall(r"<td\b[^>]*>[\s\S]*?</td>", l, re.I)]
            if len(c) <= max(col["pedido"], col["qtd"], col["est"]):
                continue
            ped = c[col["pedido"]]
            if not re.match(r"^\(11\)-", ped) or C.n_ped(ped) != alvo:
                continue
            g = lambda k: (c[col[k]] if 0 <= col[k] < len(c) else "") or ""  # noqa: E731
            itens.append({"codigoItem": g("item"), "descricao": g("desc"), "prazo": g("prazo"),
                          "quantidade": _numero_outlet(c[col["qtd"]]), "estoque": _numero_outlet(c[col["est"]])})
    com_qtd = [x for x in itens if x["quantidade"] is not None and x["quantidade"] > 0]
    outlet = len(com_qtd) > 0 and all(x["estoque"] is not None and abs(x["estoque"] - x["quantidade"]) < 1e-9 for x in com_qtd)
    if not col:
        motivo = "PAGINA_SEM_COLUNA_ESTOQUE" if re.search(r"Saldo de pedidos entre os dias", html, re.I) else "PAGINA_ESTOQUE_INVALIDA"
    elif not com_qtd:
        motivo = "PEDIDO_NAO_ENCONTRADO_NA_PAGINA_ESTOQUE"
    else:
        motivo = "OUTLET: QUANTIDADE = ESTOQUE EM TODOS OS ITENS" if outlet else "NAO_OUTLET"
    prazos = sorted((x["prazo"] for x in com_qtd if C.RE_DATA_BR.match(x["prazo"])),
                    key=lambda d: "".join(reversed(d.split("/"))))
    data_outlet = (prazos[0] if prazos else None) or p.get("entregaLider") or ""
    return {**p, "outlet": outlet, "motivoOutlet": motivo, "itensOutlet": com_qtd,
            "dataOutlet": data_outlet, "dataOutletISO": C.br_para_iso(data_outlet)}


# ------------------------------------------------------------------ Montar registro (outlet)
def montar_registro_outlet(p: dict) -> dict:
    datas = sorted(C.unicos(str(x.get("prazo") or "").strip() for x in (p.get("itensOutlet") or [])
                            if C.RE_DATA_BR.match(str(x.get("prazo") or "").strip())), key=C.data_num)
    if not datas and C.RE_DATA_BR.match(str(p.get("dataOutlet") or "")):
        datas = [p["dataOutlet"]]
    if not datas and C.RE_DATA_BR.match(str(p.get("entregaLider") or "")):
        datas = [p["entregaLider"]]
    datas_txt = " E ".join(datas)
    dat_entrega = (C.br_para_iso(datas[0]) if datas else "") or p.get("dataOutletISO") or ""
    pedido_sheet = p.get("Pedido") if p.get("Pedido") is not None else (
        p.get("pedidoOriginal") if p.get("pedidoOriginal") is not None else f"11-{p.get('pedidoLider')}")
    agora_iso = C.agora_iso_utc()
    return {**p, "pedidoSheet": str(pedido_sheet).strip(), "sheetG": "SIM", "sheetH": "CONFIRMADO",
            "sheetI": C.carimbo_br(),
            "clienteIntranet": C.sem_acento(p.get("clienteLider") if p.get("clienteLider") is not None else (p.get("Cliente") or "")).strip(),
            "datEntrega": dat_entrega, "temDataIntranet": bool(dat_entrega),
            "entregas": [{"data": d} for d in datas],
            "observacaoOutlet": C.sem_acento(f"CLIENTE CONTATADO VIA WHATSAPP E CONFIRMOU A DATA DE ENTREGA {datas_txt}.").upper(),
            "statusFinal": "CONCLUIDO", "categoria": "ACEITA",
            "resumoOutlet": "Cliente confirmou a data de entrega.", "registradoEm": agora_iso}


# ------------------------------------------------------------------ Classificar Tipo de Móvel
def classificar_tipo_movel(p: dict) -> dict:
    r = str(p.get("RESPONSÁVEL") or "").strip().upper()
    tipo = "Planejados" if r in RESPONSAVEIS_PLANEJADOS else "Moveis soltos" if r in RESPONSAVEIS_SOLTOS else None
    return {**p, "tipoMovel": tipo}


# ------------------------------------------------------------------ Preparar Rota
DEPOSITOS = {
    "SP": {"cidade": "BARUERI", "uf": "SP", "nome": "DEPÓSITO BARUERI"},
    "RJ": {"cidade": "RIO DE JANEIRO", "uf": "RJ", "nome": "DEPÓSITO RIO DE JANEIRO"},
    "ES": {"cidade": "CARIACICA", "uf": "ES", "nome": "DEPÓSITO CARIACICA"},
    "BA": {"cidade": "LAURO DE FREITAS", "uf": "BA", "nome": "DEPÓSITO LAURO DE FREITAS"},
    "DF": {"cidade": "BRASILIA", "uf": "DF", "nome": "DEPÓSITO BRASILIA"},
}
ALIAS_CIDADES = {"M.LEME": "MATEUS LEME"}


def _primeiro_def(p, *chaves):
    for k in chaves:
        if p.get(k) is not None:
            return p.get(k)
    return ""


def preparar_rota(p: dict) -> dict:
    nz = lambda t: C.sem_acento(t).strip().upper()  # noqa: E731
    uf_dest = nz(p.get("ufEntrega"))
    cid_dest = re.sub(r"\s+", " ", nz(p.get("cidadeEntrega")))
    referencia = nz(_primeiro_def(p, "referencia", "REFERENCIA", "referenciaLider", "REFERENCIA_LIDER"))
    observacao = nz(_primeiro_def(p, "observacaoEntrega", "OBSERVACAO", "observacao"))
    p10 = bool(re.search(r"\b10\s*DIAS?\b", observacao) or re.search(r"\bDEZ\s*DIAS?\b", observacao))
    origem, ok, motivo = None, False, ""
    if uf_dest != "MG":
        if uf_dest in DEPOSITOS:
            origem, ok, motivo = DEPOSITOS[uf_dest], True, "DEPOSITO_REGIONAL"
        else:
            motivo = "UF_SEM_DEPOSITO_CONFIGURADO"
    else:
        if any(x in referencia for x in ("SILVIANO", "S.BRANDAO", "PONTEIO", "CATALAO", "SION")):
            origem, ok, motivo = {"cidade": "BELO HORIZONTE", "uf": "MG", "nome": "BELO HORIZONTE"}, True, "REFERENCIA_LOJA_BH"
        elif referencia:
            cid_ref = referencia
            mp = re.search(r"\(([^)]+)\)", referencia)
            if mp:
                cid_ref = mp.group(1).strip()
            cid_ref = ALIAS_CIDADES.get(cid_ref, cid_ref)
            if "CORP" in cid_ref or "SAO PAULO" in cid_ref or "CENTRAL" in cid_ref:
                ok, motivo = False, "REFERENCIA_CORPORATIVA_SEM_PRACA_MG"
            else:
                origem, ok, motivo = {"cidade": cid_ref, "uf": "MG", "nome": cid_ref}, True, "REFERENCIA_MG"
        else:
            motivo = "REFERENCIA_MG_NAO_INFORMADA"
    candidatos = [p.get("phone"), p.get("telefone"), p.get("telefone2"),
                  *(p.get("telefones") if isinstance(p.get("telefones"), list) else [])]
    tels = C.unicos(t for t in (C.normalizar_celular(x) for x in candidatos) if t)
    tel_ok = len(tels) > 0
    if not ok and not tel_ok:
        mot_pend = "ORIGEM_E_TELEFONE_NAO_IDENTIFICADOS"
    elif not ok:
        mot_pend = motivo
    elif not tel_ok:
        mot_pend = "TELEFONE_NAO_LOCALIZADO"
    else:
        mot_pend = None
    sem_pend = ok and tel_ok
    return {**p, "phone": tels[0] if tel_ok else None,
            "telefones": tels if tels else (p.get("telefones") or []),
            "rota": {"origemIdentificada": ok, "telefoneIdentificado": tel_ok, "semPendencia": sem_pend,
                     "motivoPendencia": mot_pend, "status": "OK" if sem_pend else "PENDENTE",
                     "motivoOrigem": motivo, "origem": origem,
                     "destino": {"cidade": cid_dest, "uf": uf_dest}, "possui10DiasObservacao": p10,
                     "distanciaKm": None, "diasAdicionaisDistancia": 0,
                     "motivoPrazo": "10_DIAS_JA_INFORMADOS_NA_OBSERVACAO" if p10 else None}}


# ------------------------------------------------------------------ Resolver Coordenadas (Tabela)
TABELA_COORD = {
    "BELO HORIZONTE|MG": (-19.9167, -43.9345), "BARUERI|SP": (-23.5106, -46.8761),
    "RIO DE JANEIRO|RJ": (-22.9068, -43.1729), "CARIACICA|ES": (-20.2632, -40.4165),
    "LAURO DE FREITAS|BA": (-12.8978, -38.3213), "BRASILIA|DF": (-15.7939, -47.8828),
    "CARMO DO CAJURU|MG": (-20.1892, -44.7894), "DIVINOPOLIS|MG": (-20.1386, -44.8839),
    "CONTAGEM|MG": (-19.9319, -44.0539), "BETIM|MG": (-19.9668, -44.1983),
    "NOVA LIMA|MG": (-19.9856, -43.8466), "SABARA|MG": (-19.8836, -43.8267),
    "SANTA LUZIA|MG": (-19.7697, -43.8514), "RIBEIRAO DAS NEVES|MG": (-19.7669, -44.0867),
    "SETE LAGOAS|MG": (-19.4658, -44.2467), "ITAUNA|MG": (-20.0753, -44.5761),
    "NOVA SERRANA|MG": (-19.8750, -44.9847), "FORMIGA|MG": (-20.4644, -45.4269),
    "PARA DE MINAS|MG": (-19.8606, -44.6086), "OLIVEIRA|MG": (-20.6961, -44.8269),
    "BOM DESPACHO|MG": (-19.7378, -45.2589), "CAMPO BELO|MG": (-20.8969, -45.2736),
    "LAVRAS|MG": (-21.2453, -45.0000), "VARGINHA|MG": (-21.5514, -45.4306),
    "POUSO ALEGRE|MG": (-22.2300, -45.9364), "POCOS DE CALDAS|MG": (-21.7878, -46.5614),
    "PASSOS|MG": (-20.7189, -46.6097), "UBERABA|MG": (-19.7472, -47.9381),
    "UBERLANDIA|MG": (-18.9186, -48.2772), "JUIZ DE FORA|MG": (-21.7642, -43.3503),
    "BARBACENA|MG": (-21.2258, -43.7736), "CONSELHEIRO LAFAIETE|MG": (-20.6603, -43.7853),
    "IPATINGA|MG": (-19.4703, -42.5476), "GOVERNADOR VALADARES|MG": (-18.8511, -41.9494),
    "MONTES CLAROS|MG": (-16.7282, -43.8578), "PATOS DE MINAS|MG": (-18.5789, -46.5183),
    "VILA VELHA|ES": (-20.3297, -40.2925), "VITORIA|ES": (-20.3155, -40.3128),
    "SERRA|ES": (-20.1209, -40.3074), "SAO PAULO|SP": (-23.5505, -46.6333),
    "CAMPINAS|SP": (-22.9099, -47.0626), "GUARULHOS|SP": (-23.4543, -46.5333),
    "NITEROI|RJ": (-22.8832, -43.1034), "SALVADOR|BA": (-12.9777, -38.5016),
    "CAMACARI|BA": (-12.6996, -38.3263),
}
TABELA = {k: {"lat": v[0], "lon": v[1]} for k, v in TABELA_COORD.items()}


def chave_cidade(cidade, uf) -> str:
    return f"{C.norm(cidade)}|{C.norm(uf)}"


def cidades_faltantes(pedidos: list[dict]) -> list[dict]:
    falt = {}
    for p in pedidos:
        rota = p.get("rota") or {}
        for l in (rota.get("origem"), rota.get("destino")):
            if not l or not l.get("cidade"):
                continue
            k = chave_cidade(l["cidade"], l.get("uf"))
            if k not in TABELA and k not in falt:
                falt[k] = {"chave": k, "cidade": C.norm(l["cidade"]), "uf": C.norm(l.get("uf"))}
    return list(falt.values())


def preparar_coordenadas(pedidos: list[dict], novas: dict) -> list[dict]:
    def buscar(l):
        if not l or not l.get("cidade"):
            return None
        k = chave_cidade(l["cidade"], l.get("uf"))
        return TABELA.get(k) or novas.get(k)

    saida = []
    for i, p in enumerate(pedidos):
        rota = p.get("rota") or {}
        o, d = buscar(rota.get("origem")), buscar(rota.get("destino"))
        ok = bool(o) and bool(d)
        mot = rota.get("motivoPendencia")
        ori, des = rota.get("origem") or {}, rota.get("destino") or {}
        if not o:
            mot = f"CIDADE_ORIGEM_NAO_LOCALIZADA: {_js(ori.get('cidade'))}/{_js(ori.get('uf'))}"
        elif not des.get("cidade"):
            mot = "CIDADE_DESTINO_NAO_INFORMADA (endereço não lido da intranet)"
        elif not d:
            mot = f"CIDADE_DESTINO_NAO_LOCALIZADA: {_js(des.get('cidade'))}/{_js(des.get('uf'))}"
        item = {**p, "coordenadasValidas": ok, "coordenadas": {"origem": o, "destino": d},
                "status": (p.get("status") or "EM_PROCESSAMENTO") if ok else "PENDENTE_DESTINO",
                "rota": {**rota, "origemIdentificada": bool(o), "semPendencia": ok,
                         "status": "OK" if ok else "PENDENTE", "motivoPendencia": mot}}
        if i == 0:
            item["linhasParaTabela"] = [f"'{k}': {{ lat: {c['lat']}, lon: {c['lon']} }}," for k, c in novas.items()]
        saida.append(item)
    return saida


def _js(v) -> str:
    """Interpolação de template do JS: undefined/null viram 'undefined'/'null'."""
    return "undefined" if v is None else str(v)


# ------------------------------------------------------------------ Tratar Distância
def tratar_distancia(resp: dict, p: dict) -> dict:
    dist, motivo, ok = None, None, False
    rotas = resp.get("routes") if isinstance(resp, dict) else None
    if resp.get("code") == "Ok" and rotas and rotas[0].get("distance"):
        dist = round((rotas[0]["distance"] / 1000) * 10) / 10
        ok = True
    elif (p.get("coordenadas") or {}).get("origem") and (p.get("coordenadas") or {}).get("destino"):
        o, d = p["coordenadas"]["origem"], p["coordenadas"]["destino"]
        r = 6371
        dlat = math.radians(d["lat"] - o["lat"])
        dlon = math.radians(d["lon"] - o["lon"])
        a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(o["lat"])) * math.cos(math.radians(d["lat"]))
             * math.sin(dlon / 2) ** 2)
        reta = r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        dist = round(reta * 1.35 * 10) / 10
        motivo, ok = "DISTANCIA_ESTIMADA_FALLBACK_OSRM", True
    rota = p.get("rota") or {}
    if not ok:
        return {**p, "rota": {**rota, "status": "PENDENTE", "distanciaKm": None, "diasAdicionaisDistancia": 0,
                              "motivoPrazo": "ERRO_AO_CALCULAR_ROTA_OSRM"}}
    dias = 10 if (dist > 100 and not rota.get("possui10DiasObservacao")) else 0
    if not motivo:
        motivo = ("DISTANCIA_MAIOR_QUE_100KM" if dias == 10 else
                  "10_DIAS_JA_INFORMADOS_NA_OBSERVACAO" if rota.get("possui10DiasObservacao") else "DISTANCIA_ATE_100KM")
    return {**p, "rota": {**rota, "status": "OK", "distanciaKm": dist, "diasAdicionaisDistancia": dias,
                          "motivoPrazo": motivo}}


# ------------------------------------------------------------------ Calcular Data de Entrega
def calcular_data_entrega(p: dict) -> dict:
    dias = int(float(p.get("diasAdicionaisLider") or 0)) + int(float((p.get("rota") or {}).get("diasAdicionaisDistancia") or 0))
    base = p.get("datasEntrega") or [p.get("entregaLider")]
    ordenadas = sorted(C.unicos(d for d in base if d), key=C.data_num)
    calc = [{"original": d, "calculada": C.fmt_br(C.adicionar_dias_uteis(C.parse_br(d), dias))} for d in ordenadas]
    return {**p, "diasAdicionaisTotais": dias, "datasCalculadas": calc,
            "dataEntregaCalculada": calc[-1]["calculada"] if calc else None}


# ------------------------------------------------------------------ Verificar reincidência sem retorno
def verificar_reincidencia(pedidos: list[dict], sem_conf: list[dict]) -> list[dict]:
    hoje = C.hoje_iso()
    nao_conta = ["RESPONDEU_DEPOIS", "RESPOSTA_TARDIA_TRATADA"]
    hist = [r for r in sem_conf if str(r.get("pedidoLider") or "").strip() != ""
            and str(r.get("status") or "").upper() not in nao_conta]
    por = {}
    for r in hist:
        k = C.n_ped(r.get("pedidoLider"))
        if k:
            por.setdefault(k, []).append(r)
    saida = []
    for p in pedidos:
        regs = por.get(C.n_ped(p.get("pedidoLider")), [])
        ja = any(str(r.get("status") or "").upper() == "ESCALADO" for r in regs)
        dias = sorted(C.unicos(x for x in (str(r.get("dataRef") or "").strip() for r in regs) if x and x != hoje))
        acao = "JA_ESCALADO" if ja else ("ESCALAR" if len(dias) >= 2 else "NORMAL")
        saida.append({**p, "acaoReincidencia": acao, "diasSemRetorno": dias, "qtdDiasSemRetorno": len(dias)})
    return saida


# ------------------------------------------------------------------ Verificar resposta tardia
def verificar_resposta_tardia(pedidos: list[dict], sem_conf: list[dict], mensagens: list[dict]) -> list[dict]:
    hoje = C.hoje_iso()
    ignorar = ["ESCALADO", "RESPOSTA_TARDIA_TRATADA"]
    sc = [r for r in sem_conf if str(r.get("pedidoLider") or "").strip() != ""]
    ts_de = lambda m: (float(m.get("ts")) if m.get("ts") not in (None, "", 0) else 0) or C.iso_ms(m.get("recebidoEm"))  # noqa: E731
    por_contato = {}
    for m in mensagens:
        if not m or m.get("error"):
            continue
        cid = str(m.get("contactId") or "").strip()
        if not cid or str(m.get("texto") or "").strip() == "":
            continue
        por_contato.setdefault(cid, []).append(m)
    for l in por_contato.values():
        l.sort(key=ts_de)
    quando = lambda r: C.iso_ms(r.get("registradoEm"))  # noqa: E731

    def fala(m):
        return {"papel": "CLIENTE" if str(m.get("papel") or "").upper() == "CLIENTE" else "LIDER",
                "texto": str(m.get("texto") or "").strip()[:2000], "ts": ts_de(m)}

    saida = []
    for p in pedidos:
        sem = {**p, "respostaTardia": None}
        if p.get("acaoReincidencia") == "JA_ESCALADO":
            saida.append(sem)
            continue
        regs = [r for r in sc if C.n_ped(r.get("pedidoLider")) == C.n_ped(p.get("pedidoLider"))
                and str(r.get("dataRef") or "").strip() != hoje]
        regs.sort(key=lambda r: (-quando(r), _neg_str(str(r.get("dataRef") or ""))))
        ult = regs[0] if regs else None
        if not ult or str(ult.get("status") or "").upper() in ignorar:
            saida.append(sem)
            continue
        if str(ult.get("status") or "").upper() == "RESPONDEU_DEPOIS":
            corte = C.iso_ms(f"{str(ult.get('dataRef') or '').strip()}T00:00:00-03:00") or quando(ult)
        else:
            corte = quando(ult)
        cid = str(ult.get("contactId") or "").strip()
        if not corte or not cid:
            saida.append(sem)
            continue
        conversa = por_contato.get(cid, [])
        resp = [m for m in conversa if str(m.get("papel") or "").upper() == "CLIENTE" and ts_de(m) > corte]
        if not resp:
            saida.append(sem)
            continue
        saida.append({**p,
                      "acaoReincidencia": "NORMAL" if p.get("acaoReincidencia") == "ESCALAR" else p.get("acaoReincidencia"),
                      "respostaTardia": {
                          "pedidoLiderRegistro": str(ult.get("pedidoLider")), "dataRef": str(ult.get("dataRef") or ""),
                          "encerradoEm": str(ult.get("registradoEm") or ""), "etapa": str(ult.get("status") or ""),
                          "contactId": cid, "respostas": [fala(m) for m in resp[-20:]],
                          "contexto": [fala(m) for m in [m for m in conversa if ts_de(m) <= corte][-6:]],
                          "detectadoEm": C.agora_iso_utc(),
                          "reincidenciaIgnorada": p.get("acaoReincidencia") == "ESCALAR"}})
    return saida


def _neg_str(s: str):
    """Chave para ordenar string em ordem decrescente dentro de sort crescente."""
    return [-ord(c) for c in s] + [0]
