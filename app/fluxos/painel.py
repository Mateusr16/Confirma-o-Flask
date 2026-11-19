"""Gatilhos de leitura do painel: Status do disparo e API Pendências (v28)."""
import time

from .. import tabelas as T
from . import gatilho

STATUS_CONHECIDOS = [
    "EM_PROCESSAMENTO", "PENDENTE_DESTINO", "RESOLVIDO", "INDIVIDUAL", "PENDENTE_REVISAO",
    "BLOQUEADO", "CANCELADO", "AGUARDANDO", "DATA_ENVIADA", "AGUARDANDO_DECISAO_RESPONSAVEL",
    "AGUARDANDO_CONSULTOR", "CONCLUIDO", "ESCALADO", "TRANSFERIDO", "TRANSFERENCIA_MANUAL",
    "AGUARDANDO_CHAMADO_LIVRE", "PENDENTE_RESPOSTA_TARDIA", "SEM_RETORNO_CLIENTE", "AGRUPADO",
    "OUTLET",
]

# Reserva: só conclui por silêncio se o evento de fim nunca chegar (ex.: servidor caiu no meio).
INATIVIDADE_RESERVA_MS = 30 * 60 * 1000


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@gatilho("status-fluxo-lider")
def status_disparo(entrada, req):
    """Nós: Ler eventos do disparo → Montar estado do disparo → Responder status."""
    disparo_id = (entrada.get("query") or {}).get("disparoId")
    rows = [r for r in T.get("FLUXO_STATUS") if r.get("ts")]
    agora = int(time.time() * 1000)
    eventos = sorted((r for r in rows if r["disparoId"] == disparo_id and r["tipo"] != "erro"),
                     key=lambda r: r["ts"])
    if not disparo_id or not eventos:
        return {"encontrado": False, "agora": agora}, 200

    inicio = eventos[0]["ts"]
    erros = sorted((r for r in rows if r["tipo"] == "erro" and r["ts"] >= inicio), key=lambda r: r["ts"])
    erro_row = erros[0] if erros else None
    # Evento "fim" é gravado pelo disparo quando ele termina de verdade (a tela escreve a linha "Fluxo concluído").
    fim = next((e for e in eventos if e["tipo"] == "fim"), None)
    passos = [e for e in eventos if e["tipo"] != "fim"] or eventos
    ultimo = passos[-1]
    pct = max(_num(e["pct"]) for e in passos)
    logs = [{"t": e["ts"], "msg": e["msg"], "tipo": e["tipo"]} for e in passos]
    status, erro, sem_atividade = "executando", None, False
    atualizado = ultimo["ts"]
    # Divergência da v16/v28: antes concluía por inatividade (60 s depois de 96 %, senão 7 min).
    if erro_row:
        status = "erro"
        erro = {"mensagem": erro_row["msg"], "no": erro_row["no"], "t": erro_row["ts"]}
        logs.append({"t": erro_row["ts"], "msg": f'Erro na etapa "{erro_row["no"]}"', "tipo": "erro"})
    elif fim:
        status, pct, atualizado = "concluido", 100, fim["ts"]
    elif agora - ultimo["ts"] > INATIVIDADE_RESERVA_MS:
        status, pct, sem_atividade = "concluido", 100, True
    if pct == int(pct):
        pct = int(pct)
    return {"encontrado": True, "agora": agora, "status": status, "pct": pct,
            "etapa": ultimo["msg"], "atualizadoEm": atualizado, "logs": logs,
            "erro": erro, "semAtividade": sem_atividade}, 200


@gatilho("central-lider-pendencias")
def api_pendencias(entrada, req):
    """Nós: Pendente_destino → Filtro status → Resposta Pendentes (todos os itens)."""
    saida = [
        {**r, "criadoEm": r.get("criadoEm") or r.get("createdAt"),
         "statusConhecido": r["status"] in STATUS_CONHECIDOS}
        for r in T.get("AGUARDANDO_ENTREGA")
        if r.get("pedidoLider") and r.get("status")
    ]
    return (saida or [{}]), 200
