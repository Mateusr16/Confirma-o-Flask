"""Simula uma mensagem do cliente chegando pelo DigiSac (sem precisar apontar o DigiSac para o Flask).

    python simular_resposta.py 97680 "Sim"
    python simular_resposta.py 97680 "pode ser, obrigado"
    python simular_resposta.py 97680 "quero adiar para março"

O servidor precisa estar rodando. A resposta é processada em ~60 s (mesma espera do n8n para juntar
mensagens seguidas). Com MODO_TESTE=true nada é enviado ao cliente: veja o resultado no painel e em
envios_simulados (python simular_resposta.py --ultimos).
"""
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.config import Config  # noqa: E402


def contato_do_pedido(pedido: str) -> str:
    con = sqlite3.connect(f"file:{Config.SQLITE_PATH}?mode=ro", uri=True)
    r = con.execute("SELECT contactId, status FROM AGUARDANDO_ENTREGA WHERE pedidoLider = ?", (pedido,)).fetchone()
    con.close()
    if not r or not r[0]:
        sys.exit(f"Pedido {pedido} não tem contato DigiSac no banco (status: {r[1] if r else 'não encontrado'}).")
    print(f"Pedido {pedido}: status atual {r[1]}, contato {r[0]}")
    return r[0]


def ultimos(n=10):
    con = sqlite3.connect(f"file:{Config.SQLITE_PATH}?mode=ro", uri=True)
    for criado, destino, acao, payload in con.execute(
            "SELECT criado_em, destino, acao, payload FROM envios_simulados ORDER BY id DESC LIMIT ?", (n,)):
        p = json.loads(payload or "{}")
        resumo = p.get("text") or p.get("assunto") or p.get("observacao") or json.dumps(p, ensure_ascii=False)[:150]
        print(f"{criado}  {destino}/{acao}\n    {str(resumo)[:300]}\n")
    con.close()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--ultimos":
        ultimos(int(sys.argv[2]) if len(sys.argv) > 2 else 10)
        sys.exit()
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    pedido, texto = sys.argv[1], " ".join(sys.argv[2:])
    corpo = {"data": {"contactId": contato_do_pedido(pedido), "id": f"simulado-{int(time.time() * 1000)}",
                      "isFromMe": False, "type": "chat", "data": {"text": texto}}}
    req = urllib.request.Request(f"http://{Config.HOST}:{Config.PORT}/webhook/digisac-resposta",
                                 data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    print(urllib.request.urlopen(req, timeout=10).read().decode())
    print("Mensagem entregue. Aguarde ~60 s e clique em Atualizar no painel "
          "(ou rode: python simular_resposta.py --ultimos).")
