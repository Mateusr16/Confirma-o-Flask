"""Gatilhos já migrados que não dependem de regra de negócio."""
from pathlib import Path

from flask import send_file

from . import gatilho

STATIC = Path(__file__).resolve().parent.parent / "static"


@gatilho("central-lider")
def frontend(dados, req):
    """Equivale ao webhook 'Central - Lider - Frontend': entrega o painel."""
    pagina = STATIC / "index.html"
    if not pagina.exists():
        return {"erro": "index.html ainda não foi copiado para app/static"}, 404
    return send_file(pagina, mimetype="text/html"), 200
