"""Nominatim (geocodificação) e OSRM (rota) — nós 'Geocodificar Cidade' e 'Calcular Rota OSRM'."""
import time

import requests

from ..config import Config

_ultimo_nominatim = 0.0
_ultimo_osrm = 0.0


def geocodificar(cidade: str, uf: str) -> dict:
    """Batching do n8n: 1 por vez, 1,5 s de intervalo. onError=continue -> devolve {'data': texto} ou {'error'}."""
    global _ultimo_nominatim
    espera = 1.5 - (time.time() - _ultimo_nominatim)
    if espera > 0:
        time.sleep(espera)
    try:
        r = requests.get(f"{Config.NOMINATIM_URL}/search", timeout=30,
                         params={"q": f"{cidade}, {uf}, Brasil", "format": "json", "limit": "1",
                                 "countrycodes": "br"},
                         headers={"User-Agent": "n8n-automacao-lider/1.0"})
        return {"data": r.text}
    except requests.RequestException as exc:
        return {"error": str(exc), "data": "[]"}
    finally:
        _ultimo_nominatim = time.time()


def rota(orig: dict, dest: dict) -> dict:
    """Batching 1 por vez, 0,8 s; timeout 15 s; retry. Devolve o JSON do OSRM ou {'error'}."""
    global _ultimo_osrm
    url = (f"{Config.OSRM_URL}/route/v1/driving/"
           f"{orig['lon']},{orig['lat']};{dest['lon']},{dest['lat']}")
    ultimo = None
    for _ in range(3):
        espera = 0.8 - (time.time() - _ultimo_osrm)
        if espera > 0:
            time.sleep(espera)
        try:
            r = requests.get(url, params={"overview": "false", "steps": "false"}, timeout=15)
            _ultimo_osrm = time.time()
            if r.status_code < 400:
                return r.json()
            ultimo = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as exc:
            _ultimo_osrm = time.time()
            ultimo = str(exc)
        time.sleep(1)
    return {"error": ultimo}
