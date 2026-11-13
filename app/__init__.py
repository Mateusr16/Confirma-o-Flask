from flask import Flask

from . import db
from .registro import configurar_log


def create_app() -> Flask:
    log = configurar_log()
    app = Flask(__name__, static_folder="static")
    app.json.ensure_ascii = False

    aplicadas = db.migrar()
    if aplicadas:
        log.info("Migrações aplicadas: %s", aplicadas)

    from .rotas.webhooks import bp
    app.register_blueprint(bp)

    @app.errorhandler(Exception)
    def _erro(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        log.exception("Erro não tratado na requisição")
        return {"erro": "Falha interna", "detalhe": f"{type(exc).__name__}: {exc}"}, 500
    return app
