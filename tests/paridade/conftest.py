"""Paridade: roda o JavaScript ORIGINAL do nó da v28 (Node) e compara com a tradução em Python.

Precisa de Node instalado e do JSON da v28 em tests/paridade/v28.json (ou V28_JSON=caminho).
Sem Node, estes testes são pulados.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
V28 = os.getenv("V28_JSON", str(AQUI / "v28.json"))
FIX = AQUI / "fixtures"
NODE = shutil.which("node")


def _normal(x):
    """Igualdade 'à moda JSON': 1.0 == 1, tuplas == listas."""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, dict):
        return {k: _normal(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_normal(v) for v in x]
    return x


def rodar_js(no: str, entrada: list, nodes: dict | None = None, agora: str | None = None, prev: str = ""):
    if not NODE or not Path(V28).exists():
        pytest.skip("Node ou v28.json indisponível")
    req = {"wf": V28, "no": no, "input": entrada, "nodes": nodes or {}, "now": agora, "prevNode": prev}
    env = {**os.environ, "TZ": "America/Sao_Paulo"}
    r = subprocess.run([NODE, str(AQUI / "run_node.js")], input=json.dumps(req, default=str),
                       capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    if "erro" in out:
        raise RuntimeError(f"JS do nó {no!r}: {out['erro']}")
    return out["ok"]


def igual(js, py, ignorar=()):
    js, py = _normal(json.loads(json.dumps(js, default=str))), _normal(json.loads(json.dumps(py, default=str)))
    if ignorar:
        def tira(x):
            if isinstance(x, dict):
                return {k: tira(v) for k, v in x.items() if k not in ignorar}
            if isinstance(x, list):
                return [tira(v) for v in x]
            return x
        js, py = tira(js), tira(py)
    if js != py:
        import difflib
        a = json.dumps(js, indent=1, ensure_ascii=False, sort_keys=True).splitlines()
        b = json.dumps(py, indent=1, ensure_ascii=False, sort_keys=True).splitlines()
        diff = "\n".join(list(difflib.unified_diff(a, b, "js", "py", lineterm=""))[:80])
        raise AssertionError("Saídas diferentes:\n" + diff)
    return True


def fixture(nome: str) -> str:
    return (FIX / nome).read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def js():
    return rodar_js
