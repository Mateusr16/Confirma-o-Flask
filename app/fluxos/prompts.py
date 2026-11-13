"""Prompts da IA, com o texto EXATO da v28 (prompts_v28.json) e as expressões {{ }} resolvidas em Python."""
import json
import re
from pathlib import Path

_TEXTOS = json.loads((Path(__file__).parent / "prompts_v28.json").read_text(encoding="utf-8"))
EXEMPLO_SAIDA_CATEGORIA = _TEXTOS["__exemplo_saida_Basic LLM Chain"]


def _s(v) -> str:
    return "" if v is None else (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))


def _ultimo_cliente(j):
    try:
        chat = json.loads(j.get("chatConsultor") or "[]")
        cl = [m for m in chat if m.get("role") == "cliente"]
        return cl[-1].get("texto", "") if cl else ""
    except (ValueError, AttributeError):
        return ""


EXPRESSOES = {
    "$json.ctxHistorico": lambda j: j.get("ctxHistorico"),
    "$json.ctxHoje": lambda j: j.get("ctxHoje"),
    "$json.ctxLimite": lambda j: j.get("ctxLimite"),
    "$json.ctxPrevista": lambda j: j.get("ctxPrevista"),
    "$json.ctxRegistro": lambda j: j.get("ctxRegistro"),
    "$json.textoCliente": lambda j: j.get("textoCliente"),
    "String($json.mensagem || '').slice(0, 1500)": lambda j: str(j.get("mensagem") or "")[:1500],
    "String($json.mensagem || '').slice(0, 800)": lambda j: str(j.get("mensagem") or "")[:800],
    "String($json.mensagem || '').slice(0, 600)": lambda j: str(j.get("mensagem") or "")[:600],
    "$json.respostaData": lambda j: j.get("respostaData"),
    "String($json.historicoConversa || '(sem histórico)').slice(-3000)":
        lambda j: str(j.get("historicoConversa") or "(sem histórico)")[-3000:],
    "$json.baseTexto": lambda j: j.get("baseTexto"),
    "$json.assuntoFora": lambda j: j.get("assuntoFora"),
    "$json.baseTexto || '(vazia)'": lambda j: j.get("baseTexto") or "(vazia)",
    "$json.orientacao": lambda j: j.get("orientacao"),
    "$json.perguntaCliente": lambda j: j.get("perguntaCliente"),
    "$json.respostaEnviada": lambda j: j.get("respostaEnviada"),
    "$json.textoConsultor": lambda j: j.get("textoConsultor"),
    "$json.chatConsultor ? JSON.parse($json.chatConsultor).filter(m => m.role === 'cliente').slice(-1)[0]?.texto : ''":
        lambda j: _ultimo_cliente(j) if j.get("chatConsultor") else "",
}


def montar(nome_no: str, j: dict) -> str:
    texto = _TEXTOS[nome_no]

    def troca(m):
        expr = m.group(1).strip()
        if expr not in EXPRESSOES:
            raise KeyError(f"Expressão não mapeada no prompt '{nome_no}': {expr}")
        return _s(EXPRESSOES[expr](j))
    return re.sub(r"\{\{(.*?)\}\}", troca, texto)
