"""Paridade dos nós Code do Fluxo 1 (JS original x Python)."""
import copy
from datetime import timedelta

from app import comum as C
from app.fluxos import f1_extracao as X
from app.fluxos import f1_mensagens as M

from .conftest import fixture, igual, rodar_js

LINHA = {"row_number": 2, "Pedido": "11-209768", "Cliente": "MERCANTIL", "RESPONSÁVEL": "DANIELA",
         "MOTIVO": "", "CONFIRMADO": ""}


def _futuro(dias):
    return C.fmt_br(C.agora().date() + timedelta(days=dias))


def test_preparar_pedido():
    linhas = [LINHA, {"Pedido": "(11) 0051695"}, {"Pedido": "sem numero"}, {"Pedido": "11-12345678"}]
    igual(rodar_js("Preparar Pedido", linhas), [X.preparar_pedido(l) for l in linhas])


def test_extrair_dados_pedido_pagina_real():
    html = fixture("lojas_209768.html")
    plan = X.preparar_pedido(LINHA)
    js = rodar_js("Extrair Dados Pedido", [{"data": html}], {"Preparar Pedido": [plan]})
    igual(js, [X.extrair_dados_pedido(html, plan)])


def test_extrair_dados_pedido_cancelado_e_vazio():
    plan = X.preparar_pedido(LINHA)
    for html in ["<html>PEDIDO: 1 CANCELADO</html>", "<html></html>",
                 "<b>ENTREGA</b>: RUA X, 10 - CENTRO, NOVA LIMA - MG.<br> PEDIDO: 207476 / 0 01/10/2026 ENTREGA: 20/12/2026 "
                 "Sit.: N FULANO DE TAL 0123456789012345 31999998888 3133334444 LUCIANA CALISTO ( M.LEME) NATUREZA"
                 "<font color=red>CONSIDERAR MAIS 10 DIAS ÚTEIS PARA ENTREGA</font>"]:
        js = rodar_js("Extrair Dados Pedido", [{"data": html}], {"Preparar Pedido": [plan]})
        igual(js, [X.extrair_dados_pedido(html, plan)])


def test_verificar_outlet_pagina_real():
    html = fixture("vdp_situacao_209534.html")
    p = {"pedidoLider": "209534", "entregaLider": "10/11/2026"}
    js = rodar_js("Verificar outlet", [{"data": html}], {"Merge1": [p]})
    igual(js, [X.verificar_outlet(p, html)])


def test_extrair_entrega_por_produto():
    html = fixture("vdp_situacao_209534.html")
    p = X.preservar_dados_pedido({"pedidoLider": "209534", "datasEntrega": ["01/10/2026", "05/10/2026"],
                                  "datasEntregaUnicas": ["01/10/2026", "05/10/2026"]})
    js = rodar_js("Extrair Entrega por Produto", [{"data": html}], {"Preservar Dados Pedido": [p]})
    igual(js, [X.extrair_entrega_por_produto(html, p)])


def test_preparar_rota_varios():
    casos = [
        {"ufEntrega": "MG", "cidadeEntrega": "Nova Lima", "referencia": "LUCIANA CALISTO (M.LEME)", "telefone": "31999998888"},
        {"ufEntrega": "SP", "cidadeEntrega": "São Paulo", "telefone": "1133334444", "telefone2": "11988887777"},
        {"ufEntrega": "MG", "cidadeEntrega": "BH", "referencia": "ANA (SILVIANO)", "observacaoEntrega": "CONSIDERAR MAIS 10 DIAS"},
        {"ufEntrega": "GO", "cidadeEntrega": "Goiânia"},
        {"ufEntrega": "MG", "referencia": "JOAO (CORPORATIVO)", "telefones": ["31988887777"]},
    ]
    igual(rodar_js("Preparar Rota", casos), [X.preparar_rota(c) for c in casos])


def test_calcular_datas_feriados():
    casos = [{"datasEntrega": ["18/11/2026", "24/12/2026"], "diasAdicionaisLider": 10, "rota": {"diasAdicionaisDistancia": 10}},
             {"entregaLider": "31/03/2027", "diasAdicionaisLider": 0, "rota": {}},
             {"datasEntrega": [], "entregaLider": "01/04/2026", "diasAdicionaisLider": 3}]
    igual(rodar_js("Calcular Data de Entrega", casos), [X.calcular_data_entrega(c) for c in casos])
    p50 = [{"pagamento50": {"status": "OK", "parcela50": {"vencimento": "30/03/2027"}}},
           {"pagamento50": {"status": "ERRO"}}]
    igual(rodar_js("Calcular Nova Data Boleto 50%", p50), [X.calcular_nova_data_50(c) for c in p50])


def test_tratar_distancia():
    pedidos = [{"coordenadas": {"origem": {"lat": -19.9, "lon": -43.9}, "destino": {"lat": -21.7, "lon": -43.3}}, "rota": {}},
               {"coordenadas": {"origem": {"lat": -19.9, "lon": -43.9}, "destino": {"lat": -19.98, "lon": -43.84}}, "rota": {"possui10DiasObservacao": True}},
               {"coordenadas": {}, "rota": {}}]
    respostas = [{"code": "Ok", "routes": [{"distance": 271234}]}, {"error": "timeout"}, {"error": "x"}]
    js = rodar_js("Tratar Distância", respostas, {"Coordenadas válidas?": pedidos})
    igual(js, [X.tratar_distancia(r, p) for r, p in zip(respostas, pedidos)])


def test_preparar_tentativas_e_cpf():
    casos = [{"telefone": "31999998888", "telefone2": "3133334444", "cpf": "114679806000076"},
             {"telefone": "3133334444"},
             {"telefone": "5531988887777", "telefone2": "31988887777", "cpf": "046069303000161"}]
    igual(rodar_js("Preparar Tentativas Digisac", casos), [M.preparar_tentativas(c) for c in casos])


def test_mensagem_soltos_pagina_real():
    html = fixture("vdp_situacao_209534.html")
    itens = M.extrair_itens_saldo(html, "209534")
    datas = C.unicos(i["dataEntrega"] for i in itens)
    p = {"pedidoLider": "209534", "clienteLider": "MARIA DA SILVA", "phone": "5531999998888", "contactId": "c1",
         "datasCalculadas": [{"original": d, "calculada": _futuro(10 + k)} for k, d in enumerate(datas)],
         "RESPONSÁVEL": "DANIELA", "tipoMovel": "Moveis soltos"}
    js = rodar_js("Montar Mensagem Soltos", [{"data": html}], {"Separ produtos": [p]})
    igual(js, [M.montar_mensagem_soltos(p, html)])
    p2 = {**p, "contactId": None, "datasCalculadas": []}
    igual(rodar_js("Montar Mensagem Soltos", [{"data": "<html></html>"}], {"Separ produtos": [p2]}),
          [M.montar_mensagem_soltos(p2, "<html></html>")])


def test_mensagem_planejados_paginas_reais():
    html = fixture("vdp_situacao_209534.html")
    proj = fixture("projetos.html")
    idx, valida = M.indice_projetos(proj)
    for entrega in ("01/12/2040", "10/11/2026"):
        p = {"pedidoLider": "209534", "clienteLider": "JOSE PEREIRA", "phone": "5531999998888", "contactId": "c1",
             "entregaLider": entrega, "datasEntrega": [entrega], "tipoMovel": "Planejados",
             "datasCalculadas": [{"original": d, "calculada": _futuro(20)} for d in
                                 C.unicos(i["dataEntrega"] for i in M.extrair_itens_saldo(html, "209534"))]}
        js = rodar_js("Montar Mensagem Planejados", [], {"Consultar Itens Planejado": [{"data": html}],
                                                         "Separ produtos": [p], "Consultar Projetos Postados": [{"data": proj}]})
        igual(js, [M.montar_mensagem_planejados(p, html, idx, valida)])


def test_agrupar_mesmo_cliente():
    base = lambda n, d, c="c1", tipo="UNICA": {  # noqa: E731
        "pedidoLider": n, "contactId": c, "tipoMensagem": tipo, "bloqueado": False, "tipoMovel": "Moveis soltos",
        "mensagem": "Olá, Ana! Aqui é da *Líder*.\n\nx", "entregas": [{"data": d, "itens": [
            {"descricao": f"MESA {n} - TAMPO", "quantidade": "2,00"}, {"descricao": "CADEIRA", "quantidade": "1"}]}]}
    itens = [base("210500", "20/12/2026"), base("209000", "20/12/2026"), base("208000", "05/01/2027", "c2"),
             base("208100", "06/01/2027", "c2"), base("207000", "06/01/2027", "c2"), base("206000", "07/01/2027", "c3")]
    js = rodar_js("Agrupar pedidos do mesmo cliente", itens, {"Verificar resposta tardia": []})
    igual(js, M.agrupar_pedidos(copy.deepcopy(itens), []))


def test_reincidencia_e_tardia():
    hoje = C.hoje_iso()
    ontem = (C.agora().date() - timedelta(days=1)).isoformat()
    anteontem = (C.agora().date() - timedelta(days=2)).isoformat()
    pedidos = [{"pedidoLider": "100"}, {"pedidoLider": "200"}, {"pedidoLider": "300"}, {"pedidoLider": "400"}]
    sem = [{"pedidoLider": "100", "dataRef": ontem, "status": "SEM_RETORNO", "contactId": "k1", "registradoEm": f"{ontem}T16:20:00.000Z"},
           {"pedidoLider": "100", "dataRef": anteontem, "status": "SEM_RETORNO", "contactId": "k1", "registradoEm": f"{anteontem}T16:20:00.000Z"},
           {"pedidoLider": "200", "dataRef": ontem, "status": "ESCALADO"},
           {"pedidoLider": "300", "dataRef": ontem, "status": "SEM_RETORNO", "contactId": "k3", "registradoEm": f"{ontem}T15:00:00.000Z"},
           {"pedidoLider": "400", "dataRef": hoje, "status": "SEM_RETORNO"}]
    msgs = [{"contactId": "k3", "papel": "CLIENTE", "texto": "ok pode ser", "ts": C.iso_ms(f"{ontem}T20:00:00Z")},
            {"contactId": "k3", "papel": "Líder", "texto": "template", "ts": C.iso_ms(f"{ontem}T10:00:00Z")},
            {"contactId": "k1", "papel": "CLIENTE", "texto": "oi", "ts": C.iso_ms(f"{anteontem}T10:00:00Z")}]
    js1 = rodar_js("Verificar reincidência sem retorno", msgs, {"Ler SEM_CONFIRMACAO_DIARIO": sem, "Calcular Data de Entrega": pedidos})
    py1 = X.verificar_reincidencia(pedidos, sem)
    igual(js1, py1)
    js2 = rodar_js("Verificar resposta tardia", py1, {"Ler SEM_CONFIRMACAO_DIARIO": sem, "Ler MENSAGENS_CLIENTE (resposta tardia)": msgs})
    igual(js2, X.verificar_resposta_tardia(py1, sem, msgs), ignorar=("detectadoEm",))


def test_conferencia_boleto_e_50():
    html = ('<table><tr class="fw-bold pedido"><td>1</td><td>CLIENTE</td><td>01/10/2026</td><td>11-555</td><td>x</td>'
            '<td>REP</td><td>10.000,00</td><td>ANALISAR</td><td>u</td><td>a</td><td>b</td><td>c</td></tr>'
            + "".join(f"<tr>{''.join(f'<td>{v}</td>' for v in ['11','B','A','C','','BOL',val,val,'01/10/2026',venc,'','ABERTO'])}</tr>"
                      for val, venc in [("2.000,00", "10/10/2026"), ("3.500,00", "10/11/2026"), ("4.500,00", "10/12/2026")])
            + '<tr class="fw-bold pedido"><td>outro</td></tr></table>')
    pedidos = [{"pedidoLider": "555", "motivoPlanilha": ""}, {"pedidoLider": "556", "motivoPlanilha": "BOLETO/ 50%"},
               {"pedidoLider": "557", "motivoPlanilha": ""}]
    resps = [{"data": html}, {"data": html}, {"data": "", "error": "falhou"}]
    js = rodar_js("Tratar Conferência Boleto", resps, {"Pular boleto?": pedidos})
    py = [X.tratar_conferencia_boleto(r, p) for r, p in zip(resps, pedidos)]
    igual(js, py)
    js50 = rodar_js("Analisar 50% do Pedido", [py[0]], {"Conferir Boletos": resps})
    igual(js50, [X.analisar_50(py[0], [r["data"] for r in resps])])


def test_email_vendedor_e_reincidencia():
    emails = ("<table>" + "".join(f"<tr><td>{n}</td><td>x</td><td>{e}</td><td>{loja}</td><td>{setor}</td><td>y</td></tr>"
              for n, e, loja, setor in [("LUCIANA CALISTO", "luciana@lider.design", "M.LEME", "LOJA"),
                                        ("DANIELA SOUZA", "daniela.souza@lider.design", "CENTRAL", "0104-CENTRAL DE RELACIONAMENTO"),
                                        ("RAYNNER SILVA", "raynner@lider.design", "CENTRAL", "0104-CENTRAL DE RELACIONAMENTO")]) + "</table>")
    pedido = {"pedidoLider": "207476", "referencia": "LUCIANA CALISTO (M.LEME)", "entregaLider": "10/12/2026",
              "boleto": {"pedido": "11-207476"},
              "pagamento50": {"vencimento50": "01/12/2026", "novaDataEntrega": "15/12/2026", "pedidoLinha": ["a", "b"],
                              "parcelas": [{"celulas": ["1", "2"], "destaque": True}]}}
    alt = {"sucesso": True}
    js = rodar_js("Montar E-mail", [{"data": emails}], {"Calcular Nova Data Boleto 50%": [pedido],
                                                        "Restaurar Pedido": [{**pedido, "alteracaoData": alt}]})
    igual(js, [X.montar_email_vendedor(pedido, emails, alt)])
    itens = [{"pedidoLider": "1", "acaoReincidencia": "ESCALAR", "RESPONSÁVEL": "DANIELA", "Pedido": "(11) 1",
              "diasSemRetorno": ["2026-11-10", "2026-11-11"], "telefone": "31999"},
             {"pedidoLider": "2", "acaoReincidencia": "JA_ESCALADO", "RESPONSÁVEL": "DANIELA"},
             {"pedidoLider": "3", "acaoReincidencia": "NORMAL", "RESPONSÁVEL": "RAYNNER"},
             {"pedidoLider": "4", "acaoReincidencia": "ESCALAR", "RESPONSÁVEL": "FULANO"}]
    js2 = rodar_js("Montar e-mail ao consultor (reincidência)", [{"data": emails}], {"Verificar resposta tardia": itens})
    igual(js2, M.montar_emails_consultor_reincidencia(itens, emails))


def test_quantidade_planejados_corrigida():
    """Divergência intencional da v28: '1.0' não pode virar 10x."""
    assert M.linha_item_planejado({"descricao": "MESA - X", "quantidade": "1.0"}) == "• MESA"
    assert M.linha_item_planejado({"descricao": "CADEIRA - X", "quantidade": "2,00"}) == "• 2x CADEIRA"
    assert M.linha_item_planejado({"descricao": "BANCO", "quantidade": "1.000,00"}) == "• 1000x BANCO"
