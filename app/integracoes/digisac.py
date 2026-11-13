"""DigiSac — equivalentes das operações do nó n8n-nodes-digisac usadas na v28.

  e065 buscar contato     GET  /api/v1/contacts?where[data.number][$iLike]=...&where[serviceId]=...
  e075 criar contato      POST /api/v1/contacts
  e154 enviar mensagem    POST /api/v1/messages {text, type, contactId}
  e215 enviar template    POST /api/v1/messages {type:'hsm', number, serviceId, hsmId}
  e046 transferir chamado POST /api/v1/contacts/{contactId}/ticket/transfer
  e049 fechar chamado     POST /api/v1/contacts/{contactId}/ticket/close
  + chamadas HTTP diretas: GET /users, GET /tickets, GET/POST /messages

Tudo que altera algo passa por saida.externo (MODO_TESTE).
Leituras (buscar contato, tickets, usuários, mensagens) são feitas de verdade mesmo em teste.
"""
import logging
import time
import uuid

import requests

from ..config import Config
from .. import saida

log = logging.getLogger("central")

SERVICES = ["1211d47b-8ab8-47e8-8055-6b2307a8f466", "6518c8e7-72a4-4796-bb09-2ebd252ef2d6"]
SERVICE_CRIACAO = "6518c8e7-72a4-4796-bb09-2ebd252ef2d6"
HSM_POR_SERVICE = {  # nó "POST Enviar template com botao"
    "1211d47b-8ab8-47e8-8055-6b2307a8f466": "d4496b94-dc44-4400-a227-3ae1e78fc0e1",
    "6518c8e7-72a4-4796-bb09-2ebd252ef2d6": "226eff53-3421-423d-9a44-eea6d34f7cb7",
}


class ErroDigisac(Exception):
    pass


def _req(metodo: str, caminho: str, tentativas: int = 3, **kw):
    if not Config.DIGISAC_URL or not Config.DIGISAC_TOKEN:
        raise ErroDigisac("DIGISAC_URL / DIGISAC_TOKEN não configurados no .env")
    url = f"{Config.DIGISAC_URL}{caminho}"
    headers = {"Authorization": f"Bearer {Config.DIGISAC_TOKEN}", "Accept": "application/json"}
    ultimo = None
    for _ in range(tentativas):
        try:
            r = requests.request(metodo, url, headers=headers, timeout=60, **kw)
            if r.status_code >= 400:
                raise ErroDigisac(f"{metodo} {caminho} -> HTTP {r.status_code}: {r.text[:500]}")
            return r.json() if r.content else {}
        except (requests.RequestException, ErroDigisac) as exc:
            ultimo = exc
            time.sleep(1)
    raise ErroDigisac(str(ultimo))


def _seguro(fn, *a, **kw) -> dict:
    """onError=continueRegularOutput: devolve {'error': ...} em vez de levantar."""
    try:
        r = fn(*a, **kw)
        return r if isinstance(r, dict) else {"data": r}
    except Exception as exc:  # noqa: BLE001
        return {"error": {"message": str(exc)}}


# ------------------------------------------------------------ leituras
def buscar_contatos(numero_like: str, service_id: str) -> dict:
    """e065. numero_like já vem no formato do fluxo ('%12345678')."""
    return _seguro(_req, "GET", "/api/v1/contacts", params={
        "where[data.number][$iLike]": numero_like, "where[serviceId]": service_id})


def tickets_abertos(contact_id: str) -> dict:
    return _seguro(_req, "GET", "/api/v1/tickets", params={
        "where[contactId]": contact_id, "where[isOpen]": "true", "perPage": "20"})


def listar_usuarios() -> dict:
    return _seguro(_req, "GET", "/api/v1/users", params={"perPage": "100", "page": "1"})


def mensagens_do_contato(contact_id: str, per_page: int = 100) -> dict:
    return _seguro(_req, "GET", "/api/v1/messages", params={
        "where[contactId]": contact_id, "perPage": str(per_page)})


# ------------------------------------------------------------ escritas
def _falso(prefixo: str, extra: dict | None = None) -> dict:
    return {"id": f"{prefixo}-{uuid.uuid4()}", "teste": True, **(extra or {})}


def criar_contato(internal_name: str, numero: str, service_id: str = SERVICE_CRIACAO) -> dict:
    corpo = {"internalName": internal_name, "number": numero, "serviceId": service_id,
             "defaultDepartmentId": None, "tagIds": [], "customFields": []}
    return saida.externo("digisac", "criar_contato", corpo,
                         lambda: _seguro(_req, "POST", "/api/v1/contacts", json=corpo),
                         retorno_teste=_falso("teste-contato", {"serviceId": service_id}))


def enviar_mensagem(contact_id: str, texto: str) -> dict:
    corpo = {"text": texto, "type": "chat", "contactId": contact_id}
    return saida.externo("digisac", "enviar_mensagem", corpo,
                         lambda: _seguro(_req, "POST", "/api/v1/messages", json=corpo),
                         retorno_teste=_falso("teste-msg"))


def enviar_template(numero: str, service_id: str) -> dict:
    corpo = {"type": "hsm", "number": numero, "serviceId": service_id,
             "hsmId": HSM_POR_SERVICE.get(service_id)}
    return saida.externo("digisac", "enviar_template", corpo,
                         lambda: _seguro(_req, "POST", "/api/v1/messages", json=corpo),
                         retorno_teste=_falso("teste-hsm"))


def enviar_arquivo(contact_id: str, arquivo: dict) -> dict:
    """Nó 'Enviar vídeo Digisac' (file = {base64, mimetype, name})."""
    corpo = {"type": "chat", "contactId": contact_id, "file": arquivo}
    resumo = {**corpo, "file": {k: (v if k != "base64" else f"<{len(v)} chars>") for k, v in arquivo.items()}}
    return saida.externo("digisac", "enviar_arquivo", resumo,
                         lambda: _seguro(_req, "POST", "/api/v1/messages", json=corpo),
                         retorno_teste=_falso("teste-arquivo"))


def transferir_chamado(contact_id: str, department_id: str, user_id: str, comentario: str = "") -> dict:
    corpo = {"departmentId": department_id, "userId": user_id, "comments": comentario}
    return saida.externo("digisac", "transferir_chamado", {"contactId": contact_id, **corpo},
                         lambda: _seguro(_req, "POST", f"/api/v1/contacts/{contact_id}/ticket/transfer", json=corpo),
                         retorno_teste={"ok": True, "teste": True})


def fechar_chamado(contact_id: str) -> dict:
    return saida.externo("digisac", "fechar_chamado", {"contactId": contact_id},
                         lambda: _seguro(_req, "POST", f"/api/v1/contacts/{contact_id}/ticket/close", json={}),
                         retorno_teste={"ok": True, "teste": True})
