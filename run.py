"""Inicia o servidor da Central Líder.

    python run.py            -> servidor de produção (waitress) + agendador
    python run.py --debug    -> servidor de desenvolvimento do Flask
"""
import logging
import sys

from app import create_app
from app import agendador
from app.config import Config

app = create_app()

def porta_ocupada(host: str, porta: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, porta)) == 0


if __name__ == "__main__":
    log = logging.getLogger("central")
    if porta_ocupada(Config.HOST, Config.PORT):
        log.error("Já existe um servidor rodando em %s:%s. Feche-o antes (Ctrl+C no terminal dele, "
                  "ou no PowerShell: Get-Process python | Stop-Process) e rode de novo.", Config.HOST, Config.PORT)
        sys.exit(1)
    log.info("Central Líder | http://%s:%s | MODO_TESTE=%s | AGENDADOR=%s",
             Config.HOST, Config.PORT, Config.MODO_TESTE, Config.AGENDADOR_ATIVO)
    from app.fluxos.f2_resposta import limpar_mensagens_nao_atendidas
    apagadas = limpar_mensagens_nao_atendidas()
    if apagadas:
        log.info("Limpeza: %s mensagens de contatos que o sistema não atende foram apagadas", apagadas)
    agendador.iniciar()
    if "--debug" in sys.argv:
        app.run(host=Config.HOST, port=Config.PORT, debug=True, use_reloader=False)
    else:
        from waitress import serve
        # mostra no terminal a linha "Serving on http://127.0.0.1:6050" do waitress
        wlog = logging.getLogger("waitress")
        wlog.setLevel(logging.INFO)
        for h in log.handlers:
            wlog.addHandler(h)
        log.info("Iniciando servidor... aguarde a linha 'Serving on' e então abra "
                 "http://%s:%s/webhook/central-lider", Config.HOST, Config.PORT)
        serve(app, host=Config.HOST, port=Config.PORT, threads=8)
