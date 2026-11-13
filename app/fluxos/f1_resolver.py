"""Gatilho 'Central - Lider - Resolver Pendência' (webhook central-lider-resolver).

O painel manda o destino/telefone/referência digitados (ou 'tratar individualmente').
Destino resolvido: volta para o Fluxo 1 a partir do 'Merge Origem' (coordenadas, rota, contatos, mensagem).
"""
import logging
import re
import threading
import traceback

from .. import comum as C
from .. import tabelas as T
from ..integracoes import email
from . import gatilho
from . import f1_mensagens as M
from .f1_disparo import Disparo, registrar_erro_disparo, _lock_disparo
from .f1_extracao import DEPOSITOS, registros_emails

log = logging.getLogger("central")
UFS_VALIDAS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR",
               "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
EMAIL_INDIVIDUAL = "mateus.oliveira@lider.design"  # v28: toEmail fixo no nó "Send an Email Individual"


def aplicar_destino_manual(body: dict, linha: dict) -> dict:
    """Nó 'Aplicar Destino Manual (Front)'."""
    pedido = C.loads(linha.get("dadosPedido"), {}) or {}
    pedido_lider = str(linha.get("pedidoLider") or body.get("pedidoLider") or pedido.get("pedidoLider")
                       or pedido.get("pedido") or "").strip()
    id_linha = linha.get("id")
    if body.get("acao") == "individual":
        return {**pedido, "id": id_linha, "pedidoLider": pedido_lider, "tratarIndividual": True,
                "motivoIndividual": str(body.get("observacao") or "").strip() or None,
                "rota": {**(pedido.get("rota") or {}), "origemIdentificada": False, "status": "PENDENTE",
                         "motivoOrigem": "TRATAR_INDIVIDUALMENTE"}}
    tel_manual = str(body.get("telefone") or "").strip()
    tel_atual = pedido.get("telefone")
    tels = list(pedido.get("telefones")) if isinstance(pedido.get("telefones"), list) else []
    if tel_manual:
        nt = C.normalizar_celular(tel_manual) or re.sub(r"\D", "", tel_manual)
        tel_atual = nt
        if nt not in tels:
            tels.insert(0, nt)
    tel_final = C.normalizar_celular(tel_atual)
    cidade = C.norm(body.get("cidade")) or C.norm(pedido.get("cidadeEntrega"))
    uf = C.norm(body.get("uf")) or C.norm(pedido.get("ufEntrega"))
    ref_manual = C.norm(body.get("referencia"))
    if not cidade or uf not in UFS_VALIDAS:
        raise ValueError(f"Destino inválido para o pedido {pedido_lider}")

    def origem_por_ref(ref):
        if re.search(r"SILVIANO|S\.BRANDAO|PONTEIO|CATALAO|SION", ref):
            return {"cidade": "BELO HORIZONTE", "uf": "MG", "nome": "BELO HORIZONTE"}
        m = re.search(r"\(([^)]+)\)", ref)
        c = re.sub(r"^M\.LEME$", "MATEUS LEME", m.group(1).strip() if m else ref)
        if re.search(r"CORP|SAO PAULO|CENTRAL", c):
            raise ValueError(f'Pedido {pedido_lider}: a referência "{ref}" não é uma cidade de origem em MG')
        return {"cidade": c, "uf": "MG", "nome": c}

    if uf != "MG" and uf in DEPOSITOS:
        origem, motivo = DEPOSITOS[uf], "DESTINO_MANUAL_DEPOSITO_REGIONAL"
    elif uf == "MG":
        ref = ref_manual or C.norm(pedido.get("referencia"))
        if not ref:
            raise ValueError(f"Pedido {pedido_lider}: informe a referência de origem (MG)")
        origem, motivo = origem_por_ref(ref), "DESTINO_MANUAL_REFERENCIA_MG"
    else:
        if not ref_manual:
            raise ValueError(f"Pedido {pedido_lider}: UF {uf} sem depósito regional — informe a referência de origem")
        origem, motivo = origem_por_ref(ref_manual), "DESTINO_MANUAL_UF_SEM_DEPOSITO"
    return {**pedido, "id": id_linha, "pedidoLider": pedido_lider, "tratarIndividual": False,
            "telefone": tel_final or tel_atual, "phone": tel_final, "telefones": tels,
            "cidadeEntrega": cidade, "ufEntrega": uf,
            "referencia": ref_manual or pedido.get("referencia") or None,
            "rota": {**(pedido.get("rota") or {}), "origem": origem, "origemIdentificada": True,
                     "telefoneIdentificado": bool(tel_final), "semPendencia": bool(tel_final), "apto": True,
                     "origemManual": True, "status": "OK" if tel_final else "PENDENTE", "motivoOrigem": motivo,
                     "motivoPendencia": None if tel_final else "TELEFONE_FIXO_OU_INVALIDO",
                     "destino": {"cidade": cidade, "uf": uf}}}


def montar_emails_individual(itens: list[dict], html_emails: str) -> list[dict]:
    """Nó 'Montar E-mail Individual' (MODO_TESTE = false na v28)."""
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

    th = lambda t: f'<th style="border:1px solid #999;padding:4px 8px;background:#f2f2f2;font-size:12px;">{t}</th>'  # noqa: E731
    td = lambda t: f'<td style="border:1px solid #999;padding:4px 8px;font-size:12px;">{C.esc3(t)}</td>'  # noqa: E731
    saida = []
    for resp, lista in grupos.items():
        at = M.buscar_atendente(resp, regs)
        nome_fmt = C.capitalizar(resp.split()[0]) if resp.split() else resp
        linhas = "".join(f"""<tr>
    {td(num_pedido(p))}
    {td(p.get('Cliente') or p.get('clienteLider') or '-')}
    {td((p.get('cidadeEntrega') or '-') + '/' + (p.get('ufEntrega') or '-'))}
    {td(p.get('referencia') or '-')}
    {td(p.get('motivoIndividual') or ('Sem dados na intranet (possível cancelamento)' if not p.get('pedidoLider') else ''))}
  </tr>""" for p in lista)
        html = f"""<div style="font-family:Arial,sans-serif;font-size:14px;">

<p>{C.saudacao()}, {C.esc3(nome_fmt)}. Tudo bem?</p>
<p>Os pedidos abaixo ficaram sem destino identificado no fluxo automático de aviso de entrega e precisam ser tratados individualmente:</p>
<table style="border-collapse:collapse;font-family:Arial,sans-serif;">
<tr>{''.join(th(t) for t in ['Pedido', 'Cliente', 'Destino lido', 'Vendedor/Praça', 'Observação'])}</tr>
{linhas}
</table>
<p>Obrigado!</p>
</div>"""
        para = at["email"] or M.EMAIL_TESTE
        prefixo = "" if at["email"] else "[SEM E-MAIL DO ATENDENTE] "
        nums = ", ".join(str(p.get("pedidoPlanilha") or p.get("pedidoLider")) for p in lista)
        saida.append({"para": para, "html": html, "atendente": resp, "emailAtendente": at["email"], "status": at["status"],
                      "assunto": f"{prefixo}Pedidos para tratar individualmente ({len(lista)}): {nums}"})
    return saida


def rodar_resolver(body: dict):
    _lock_disparo.acquire()
    d = Disparo(None, evento_inicial_gravado=True)
    try:
        d.no = "Buscar Pendência"
        linhas = T.get("AGUARDANDO_ENTREGA", {"pedidoLider": body.get("pedidoLider"), "status": "PENDENTE_DESTINO"})
        if not linhas:
            log.info("Resolver pendência: pedido %s não está em PENDENTE_DESTINO", body.get("pedidoLider"))
            return
        linha = linhas[0]
        d.no = "Aplicar Destino Manual (Front)"
        item = aplicar_destino_manual(body, linha)
        d.no = "Login Intranet (Retomada)"
        d.intranet.login()
        d.no = "Marcar Pendência Resolvida"
        T.update("AGUARDANDO_ENTREGA", {"id": linha["id"]},
                 {"status": "INDIVIDUAL" if item["tratarIndividual"] else "RESOLVIDO"})
        if item["tratarIndividual"] is True:
            d.no = "Montar E-mail Individual"
            for e in montar_emails_individual([item], d._emails()):
                d.no = "Send an Email Individual"
                email.enviar(EMAIL_INDIVIDUAL, e["assunto"], e["html"])
            return
        # Merge Origem -> resto do Fluxo 1
        calculados = d.calcular_rotas([item])
        if calculados:
            d.reincidencia_e_contatos(calculados)
    except Exception as exc:  # noqa: BLE001
        log.error("Resolver pendência falhou no nó %s: %s\n%s", d.no, exc, traceback.format_exc())
        registrar_erro_disparo(d.no, exc)
    finally:
        _lock_disparo.release()


@gatilho("central-lider-resolver")
def resolver(entrada, req):
    """Webhook sem 'Respond to Webhook' na v28: responde na hora e processa em segundo plano."""
    body = entrada.get("body") if isinstance(entrada.get("body"), dict) else {}
    threading.Thread(target=rodar_resolver, args=(body,), name="resolver", daemon=True).start()
    return {"message": "Workflow was started"}, 200
