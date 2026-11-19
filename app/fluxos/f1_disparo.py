"""FLUXO 1 — disparo pelo painel (webhook 'disparar-fluxo-lider' / execução manual).

Mesma sequência de nós da v28. Os itens andam em lista, como no n8n: cada etapa recebe
os pedidos que chegaram a ela e devolve os que seguem por cada saída.
"""
import logging
import threading
import time
import traceback

from .. import comum as C
from .. import tabelas as T
from ..integracoes import digisac, email, planilha, rotas_geo
from ..integracoes.intranet import Intranet
from ..registro import alertar_erro
from . import gatilho
from . import f1_extracao as X
from . import f1_mensagens as M

log = logging.getLogger("central")
EMAIL_EXPEDICAO = "expedicaobh@lider.design"
EMAIL_ALERTA = "mateus.oliveira@lider.design"

MAPA_STATUS = {
    "Status: Coletando dados da planilha": ("Coletando dados da planilha", 8),
    "Status: Acessando a intranet": ("Acessando a intranet", 18),
    "Status: Consultando pedidos na intranet": ("Consultando pedidos na intranet", 28),
    "Status: Verificando entregas realizadas": ("Verificando entregas realizadas", 40),
    "Status: Verificando boletos": ("Verificando boletos", 52),
    "Status: Verificando pedidos de outlet": ("Verificando pedidos de outlet", 58),
    "Status: Calculando rota e prazo": ("Calculando rota e prazo de entrega", 64),
    "Status: Registrando pendências": ("Registrando pendências para preenchimento manual", 0),
    "Status: Pesquisando contatos": ("Pesquisando contatos no Digisac", 78),
    "Status: Montando e enviando mensagens": ("Montando e enviando mensagens", 88),
    "Status: Registrando envios": ("Registrando envios", 96),
}

_lock_disparo = threading.Lock()
PROGRESSO_A_CADA_S = 20   # etapas longas (pedido a pedido) avisam a tela no máximo a cada 20 s


class Disparo:
    def __init__(self, disparo_id=None, evento_inicial_gravado: bool = False):
        self.disparo_id = disparo_id
        self.evento_inicial_gravado = evento_inicial_gravado
        self.no = "Evento inicial do disparo"
        self.intranet = Intranet()
        self.html_boletos: list[str] = []
        self._emails_html: str | None = None
        self.tardia_por_pedido: dict[str, dict] = {}
        self._ultimo_progresso = 0.0

    # ------------------------------------------------------------ progresso (FLUXO_STATUS)
    def status(self, nome_no: str, itens: list | None = None):
        """noOp 'Status: ...' + 'Montar evento de status' + 'Salvar evento de status'.
        Só registra se chegou ao menos 1 item (no n8n o nó não roda sem itens)."""
        if itens is not None and not itens:
            return
        self.no = nome_no
        if nome_no == "Status: Coletando dados da planilha" and self.evento_inicial_gravado:
            return
        msg, pct = MAPA_STATUS.get(nome_no, (nome_no.replace("Status: ", ""), 0))
        self._gravar_evento(msg, pct, nome_no)
        self._ultimo_progresso = time.monotonic()

    def _gravar_evento(self, msg: str, pct, nome_no: str, tipo: str = "info"):
        try:
            T.insert("FLUXO_STATUS", {"disparoId": self.disparo_id, "ts": C.agora_ms(), "tipo": tipo,
                                      "msg": msg, "pct": str(pct), "no": nome_no})
        except Exception:  # noqa: BLE001  (onError=continueRegularOutput)
            log.exception("Falha ao gravar evento de status")

    def progresso(self, nome_no: str, feitos: int, total: int, pct_ate: int):
        """Etapa longa: grava 'Etapa (feitos/total)' no máximo a cada PROGRESSO_A_CADA_S.
        Mostra na tela que o fluxo segue vivo. O % avança entre o da etapa e pct_ate."""
        if not total or time.monotonic() - self._ultimo_progresso < PROGRESSO_A_CADA_S:
            return
        msg, pct = MAPA_STATUS.get(nome_no, (nome_no.replace("Status: ", ""), 0))
        pct = int(pct + (pct_ate - pct) * feitos / total)
        self._gravar_evento(f"{msg} ({feitos}/{total})", pct, nome_no)
        self._ultimo_progresso = time.monotonic()

    def concluir(self):
        """Evento de fim real: a tela só mostra 100 % quando ele chega (ou por erro)."""
        self._gravar_evento("Fluxo concluído", 100, "Fim do disparo", tipo="fim")

    def _emails(self) -> str:
        """Nó 'Lista de e-mails' (inf/emails.php)."""
        if self._emails_html is None:
            self._emails_html = self.intranet.lista_emails().get("data") or ""
        return self._emails_html

    # ------------------------------------------------------------ execução
    def executar(self):
        self.status("Status: Coletando dados da planilha")
        self.limpeza_diaria()

        self.no = "Get row(s) in sheet"
        linhas = planilha.ler_linhas()
        pedidos = [X.preparar_pedido(l) for l in linhas]
        if not pedidos:
            log.info("Planilha sem linhas: nada a fazer")
            return

        self.no = "Anotar Pedidos Iniciais"
        for p in pedidos:
            dados = {k: v for k, v in p.items()}
            T.upsert("AGUARDANDO_ENTREGA", {"pedidoLider": p.get("pedido")}, {
                "cliente": p.get("Cliente") or p.get("cliente") or "",
                "responsavel": p.get("RESPONSÁVEL") or "", "status": "EM_PROCESSAMENTO",
                "enviadoEm": C.agora_iso(), "dadosPedido": C.dumps(dados)})

        self.status("Status: Acessando a intranet", pedidos)
        self.no = "Login Intranet"
        self.intranet.login()

        self.status("Status: Consultando pedidos na intranet", pedidos)
        self.no = "Buscar Pedido"
        htmls = []
        for i, p in enumerate(pedidos):
            htmls.append(self.intranet.pedido_lojas(p.get("pedido") or ""))
            self.progresso("Status: Consultando pedidos na intranet", i + 1, len(pedidos), 39)
        self.no = "Extrair Dados Pedido"
        if any(X.html_eh_tela_login(h) for h in htmls):
            raise RuntimeError("Sessão da intranet inválida: a consulta de pedidos retornou a tela de login. "
                               "Nenhum pedido foi marcado como cancelado. Verifique usuário/senha e dispare novamente.")
        extraidos = [X.extrair_dados_pedido(h, pedidos[i]) for i, h in enumerate(htmls)]

        cancelados = [p for p in extraidos if p["pedidoCancelado"] is True]
        ativos = [p for p in extraidos if p["pedidoCancelado"] is not True]
        self.marcar_cancelados(cancelados)

        self.status("Status: Verificando entregas realizadas", ativos)
        entregues, seguem = self.verificar_entregas(ativos)
        self.registrar_entregues(entregues)

        seguem = [X.verificar_planejado_data_absurda(p) for p in seguem]
        conferir = [p for p in seguem if p.get("pularBoleto") is False]
        pular = [p for p in seguem if p.get("pularBoleto") is not False]

        merge1 = self.boletos(conferir) + pular   # Merge1: entrada 0 (boleto ok) + entrada 1 (pular)
        self.status("Status: Verificando pedidos de outlet", merge1)
        nao_outlet = self.outlet(merge1)

        self.status("Status: Calculando rota e prazo", nao_outlet)
        com_rota = [X.preparar_rota(X.classificar_tipo_movel(p)) for p in nao_outlet]
        origem_ok = [p for p in com_rota if (p.get("rota") or {}).get("semPendencia") is True]
        pendentes = [p for p in com_rota if (p.get("rota") or {}).get("semPendencia") is not True]
        self.registrar_pendencias(pendentes)

        calculados = self.calcular_rotas(origem_ok)
        if not calculados:
            return
        self.reincidencia_e_contatos(calculados)

    # ------------------------------------------------------------ limpeza diária
    def limpeza_diaria(self):
        self.no = "Selecionar eventos antigos"
        limite = C.agora_ms() - 3 * 86400000
        antigos_ev = [r["id"] for r in T.get("FLUXO_STATUS") if r.get("id") is not None
                      and float(r.get("ts") or 0) > 0 and float(r.get("ts") or 0) < limite]
        if antigos_ev:
            T.delete_rows("FLUXO_STATUS", {"id": ("in", antigos_ev)})

        # Ajuste do Flask: conversa com mais de 30 dias não serve mais para nada (tardia, lembrete, agrupamento)
        try:
            corte_msg = C.agora_ms() - 30 * 86400000
            T.delete_rows("MENSAGENS_CLIENTE", {"ts": ("lt", corte_msg)})
        except Exception:  # noqa: BLE001
            log.exception("Limpeza de mensagens antigas")

        self.no = "Separar dias anteriores"
        hoje = C.hoje_iso()
        todas = T.get("AGUARDANDO_ENTREGA")

        def status_efetivo(r):
            if str(r.get("status") or "") != "AGRUPADO":
                return str(r.get("status") or "")
            dp = C.loads(r.get("dadosPedido"), {}) or {}
            p = next((x for x in todas if str(x.get("pedidoLider") or "") == str(dp.get("agrupadoEm") or "")
                      and x.get("status") != "AGRUPADO"), None)
            return str(p.get("status") or "") if p else "AGRUPADO"

        antigos = []
        for r in todas:
            dia = (r.get("createdAt") or "")[:10] or None
            if not dia or dia >= hoje:
                continue
            if str(r.get("status") or "") == "PENDENTE_RESPOSTA_TARDIA":
                continue
            antigos.append({"id": r["id"], "dataReferencia": dia, "pedidoLider": str(r.get("pedidoLider") or ""),
                            "cliente": str(r.get("cliente") or ""), "responsavel": str(r.get("responsavel") or ""),
                            "status": status_efetivo(r), "criadoEm": str(r.get("createdAt") or ""),
                            "atualizadoEm": str(r.get("updatedAt") or ""), "dados": C.dumps(r)})
        if not antigos:
            return
        self.no = "Arquivar no HISTORICO_PEDIDOS"
        for a in antigos:
            T.upsert("HISTORICO_PEDIDOS", {"idOriginal": str(a["id"])}, {
                "dataReferencia": a["dataReferencia"], "pedidoLider": a["pedidoLider"], "cliente": a["cliente"],
                "responsavel": a["responsavel"], "status": a["status"], "criadoEm": a["criadoEm"],
                "atualizadoEm": a["atualizadoEm"], "arquivadoEm": C.agora_iso(), "dados": a["dados"]})
        self.no = "Apagar dias anteriores"
        T.delete_rows("AGUARDANDO_ENTREGA", {"id": ("in", [a["id"] for a in antigos])})
        log.info("Limpeza diária: %s arquivados", len(antigos))

    # ------------------------------------------------------------ cancelados
    def marcar_cancelados(self, cancelados):
        for p in cancelados:
            self.no = "Marcar Cancelado Data Table"
            nao_loc = p.get("statusCancelamento") == "PEDIDO_NAO_LOCALIZADO"
            T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p.get("pedidoLider")}, {
                "status": p.get("statusCancelamento") or "PEDIDO_CANCELADO",
                "resumoIA": "Pedido não localizado na Intranet (verificar número na planilha)" if nao_loc else "Pedido cancelado na Intranet",
                "dadosPedido": C.dumps(p)})
            self.no = "Sheet – Pedido Cancelado"
            planilha.atualizar("Pedido", p.get("Pedido"), {
                "CONFIRMADO": "NÃO", "DATA ENVIO CONF.": C.carimbo_br(),
                "MOTIVO": p.get("motivoCancelamento") or "PEDIDO CANCELADO"})

    # ------------------------------------------------------------ entregas realizadas
    def verificar_entregas(self, ativos):
        entregues, seguem = [], []
        for p in ativos:
            self.no = "Preparar Verificação de Entrega"
            p = X.preparar_verificacao_entrega(p)
            if p["consultarEntregaPorProduto"] is False:
                p = X.verificar_entrega_realizada(p)
                (entregues if p["entregaJaPassou"] is True else seguem).append(p)
            else:
                p = X.preservar_dados_pedido(p)
                self.no = "Cosultada Data Produto"
                resp = self.intranet.situacao_pedidos(p.get("pedidoLider"))
                self.no = "Extrair Entrega por Produto"
                p = X.extrair_entrega_por_produto(str(resp.get("data") or ""), p)
                (entregues if (p.get("semProdutosPendentes") or p.get("entregaParcialVencida")) else seguem).append(p)
        return entregues, seguem

    def registrar_entregues(self, entregues):
        if not entregues:
            return
        for p in entregues:
            self.no = "Marcar Pedido Entregue"
            T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p.get("pedidoLider")}, {
                "status": "PEDIDO_ENTREGUE", "resumoIA": "Pedido já entregue ou retirado na loja",
                "dadosPedido": C.dumps(p)})
            self.no = "Sheet – Já Faturado"
            planilha.atualizar("Pedido", p.get("Pedido"), {
                "DATA ENVIO CONF.": C.carimbo_br(), "CONFIRMADO": "NÃO", "MOTIVO": "JÁ FATURADO"})
        self.no = "Montar E-mail Expedição"
        e = X.montar_email_expedicao(entregues)
        email.enviar(EMAIL_EXPEDICAO, e["assunto"], e["html"])

    # ------------------------------------------------------------ boletos
    def boletos(self, conferir) -> list[dict]:
        """Devolve os pedidos que seguem para o Merge1 (boleto OK / não encontrado)."""
        if not conferir:
            return []
        self.status("Status: Verificando boletos", conferir)
        tratados = []
        for p in conferir:
            self.no = "Conferir Boletos"
            dp = p.get("dataPedidoLider")
            data_iso = "-".join(reversed(dp.split("/"))) if dp else ""
            resp = self.intranet.conferir_boletos(data_iso)
            self.html_boletos.append(str(resp.get("data") or ""))
            self.no = "Tratar Conferência Boleto"
            tratados.append(X.tratar_conferencia_boleto(resp, p))
            self.progresso("Status: Verificando boletos", len(tratados), len(conferir), 57)

        seguem, analisar = [], []
        for p in tratados:
            st = p["boleto"]["status"]
            if st in ("ANALISAR", "ERRO_CONSULTA"):
                analisar.append(p)
                self._bloquear_boleto(p)
            elif st == "BOLETO_JA_TRATADO":
                self._bloquear_boleto(p)
            else:
                seguem.append(p)
        self.boleto_50(analisar)
        return seguem

    def _bloquear_boleto(self, p):
        self.no = "Bloquear pedido (pendência de boleto)"
        T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p.get("pedidoLider")}, {"status": "PENDENCIA_BOLETO"})

    def boleto_50(self, analisar):
        if not analisar:
            return
        falhas = []
        for p in analisar:
            self.no = "Analisar 50% do Pedido"
            p = X.analisar_50(p, self.html_boletos)
            self.no = "Calcular Nova Data Boleto 50%"
            p = X.calcular_nova_data_50(p)
            pg = p.get("pagamento50") or {}
            if not (pg.get("status") == "OK" and pg.get("novaDataEntrega")):
                falhas.append(p)
                continue
            self.no = "Abrir Formulário Alteração"
            data_iso = "-".join(reversed(pg["novaDataEntrega"].split("/")))
            form = self.intranet.abrir_form_alteracao(data_iso, p.get("pedidoLider"))
            self.no = "Montar URL Alteração"
            url = X.montar_url_alteracao(str(form.get("data") or ""), p, self.intranet.base)
            resp = {"data": ""}
            if url.get("urlAlterar"):
                self.no = "Alterar Data - Boleto 50%"
                resp = self.intranet.alterar_data(url["urlAlterar"])
            else:
                resp = {"error": "URL vazia (formulário sem itens)", "data": ""}
            self.no = "Restaurar Pedido"
            alteracao = {
                "itensAlterados": url.get("qtdItens"),
                "sucesso": bool(url.get("urlAlterar")) and not resp.get("error"),
                "erro": url.get("erroFormulario") or (str(resp["error"]) if resp.get("error") else None),
                "respostaResumo": C.limpar(C.sem_tags(resp.get("data")))[:300]}
            p = {**p, "alteracaoData": alteracao}
            if alteracao["sucesso"] is True:
                self.no = "Observação - Boleto 50%"
                self.intranet.aviso_entrega(
                    p.get("pedidoLider"), p.get("clienteLider"), pg["novaDataEntrega"], "BOLETO 50%",
                    f'PRAZO DE ENTREGA DO PEDIDO {p["boleto"]["pedido"]} ALTERADO DE "{p.get("entregaLider")}" para '
                    f'"{pg["novaDataEntrega"]}" - vencimento do boleto de 50% para "{pg.get("vencimento50")}"')
            self.no = "Montar E-mail"
            p = X.montar_email_vendedor(p, self._emails(), alteracao)
            self.no = "Send an Email"
            email.enviar(p["email"]["para"], p["email"]["assunto"], p["email"]["html"])
            self.no = "Sheet – Boleto 50%"
            planilha.atualizar("Pedido", p.get("Pedido"), {
                "CONFIRMADO": "NÃO", "DATA ENVIO CONF.": C.carimbo_br(), "MOTIVO": "BOLETO/ 50%"})
            self.no = "Registrar 50%"
            T.upsert("AGUARDANDO_ENTREGA", {"pedidoLider": p.get("pedidoLider")}, {"status": "PENDENCIA_BOLETO"})
        if falhas:
            self.no = "Montar alerta 50% (falha)"
            a = X.montar_alerta_50(falhas)
            email.enviar(EMAIL_ALERTA, a["assunto"], a["html"])

    # ------------------------------------------------------------ outlet
    def outlet(self, pedidos) -> list[dict]:
        nao_outlet = []
        for p in pedidos:
            self.no = "Consultar estoque (outlet)"
            resp = self.intranet.situacao_pedidos(p.get("pedidoLider"))
            self.no = "Verificar outlet"
            p = X.verificar_outlet(p, str(resp.get("data") or ""))
            if p.get("outlet") is not True:
                nao_outlet.append(p)
                continue
            self.no = "Montar registro (outlet)"
            r = X.montar_registro_outlet(p)
            self.no = "Marcar outlet (AGUARDANDO_ENTREGA)"
            T.update("AGUARDANDO_ENTREGA", {"pedidoLider": r.get("pedidoLider")}, {
                "status": r["statusFinal"], "categoria": r["categoria"], "resumoIA": r["resumoOutlet"],
                "enviadoEm": r["registradoEm"], "respondidoEm": r["registradoEm"], "dadosPedido": C.dumps(r)})
            self.no = "Sheet – Outlet"
            planilha.atualizar("Pedido", r["pedidoSheet"], {
                "CONFIRMADO": r["sheetG"], "MOTIVO": r["sheetH"], "DATA ENVIO CONF.": r["sheetI"]})
            if r["temDataIntranet"] is True:
                self.no = "Observação Intranet (outlet)"
                self.intranet.aviso_entrega(r.get("pedidoLider"), r["clienteIntranet"], r["datEntrega"],
                                            "CONFIRMACAO DE DATA DE ENTREGA", r["observacaoOutlet"])
        return nao_outlet

    # ------------------------------------------------------------ pendências (PENDENTE_DESTINO)
    def registrar_pendencias(self, pendentes):
        if not pendentes:
            return
        self.status("Status: Registrando pendências", pendentes)
        for p in pendentes:
            self.no = "Registrar Pendência Central"
            T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p.get("pedidoLider")}, {
                "pedidoLider": p.get("pedidoLider"), "responsavel": p.get("RESPONSÁVEL"), "status": "PENDENTE_DESTINO",
                "cliente": p.get("clienteLider"), "enviadoEm": C.agora_iso(), "dadosPedido": C.dumps(p)})

    # ------------------------------------------------------------ coordenadas, rota, prazo
    def calcular_rotas(self, origem_ok) -> list[dict]:
        if not origem_ok:
            return []
        self.no = "Resolver Coordenadas (Tabela)"
        faltantes = X.cidades_faltantes(origem_ok)
        novas = {}
        for f in faltantes:
            self.no = "Geocodificar Cidade"
            r = rotas_geo.geocodificar(f["cidade"], f["uf"])
            lista = C.loads(r.get("data") or "[]", []) or []
            if lista and isinstance(lista, list):
                try:
                    novas[f["chave"]] = {"lat": float(lista[0]["lat"]), "lon": float(lista[0]["lon"])}
                except (KeyError, ValueError, TypeError):
                    pass
        self.no = "Preparar Coordenadas OSRM"
        coords = X.preparar_coordenadas(origem_ok, novas)
        validos = [p for p in coords if p["coordenadasValidas"] is True]
        self.registrar_pendencias([p for p in coords if p["coordenadasValidas"] is not True])
        saida = []
        for p in validos:
            self.no = "Calcular Rota OSRM"
            resp = rotas_geo.rota(p["coordenadas"]["origem"], p["coordenadas"]["destino"])
            self.no = "Tratar Distância"
            p = X.tratar_distancia(resp, p)
            self.no = "Calcular Data de Entrega"
            saida.append(X.calcular_data_entrega(p))
        return saida

    # ------------------------------------------------------------ reincidência, tardia, contatos, mensagens
    def reincidencia_e_contatos(self, calculados):
        self.no = "Ler SEM_CONFIRMACAO_DIARIO"
        sem_conf = T.get("SEM_CONFIRMACAO_DIARIO")
        self.no = "Ler MENSAGENS_CLIENTE (resposta tardia)"
        try:
            msgs = T.get("MENSAGENS_CLIENTE")
        except Exception:  # noqa: BLE001
            msgs = []
        self.no = "Verificar reincidência sem retorno"
        itens = X.verificar_reincidencia(calculados, sem_conf)
        self.no = "Verificar resposta tardia"
        itens = X.verificar_resposta_tardia(itens, sem_conf, msgs)
        self.tardia_por_pedido = {C.n_ped(p.get("pedidoLider")): p["respostaTardia"]
                                  for p in itens if p.get("respostaTardia")}

        normais = []
        for p in itens:
            acao = p.get("acaoReincidencia")
            if acao == "ESCALAR":
                self.no = "Marcar escalado (sem confirmação)"
                T.update("SEM_CONFIRMACAO_DIARIO", {"pedidoLider": p.get("pedidoLider")}, {"status": "ESCALADO"})
                self.no = "Marcar ESCALADO (AGUARDANDO_ENTREGA)"
                T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p.get("pedidoLider")}, {
                    "status": "ESCALADO",
                    "resumoIA": f"Sem confirmação em {p['qtdDiasSemRetorno']} dias ({', '.join(p['diasSemRetorno'])}); "
                                f"encaminhado ao consultor em {C.agora().strftime('%d/%m/%Y %H:%M')}"})
            elif acao == "JA_ESCALADO":
                self.no = "Marcar já encaminhado (AGUARDANDO_ENTREGA)"
                T.update("AGUARDANDO_ENTREGA", {"pedidoLider": p.get("pedidoLider")}, {
                    "status": "ESCALADO",
                    "resumoIA": f"Sem confirmação em {p['qtdDiasSemRetorno']} dias ({', '.join(p.get('diasSemRetorno') or [])}); "
                                f"já tinha sido encaminhado ao consultor, não reenviado em {C.agora().strftime('%d/%m/%Y %H:%M')}"})
            else:
                normais.append(p)
            if p.get("respostaTardia"):
                self.no = "Marcar respondeu depois (SEM_CONFIRMACAO)"
                try:
                    T.update("SEM_CONFIRMACAO_DIARIO", {"pedidoLider": p["respostaTardia"]["pedidoLiderRegistro"],
                                                        "dataRef": p["respostaTardia"]["dataRef"]}, {"status": "RESPONDEU_DEPOIS"})
                except Exception:  # noqa: BLE001
                    log.exception("Marcar respondeu depois")

        if any(p.get("acaoReincidencia") in ("ESCALAR", "JA_ESCALADO") for p in itens):
            self.no = "Montar e-mail ao consultor (reincidência)"
            for e in M.montar_emails_consultor_reincidencia(itens, self._emails()):
                email.enviar(e["para"], e["assunto"], e["html"])

        self.status("Status: Pesquisando contatos", normais)
        para_contato = []
        for p in normais:
            if (p.get("boleto") or {}).get("status") in ("ANALISAR", "ERRO_CONSULTA", "BOLETO_JA_TRATADO") \
                    or p.get("pagamento50") or "BOLETO" in str(p.get("motivoPlanilha") or "").upper():
                self._bloquear_boleto(p)
            else:
                para_contato.append(p)

        self.no = "Preparar Tentativas Digisac"
        prep = [M.preparar_tentativas(p) for p in para_contato]
        self.registrar_pendencias([p for p in prep if p.get("semCelularValido") is True])
        com_cel = [p for p in prep if p.get("semCelularValido") is not True]

        contatos = [self.buscar_contato(p) for p in com_cel]   # Loop Over Items1
        if contatos:
            self.mensagens(contatos)

    def buscar_contato(self, p: dict) -> dict:
        """Loop Over Items1: tenta cada telefone x serviço; se não achar, cria o contato."""
        atual = dict(p)
        while True:
            self.no = "Preparar Busca Digisac"
            t = atual["tentativas"][atual["tentativaAtual"]]
            busca_in = {**atual, "phoneBusca": t["phone"], "serviceBusca": t["serviceId"], "chaveBusca": t["chave"]}
            self.no = "Busca Digisac"
            r = digisac.buscar_contatos(busca_in["phoneBusca"], busca_in["serviceBusca"])
            self.no = "Verificar Busca Digisac"
            v = M.verificar_busca(r, busca_in)
            if v.get("achou") is True:
                return v
            atual = {**v, "tentativaAtual": v["tentativaAtual"] + 1}
            if atual["tentativaAtual"] < len(atual["tentativas"]):
                continue
            if (atual.get("errosBusca") or 0) > 0:
                self.no = "Marcar erro de busca Digisac"
                return {**atual, "statusBusca": "ERRO_BUSCA_DIGISAC", "contactId": None}
            self.no = "Criar Contato"
            criado = digisac.criar_contato(M.nome_contato(atual), atual.get("phone"))
            self.no = "Resultado Criação"
            if not (criado or {}).get("id"):
                return {**atual, "statusBusca": "ERRO_CRIAR_CONTATO", "erro": C.dumps(criado)}
            return {**atual, "statusBusca": "CRIADO", "contactId": criado["id"],
                    "serviceId": criado.get("serviceId") or atual.get("serviceCriacao"), "phone": atual.get("phone")}

    def mensagens(self, contatos):
        self.status("Status: Montando e enviando mensagens", contatos)
        soltos = [p for p in contatos if p.get("tipoMovel") == "Moveis soltos"]
        planej = [p for p in contatos if p.get("tipoMovel") == "Planejados"]
        sem_tipo = [p for p in contatos if p.get("tipoMovel") not in ("Moveis soltos", "Planejados")]

        msgs_soltos = []
        for p in soltos:
            self.no = "Consultar Itens Solto"
            r = self.intranet.situacao_pedidos(p.get("pedidoLider"))
            self.no = "Montar Mensagem Soltos"
            msgs_soltos.append(M.montar_mensagem_soltos(p, str(r.get("data") or "")))

        msgs_plan = []
        if planej:
            respostas = []
            for p in planej:
                self.no = "Consultar Itens Planejado"
                respostas.append(self.intranet.situacao_pedidos(p.get("pedidoLider")))
            self.no = "Consultar Projetos Postados"
            proj = self.intranet.projetos_postados()
            idx, valida = M.indice_projetos(str(proj.get("data") or ""))
            for p, r in zip(planej, respostas):
                self.no = "Montar Mensagem Planejados"
                msgs_plan.append(M.montar_mensagem_planejados(p, str(r.get("data") or ""), idx, valida))

        if sem_tipo:
            self.no = "Responsável sem tipo de móvel"
            itens = [{**p, "bloqueado": True,
                      "motivosBloqueio": f'Responsável "{str(p.get("RESPONSÁVEL") or "").strip() or "vazio"}" '
                                         f"não está cadastrado em Planejados nem Móveis soltos"} for p in sem_tipo]
            self.status("Status: Registrando envios", itens)
            self.registrar_revisao(itens)

        juncao = msgs_soltos + msgs_plan
        if juncao:
            self.no = "Agrupar pedidos do mesmo cliente"
            agrupados = M.agrupar_pedidos(juncao, list(self.tardia_por_pedido.keys()))
            self.status("Status: Registrando envios", agrupados)
            self.registrar_revisao(agrupados)

    def registrar_revisao(self, itens):
        for j in itens:
            self.no = "Registrar Revisão"
            tardia = self.tardia_por_pedido.get(C.n_ped(j.get("pedidoLider")))
            status = ("AGRUPADO" if j.get("agrupadoEm") else "BLOQUEADO" if j.get("bloqueado")
                      else "PENDENTE_RESPOSTA_TARDIA" if tardia else "PENDENTE_REVISAO")
            T.upsert("AGUARDANDO_ENTREGA", {"pedidoLider": j.get("pedidoLider")}, {
                "status": status,
                "dadosPedido": C.dumps({**j, "motivoRevisao": j.get("motivosBloqueio"), "respostaTardia": tardia})})


# ---------------------------------------------------------------- erro (gatilho 'Erro no fluxo')
def registrar_erro_disparo(no: str, exc: BaseException):
    msg = str(exc) or exc.__class__.__name__
    try:
        T.insert("FLUXO_STATUS", {"disparoId": None, "ts": C.agora_ms(), "tipo": "erro",
                                  "msg": msg[:1500], "pct": "0", "no": no})
    except Exception:  # noqa: BLE001
        log.exception("Falha ao gravar evento de erro")
    alertar_erro(no, exc)


def rodar_disparo(disparo_id=None, evento_inicial_gravado: bool = False):
    if not _lock_disparo.acquire(blocking=False):
        log.warning("Já existe um disparo em andamento; este foi enfileirado")
        _lock_disparo.acquire()
    d = Disparo(disparo_id, evento_inicial_gravado)
    try:
        d.executar()
        d.concluir()
    except Exception as exc:  # noqa: BLE001
        log.error("Disparo falhou no nó %s: %s\n%s", d.no, exc, traceback.format_exc())
        registrar_erro_disparo(d.no, exc)
    finally:
        _lock_disparo.release()


@gatilho("disparar-fluxo-lider")
def disparar(entrada, req):
    """Webhook responde na hora (responseMode onReceived) e o fluxo roda em segundo plano."""
    disparo_id = (entrada.get("body") or {}).get("disparoId") if isinstance(entrada.get("body"), dict) else None
    T.insert("FLUXO_STATUS", {"disparoId": disparo_id, "ts": C.agora_ms(), "tipo": "info",
                              "msg": "Coletando dados da planilha", "pct": "8",
                              "no": "Status: Coletando dados da planilha"})
    # o evento inicial já foi gravado aqui: a tela enxerga o disparo em poucos segundos
    threading.Thread(target=rodar_disparo, args=(disparo_id, True), name="disparo", daemon=True).start()
    return {"message": "Workflow was started"}, 200
