"""Os 6 agendamentos da v28 (Schedule Trigger), com os mesmos horários.

Fuso: America/Sao_Paulo. Cada job roda uma instância por vez (como o n8n,
uma execução nova não começa enquanto a anterior do mesmo job está rodando).
"""
import logging

from . import db
from .config import Config
from .fluxos import JOBS
from .registro import alertar_erro

log = logging.getLogger("central")

# nome do job -> (gatilho APScheduler, argumentos)  — copiado da v28
AGENDA = {
    "varredura_vigilancia":   [("cron", dict(minute="*/10"))],
    "chamados_ocupados":      [("interval", dict(minutes=30))],
    "lembrete_13h":           [("cron", dict(hour=13, minute=0, day_of_week="mon-fri"))],
    "reenvio_template":       [("cron", dict(hour=13, minute=20, day_of_week="mon-fri"))],
    "varredura_tardia":       [("cron", dict(hour=8, minute=5, day_of_week="mon-fri"))],
    "encerramento_pendencias": [("cron", dict(hour=16, minute=20, day_of_week="mon-thu")),
                                ("cron", dict(hour=15, minute=20, day_of_week="fri"))],
}


def _executar(nome: str):
    fn = JOBS.get(nome)
    inicio = db.agora_iso()
    if fn is None:
        db.registrar_execucao(f"agenda:{nome}", "nao_migrado", None, inicio)
        return
    try:
        fn()
        db.registrar_execucao(f"agenda:{nome}", "ok", None, inicio)
    except Exception as exc:  # noqa: BLE001
        db.registrar_execucao(f"agenda:{nome}", "erro", None, inicio, erro=repr(exc))
        alertar_erro(f"agendamento {nome}", exc)


def iniciar():
    if not Config.AGENDADOR_ATIVO:
        log.info("Agendador DESLIGADO (AGENDADOR_ATIVO=false)")
        return None
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = BackgroundScheduler(timezone=Config.TZ_LOCAL,
                                job_defaults={"coalesce": True, "max_instances": 1,
                                              "misfire_grace_time": 300})
    for nome, regras in AGENDA.items():
        for i, (tipo, args) in enumerate(regras):
            sched.add_job(_executar, tipo, args=[nome], id=f"{nome}#{i}", name=nome, **args)
    sched.start()
    for job in sched.get_jobs():
        log.info("Agendado %-28s próxima: %s", job.id, job.next_run_time)
    # Equivale ao gatilho "Varredura tardia - n8n iniciou" (espera 60 s e roda em segundo plano)
    if "ao_iniciar" in JOBS:
        import threading
        threading.Thread(target=_executar, args=("ao_iniciar",), name="ao-iniciar", daemon=True).start()
    return sched
