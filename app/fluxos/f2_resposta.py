"""FLUXO 2 — webhook 'digisac-resposta' (DigiSac - Aguardar confirmação).

Mesma ordem de nós da v28. Responde 200 na hora; o processamento roda em segundo plano
(inclui a espera de 60 s para juntar as mensagens seguidas do cliente).
"""
import base64
import logging
import mimetypes
import time
from datetime import timedelta
from pathlib import Path

from .. import comum as C
from .. import tabelas as T
from ..config import RAIZ
from ..integracoes import digisac, email, gemini, planilha
from ..integracoes.intranet import Intranet
from . import gatilho
from . import f2_logica as L
from . import prompts as P
from .f1_revisao import DEPARTAMENTO_CENTRAL, listar_usuarios_todos

log = logging.getLogger("central")
ESPERA_AGRUPAR_S = 60
EMAIL_AVISOS = "mateus.oliveira@lider.design"
ARQUIVOS_DIR = RAIZ / "arquivos"          # '/files/LIDER.mp4' do n8n -> arquivos/LIDER.mp4
LIMITE_WHATSAPP = 16 * 1024 * 1024


def _mais_1h() -> str:
    return (C.agora() + timedelta(hours=1)).isoformat(timespec="milliseconds")


def _registrar_bot(contact_id, texto):
    """Nós 'Preparar registro da resposta' + 'Registrar resposta da Líder'."""
    if not contact_id or not str(texto or "").strip():
        return
    ts = C.agora_ms()
    try:
        T.insert("MENSAGENS_CLIENTE", {"contactId": contact_id, "messageId": f"lider-{ts}", "papel": "BOT",
                                       "texto": str(texto)[:3000], "ts": ts, "recebidoEm": C.agora_iso()})
    except Exception:  # noqa: BLE001
        log.exception("Registrar resposta da Líder")


DIAS_RESPOSTA_TARDIA = 30   # contato encerrado sem retorno continua "atendido" por esse prazo


def contato_atendido(contact_id) -> bool:
    """Só grava/processa mensagens de quem o sistema está atendendo:
    - contato de algum pedido em AGUARDANDO_ENTREGA (qualquer etapa), ou
    - contato encerrado sem retorno nos últimos 30 dias (base da resposta tardia)."""
    if not contact_id:
        return False
    if T.get("AGUARDANDO_ENTREGA", {"contactId": str(contact_id)}, limite=1):
        return True
    limite = (C.agora().date() - timedelta(days=DIAS_RESPOSTA_TARDIA)).isoformat()
    return bool(T.get("SEM_CONFIRMACAO_DIARIO", {"contactId": str(contact_id), "dataRef": ("gte", limite)}, limite=1))


def limpar_mensagens_nao_atendidas() -> int:
    """Apaga mensagens já gravadas de contatos que o sistema não atende (roda ao iniciar o servidor)."""
    from .. import db
    contatos = {r["contactId"] for r in db.consultar("SELECT DISTINCT contactId FROM MENSAGENS_CLIENTE")}
    apagar = [c for c in contatos if not contato_atendido(c)]
    total = 0
    for i in range(0, len(apagar), 500):
        total += T.delete_rows("MENSAGENS_CLIENTE", {"contactId": ("in", apagar[i:i + 500])})
    return total


def _conversa(contact_id):
    try:
        return T.get("MENSAGENS_CLIENTE", {"contactId": contact_id})
    except Exception:  # noqa: BLE001
        return []


class Resposta:
    def __init__(self, entrada: dict):
        self.entrada = entrada
        self.no = "Filtrar Mensagem"

    # ================================================================ início
    def executar(self, esperar: bool = True):
        me = L.filtrar_mensagem(self.entrada)
        if not me:
            return
        # Ajuste do Flask (13/11): o n8n gravava TODAS as mensagens do DigiSac.
        # Aqui só entra quem o sistema atende; o resto é descartado sem gravar e sem esperar 60 s.
        if not contato_atendido(me.get("contactId")):
            return
        self.no = "Registrar mensagem do cliente"
        try:
            T.insert("MENSAGENS_CLIENTE", {"contactId": me.get("contactId"), "messageId": me["messageId"], "papel": "CLIENTE",
                                           "texto": me["text"], "ts": me["ts"], "recebidoEm": C.agora_iso()})
        except Exception:  # noqa: BLE001
            log.exception("Registrar mensagem do cliente")
        if esperar:
            time.sleep(ESPERA_AGRUPAR_S)
        self.no = "Agrupar mensagens do cliente"
        msg = L.agrupar_mensagens(me, _conversa(me.get("contactId")))
        if not msg:
            return
        self.no = "Escolher Linha"
        linhas = L.escolher_linha(msg, T.get("AGUARDANDO_ENTREGA", {"contactId": msg.get("contactId")}))
        if not linhas:
            return
        self.linhas = linhas
        self.linha = linhas[0]
        fluxo = self.linha["fluxo"]
        log.info("Resposta do cliente %s: fluxo %s (pedido %s)", msg.get("contactId"), fluxo, self.linha.get("pedidoLider"))
        if fluxo == "TEMPLATE":
            self.template_aceito(linhas)
        elif fluxo == "IA":
            self.ia(self.linha)
        elif fluxo == "DECISAO_RESPONSAVEL":
            self.decisao_responsavel(self.linha)
        elif fluxo == "CONSULTOR_MSG":
            self.no = "Anexar mensagem do cliente ao chat"
            r = L.anexar_mensagem_chat(self.linha)
            T.update("AGUARDANDO_ENTREGA", {"id": r["id"]}, {"chatConsultor": r["chatConsultor"]})
        elif fluxo == "VIGILANCIA":
            self.vigilancia(self.linha)

    # ================================================================ TEMPLATE aceito: envia a mensagem programada
    def template_aceito(self, linhas):
        com_video = [l for l in linhas if l.get("tipoMensagem") == "PRIMEIRA_CONFIRMACAO"
                     and str(l.get("anexoUrl") or "").startswith("/files/")]
        sem_video = [l for l in linhas if l not in com_video]
        prontos = []
        for l in com_video:
            self.no = "Enviar vídeo Digisac"
            l = {**l, "videoEnvio": self._enviar_video(l)}
            dados = C.loads(l.get("dadosPedido"), {}) if isinstance(l.get("dadosPedido"), str) else (l.get("dadosPedido") or {})
            dados = dados if isinstance(dados, dict) else {}
            dados["videoEnvio"] = l["videoEnvio"]
            try:
                T.update("AGUARDANDO_ENTREGA", {"id": l["id"]}, {"dadosPedido": C.dumps(dados)})
            except Exception:  # noqa: BLE001
                log.exception("Registrar envio do vídeo")
            prontos.append(l)
        originais = prontos + sem_video
        self.no = "Anti-repetição: pode enviar? (mensagem programada)"
        contato = originais[0].get("contactId") if originais else None
        liberados = L.anti_repeticao(originais, _conversa(contato), lambda j: j.get("mensagem"))
        if not liberados:
            return
        for l in liberados:
            self.no = "POST Enviar mensagem para contato ja cadastrado"
            digisac.enviar_mensagem(l.get("contactId"), l.get("mensagem"))
            self.no = "Att Enviar data"
            T.update("AGUARDANDO_ENTREGA", {"id": l["id"]}, {"status": "DATA_ENVIADA", "respondidoEm": C.agora_iso(),
                                                              "resposta": l.get("textoCliente")})
        _registrar_bot(self.linhas[0].get("contactId"),
                       "\n\n".join(x.get("mensagem") for x in self.linhas if x.get("mensagem")))

    def _enviar_video(self, l) -> dict:
        nome = str(l.get("anexoUrl"))[len("/files/"):]
        arq = ARQUIVOS_DIR / nome
        em = C.agora_iso()
        if not arq.exists():
            return {"status": "NAO_ENVIADO", "detalhe": f"ARQUIVO_NAO_LIDO: {arq} não existe", "em": em}
        dados = arq.read_bytes()
        if not dados:
            return {"status": "NAO_ENVIADO", "detalhe": "ARQUIVO_VAZIO", "em": em}
        if len(dados) > LIMITE_WHATSAPP:
            return {"status": "NAO_ENVIADO", "detalhe": f"ARQUIVO_MAIOR_QUE_16MB ({len(dados) / 1048576:.1f} MB)", "em": em}
        r = digisac.enviar_arquivo(l.get("contactId"), {"base64": base64.b64encode(dados).decode(),
                                                         "mimetype": mimetypes.guess_type(nome)[0] or "video/mp4", "name": nome})
        time.sleep(8)  # Aguardar vídeo subir (8s)
        em = C.agora_iso()
        if r.get("error"):
            e = r["error"]
            return {"status": "FALHOU", "detalhe": str(e.get("message") if isinstance(e, dict) else e)[:300], "em": em}
        if r.get("id"):
            return {"status": "ENVIADO", "detalhe": str(r["id"]), "em": em}
        return {"status": "FALHOU", "detalhe": "Resposta sem id: " + C.dumps(r)[:200], "em": em}

    # ================================================================ IA (resposta à data)
    def ia(self, linha_entrada: dict):
        self.no = "Preparar contexto IA"
        j = L.preparar_contexto(linha_entrada)
        self.no = "Basic LLM Chain"
        llm = gemini.gerar_json(P.montar("Basic LLM Chain", j), P.EXEMPLO_SAIDA_CATEGORIA, 0)
        out = llm.get("output") if isinstance(llm.get("output"), dict) else None
        base_resp = None
        if out and (out.get("foraDaRegra") is True or str(out.get("foraDaRegra")).lower() == "true"):
            self.no = "Ler base de conhecimento (1ª resposta)"
            base = T.get("BASE_CONHECIMENTO")
            texto_base, vazia = L.montar_baseTexto(base)
            consulta = {"textoCliente": str(j.get("textoCliente") or ""), "mensagem": str(j.get("mensagem") or ""),
                        "assuntoFora": str(out.get("assuntoFora") or out.get("resumo") or "").strip(),
                        "baseVazia": vazia, "baseTexto": texto_base}
            if vazia is False:
                self.no = "IA - Buscar resposta na base (1ª resposta)"
                r = gemini.gerar_texto(P.montar("IA - Buscar resposta na base (1ª resposta)", consulta), 0)
                ib = L.interpretar_resposta_base(r, base)
                base_resp = {"assuntoFora": consulta["assuntoFora"], **ib,
                             "respostaBase": ib["respostaBase"] if ib["usarBase"] else ""}
        self.no = "Normalizar Categoria"
        n = L.normalizar_categoria(self.linha, out or {}, base_resp)
        self.n = n
        if n["categoria"] == "PEDE_ADIAR" and n["adiamentoValido"] is True:
            self.adiamento(n)
            return
        if n["temResposta"] is True:
            self.no = "Anti-repetição: pode enviar? (resposta fixa)"
            if not L.anti_repeticao([n], _conversa(n.get("contactId")), lambda x: x.get("respostaFixa")):
                return
            self.no = "POST Enviar mensagem para contato ja cadastrado1"
            digisac.enviar_mensagem(n.get("contactId"), n["respostaFixa"])
            self.update_final(n)
            _registrar_bot(self.linha.get("contactId"), n["respostaFixa"])
        else:
            self.update_final(n)

    def update_final(self, n):
        self.no = "Update final"
        T.update("AGUARDANDO_ENTREGA", {"id": n["id"]}, {
            "status": n["statusFinal"], "categoria": n["categoria"], "respostaData": n.get("textoCliente"),
            "resumoIA": n["resumoIA"], "respondidoEm": C.agora_iso(),
            "vigiaAte": _mais_1h() if n["statusFinal"] == "CONCLUIDO" else ""})
        self.registrar_resultado(n)

    def adiamento(self, n):
        self.no = "Expandir adiamento (grupo)"
        alvos = L.expandir_adiamento(n)
        intra = Intranet()
        try:
            self.no = "Login Intranet Adiamento"
            intra.login()
        except Exception:  # noqa: BLE001  (onError=continueRegularOutput)
            log.exception("Login intranet (adiamento)")
        brutos = []
        for p in alvos:
            self.no = "Abrir Formulário Adiamento"
            iso = "-".join(reversed(p["dataSolicitada"].split("/")))
            form = intra.abrir_form_alteracao(iso, p.get("pedidoLider"))
            self.no = "Montar URL Adiamento"
            m = L.montar_url_adiamento(str(form.get("data") or ""), p, intra.base)
            self.no = "Alterar Data na Intranet - Adiamento"
            resp = intra.alterar_data(m["urlAlterar"]) if m.get("urlAlterar") else {"error": "URL vazia", "data": ""}
            brutos.append((m, p, resp))
        self.no = "Confirmar Alteração Intranet"
        conf = L.confirmar_alteracao(n, brutos)
        ok = conf["alteracaoDataConcluida"]
        self.no = "Anti-repetição: pode enviar? (adiamento)"
        if not L.anti_repeticao([conf], _conversa(conf.get("contactId")),
                                lambda x: L.texto_confirmacao_adiamento(x.get("alteracaoDataConcluida"), n.get("dataSolicitada"))):
            return
        self.no = "Enviar Confirmação Adiamento"
        digisac.enviar_mensagem(conf.get("contactId"), L.msg_confirmacao_adiamento(ok, n))
        self.no = "Atualizar Status - Adiamento"
        T.update("AGUARDANDO_ENTREGA", {"id": n["id"]}, {
            "status": "CONCLUIDO" if ok else "AGUARDANDO_DECISAO_RESPONSAVEL", "categoria": "PEDE_ADIAR",
            "respostaData": n.get("textoCliente"),
            "resumoIA": n["resumoIA"] + (f" | Data atualizada para {n['dataSolicitada']}" if ok
                                         else f" | FALHA ao alterar data na intranet: {conf['erroAdiamento']}"),
            "respondidoEm": C.agora_iso()})
        self.registrar_resultado(n, alteracao_ok=ok)
        _registrar_bot(self.linha.get("contactId"), L.texto_confirmacao_adiamento(ok, n.get("dataSolicitada")))

    # ---------------------------------------------------------------- planilha + intranet + consultor
    def registrar_resultado(self, n, alteracao_ok=True):
        self.no = "Classificar Resposta Sheet"
        cls = L.classificar_resposta_sheet(n, alteracao_ok)
        if cls[0]["deveAtualizar"] is True:
            self.no = "Sheet – Buscar Linhas (Resposta)"
            rows = planilha.ler_linhas()
            self.no = "Localizar Linha Sheet"
            loc = L.localizar_linhas_sheet(cls, rows)   # levanta erro se o pedido não está na planilha (igual à v28)
            for c in loc:
                self.no = "Sheet – Resposta Cliente"
                planilha.atualizar("row_number", c["row_number"], {"CONFIRMADO": c["sheetG"], "MOTIVO": c["sheetH"],
                                                                   "DATA ENVIO CONF.": c["sheetI"]})
            self.no = "Montar Observação Contato"
            obs = L.montar_observacoes_contato(n, loc, self.linha.get("tipoMensagem"))
            if obs:
                intra = Intranet()
                try:
                    intra.login()
                except Exception:  # noqa: BLE001
                    log.exception("Login intranet (observação)")
                for o in obs:
                    self.no = "Observação Intranet - Contato Cliente"
                    intra.aviso_entrega(o["pedidoLider"], o["clienteLider"], o["datEntrega"], o["status"], o["observacao"],
                                        o["tipoInformacao"])
                    self.no = "Abrir vigilância (1h)"
                    T.update("AGUARDANDO_ENTREGA", {"id": n["id"]}, {"vigiaAte": _mais_1h()})
            self.no = "Montar registro único"
            r = L.montar_registro_unico(n, cls[0])
            if r:
                T.update("AGUARDANDO_ENTREGA", {"id": r["id"]}, {"dadosPedido": r["dadosPedido"]})
            return
        if n.get("escalar") is True:
            self._email_responsavel(n)
        elif n.get("consultar") is True:
            self.no = "Montar chat com consultor"
            c = L.montar_chat_consultor(n)
            try:
                T.update("AGUARDANDO_ENTREGA", {"id": c["id"]}, {"status": "AGUARDANDO_CONSULTOR", "chatConsultor": c["chatConsultor"]})
            except Exception:  # noqa: BLE001  (onError=continueErrorOutput -> e-mail)
                log.exception("Gravar chat (pergunta ao consultor)")
                self._email_responsavel(n)

    def _email_responsavel(self, n):
        self.no = "E-mail ao responsável"
        grupo = len(n.get("pedidosGrupo") or []) > 1
        assunto = f"Cliente respondeu: {n['categoria']}" + (f" - Pedidos {n['pedidosTexto']}" if grupo else f" - Pedido {n['pedidoLider']}")
        html = (f"<p><b>Pedido:</b> {n.get('pedidosTexto') or n.get('pedidoLider')}<br><b>Cliente:</b> {n.get('cliente')}"
                f"<br><b>Categoria:</b> {n['categoria']}<br><b>Resumo:</b> {n['resumoIA']}</p>"
                f"<p><b>Resposta do cliente:</b><br>{n.get('textoCliente')}</p>")
        email.enviar(EMAIL_AVISOS, assunto, html)

    # ================================================================ decisão sobre falar com o responsável
    def decisao_responsavel(self, linha):
        self.no = "Interpretar Decisão Responsável"
        j = L.interpretar_decisao_responsavel(linha)
        d = j["decisaoResponsavel"]
        if d == "SIM":
            self.no = "Mapear responsável para transferência - Central"
            m = L.mapear_responsavel_transferencia(j, listar_usuarios_todos())
            if m["statusMapeamento"] == "OK" and m["userIdResponsavel"]:
                self.no = "Transferir chamado ao responsável - Central"
                digisac.transferir_chamado(j["contactId"], DEPARTAMENTO_CENTRAL, m["userIdResponsavel"],
                                           f"Pedido {j['pedidoLider']} - {j.get('cliente')}. Cliente pediu contato sobre adiamento/data "
                                           f"alternativa. Data desejada: {j.get('dataSolicitada') or 'não informada'}. Mensagem: {j['textoCliente']}")
                digisac.enviar_mensagem(j["contactId"], "Certo! Encaminhei seu atendimento ao responsável para verificar essa "
                                        "possibilidade. Ele poderá conversar com você sobre uma alternativa de data.")
            else:
                email.enviar(EMAIL_AVISOS, f"Ação manual necessária - pedido {j['pedidoLider']}",
                             f"<p>Não foi possível mapear com segurança o responsável para transferência.</p><p>Pedido: {j['pedidoLider']}"
                             f"<br>Responsável cadastrado: {j.get('responsavel')}<br>Cliente: {j.get('cliente')}<br>Mensagem: {j['textoCliente']}</p>")
                digisac.enviar_mensagem(j["contactId"], "Obrigado por confirmar. Não consegui encaminhar automaticamente para o "
                                        "responsável, mas registrei a solicitação para verificação interna. Não precisa repetir sua mensagem.")
            ok = m["statusMapeamento"] == "OK"
            self.no = "Marcar como transferido - Central"
            T.update("AGUARDANDO_ENTREGA", {"id": j["id"]}, {
                "status": "TRANSFERIDO" if ok else "TRANSFERENCIA_MANUAL", "categoria": "CONTATO_RESPONSAVEL",
                "respostaData": j["textoCliente"],
                "resumoIA": (j.get("resumoIA") or "Cliente aceitou contato do responsável")
                + (" | Transferido ao responsável" if ok else " | Transferência automática falhou; requer ação manual"),
                "respondidoEm": C.agora_iso()})
        elif d == "NAO":
            self.no = "Encerrar sem transferência"
            digisac.enviar_mensagem(j["contactId"], "Tudo bem! Não vou encaminhar o atendimento neste momento. Se mudar de ideia, "
                                    "é só nos avisar por aqui.")
            self.no = "Marcar decisão sem transferência"
            # v28 lia o resumo de 'Normalizar Categoria', nó que não roda neste caminho (dava erro e o status não mudava).
            # Corrigido: mantém o resumo que já estava na linha.
            T.update("AGUARDANDO_ENTREGA", {"id": j["id"]}, {
                "status": "CONCLUIDO", "categoria": "RECUSA_CONTATO_RESPONSAVEL", "respostaData": j["textoCliente"],
                "resumoIA": j.get("resumoIA"), "respondidoEm": C.agora_iso()})
        else:
            self.no = "Resposta ambígua: confirmar decisão"
            digisac.enviar_mensagem(j["contactId"], "Só para confirmar: você quer que eu encaminhe seu atendimento ao responsável "
                                    "para conversar sobre outra data? Responda sim ou não, por favor.")

    # ================================================================ vigilância (já confirmou, chamado aberto)
    def vigilancia(self, linha):
        self.no = "IA - Classificar mensagem (vigilância)"
        r = gemini.gerar_texto(P.montar("IA - Classificar mensagem (vigilância)", linha), 0)
        v = L.interpretar_classificacao_vigilancia(linha, r)
        if v["vigTipo"] == "REGRA":
            self.ia(v)
            return
        if v["vigTipo"] != "DUVIDA":
            self.no = "Prorrogar vigilância (cliente respondeu)"
            T.update("AGUARDANDO_ENTREGA", {"id": v["id"]}, {"vigiaAte": _mais_1h()})
            return
        self.no = "Ler base de conhecimento"
        base = T.get("BASE_CONHECIMENTO")
        texto_base, vazia = L.montar_baseTexto(base)
        j = {**v, "baseVazia": vazia, "baseTexto": texto_base}
        ib = {"usarBase": False}
        if vazia is False:
            self.no = "IA - Buscar resposta na base"
            ib = L.interpretar_resposta_base(gemini.gerar_texto(P.montar("IA - Buscar resposta na base", j), 0), base)
        j = {**j, **ib}
        if ib["usarBase"] is True:
            self.no = "Anti-repetição: pode enviar? (resposta da base)"
            if not L.anti_repeticao([j], _conversa(j.get("contactId")), lambda x: x.get("respostaBase")):
                return
            self.no = "Enviar resposta da base ao cliente"
            digisac.enviar_mensagem(j["contactId"], j["respostaBase"])
            self.no = "Registrar resposta automática"
            ra = L.registrar_resposta_automatica(j)
            T.update("AGUARDANDO_ENTREGA", {"id": ra["id"]}, {"chatConsultor": ra["chatConsultor"],
                                                               "respondidoEm": C.agora_iso(), "vigiaAte": _mais_1h()})
            self.no = "Contar uso da base"
            T.update("BASE_CONHECIMENTO", {"id": ra["kbId"]}, {"usos": int(float(ra["kbUsos"] or 0)) + 1,
                                                               "ultimoUso": C.agora_iso()})
            _registrar_bot(self.linha.get("contactId"), j["respostaBase"])
        else:
            self.no = "Montar dúvida ao consultor (vigilância)"
            dv = L.montar_duvida_vigilancia(v)
            T.update("AGUARDANDO_ENTREGA", {"id": dv["id"]}, {"status": "AGUARDANDO_CONSULTOR", "chatConsultor": dv["chatConsultor"]})


def processar(entrada: dict, esperar: bool = True):
    r = Resposta(entrada)
    try:
        r.executar(esperar)
    except Exception as exc:  # noqa: BLE001
        log.exception("Resposta do cliente falhou no nó %s", r.no)
        from ..registro import alertar_erro
        alertar_erro(r.no, exc, {"body": entrada.get("body")})


@gatilho("digisac-resposta")
def digisac_resposta(entrada, req):
    """Chamado em segundo plano pela rota (ASSINCRONOS): o DigiSac já recebeu 200."""
    processar(entrada)
    return {"ok": True}, 200
