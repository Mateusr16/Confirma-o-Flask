"""Gemini (equivale aos nós 'Basic LLM Chain' + 'Google Gemini Chat Model' do n8n).

gerar_texto  -> chainLlm sem parser: devolve {"text": "..."}
gerar_json   -> chainLlm com 'Structured Output Parser': devolve {"output": {...}}
Em erro (onError=continueRegularOutput) devolve {"error": "..."} e o fluxo segue.
"""
import json
import logging
import re
import time

import requests

from ..config import Config

log = logging.getLogger("central")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


def _chamar(prompt: str, temperatura: float) -> str:
    modelo = Config.GEMINI_MODELO.replace("models/", "")
    corpo = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
             "generationConfig": {"temperature": temperatura}}
    ultimo = None
    for _ in range(3):   # retryOnFail
        try:
            r = requests.post(URL.format(modelo=modelo), params={"key": Config.GEMINI_API_KEY}, json=corpo, timeout=90)
            if r.status_code >= 400:
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
            dados = r.json()
            partes = ((dados.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in partes)
        except Exception as exc:  # noqa: BLE001
            ultimo = exc
            time.sleep(1)
    raise RuntimeError(str(ultimo))


def gerar_texto(prompt: str, temperatura: float = 0) -> dict:
    try:
        return {"text": _chamar(prompt, temperatura)}
    except Exception as exc:  # noqa: BLE001
        log.error("Gemini falhou: %s", exc)
        return {"error": str(exc)}


def _schema_de_exemplo(exemplo: dict) -> dict:
    tipo = lambda v: "boolean" if isinstance(v, bool) else "number" if isinstance(v, (int, float)) else "string"  # noqa: E731
    return {"type": "object", "properties": {k: {"type": tipo(v)} for k, v in exemplo.items()},
            "required": list(exemplo), "additionalProperties": False}


INSTRUCOES = (
    'You must format your output as a JSON value that adheres to a given "JSON Schema" instance.\n\n'
    '"JSON Schema" is a declarative language that allows you to annotate and validate JSON documents.\n\n'
    'Your output will be parsed and type-checked according to the provided schema instance, so make sure all '
    'fields in your output match the schema exactly and there are no trailing commas!\n\n'
    "Here is the JSON Schema instance your output must adhere to. Include the enclosing markdown codeblock:\n"
    "```json\n{schema}\n```\n")


def extrair_json(texto: str):
    t = re.sub(r"```json|```", "", str(texto or "")).strip()
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            return json.loads(m.group(0))
        raise


def gerar_json(prompt: str, exemplo_saida: str, temperatura: float = 0) -> dict:
    """Structured Output Parser: o resultado vem em {'output': {...}}."""
    schema = {"type": "object", "properties": {"output": _schema_de_exemplo(json.loads(exemplo_saida))},
              "required": ["output"], "additionalProperties": False}
    completo = f"{prompt}\n\n{INSTRUCOES.format(schema=json.dumps(schema, ensure_ascii=False))}"
    try:
        bruto = _chamar(completo, temperatura)
        obj = extrair_json(bruto)
        if isinstance(obj, dict) and isinstance(obj.get("output"), dict):
            obj = obj["output"]
        if not isinstance(obj, dict):
            raise ValueError("saída não é um objeto JSON")
        return {"output": obj}
    except Exception as exc:  # noqa: BLE001
        log.error("Gemini (saída estruturada) falhou: %s", exc)
        return {"error": str(exc)}
