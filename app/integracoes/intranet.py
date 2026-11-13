"""Intranet Líder (http://192.168.0.6) — mesmas chamadas HTTP dos nós da v28.

Login igual ao n8n: GET /home/login/ pega o 1º cookie, POST /home/login/ com esse cookie,
e todas as consultas seguintes mandam SÓ esse cookie.
"""
import logging
import time
from urllib.parse import urlencode

import requests

from ..config import Config
from .. import saida

log = logging.getLogger("central")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")

# Parâmetros fixos da página vdp/situacao_pedidos.php (copiados dos nós)
_PARAMS_SITUACAO = [
    ("cod_empresa", "11"), ("inicio", "2000-01-01"), ("fim", "2050-12-31"),
    ("cod_cliente", ""), ("estado", ""), ("cidade", ""),
    ("repi", ""), ("repf", ""), ("repi1", ""), ("repf1", ""), ("repi2", ""), ("repf2", ""),
    ("repi3", ""), ("repf3", ""), ("repi4", ""), ("repf4", ""), ("repi5", ""), ("repf5", ""),
    ("num_pedido", None), ("grupo", ""), ("cond_pgto", ""),
    ("ordenacao", "ORDER BY [#t_9].cod_repres,[#t_9].cod_cliente,[#t_9] .origem,[#t_9].cod_empresa,[#t_9].num_pedido"),
]


class ErroIntranet(Exception):
    pass


class Intranet:
    def __init__(self, base: str | None = None):
        self.base = (base or Config.INTRANET_URL).rstrip("/")
        self.cookie: str | None = None

    # ------------------------------------------------------------ base
    def _req(self, metodo: str, caminho: str, tentativas: int = 3, **kw) -> requests.Response:
        """retryOnFail do n8n: 3 tentativas com 1 s de intervalo."""
        url = caminho if caminho.startswith("http") else f"{self.base}{caminho}"
        headers = {"User-Agent": UA, **kw.pop("headers", {})}
        if self.cookie:
            headers["Cookie"] = self.cookie
        ultimo = None
        for i in range(tentativas):
            try:
                # Sem Session: o n8n só manda o cookie do login, nunca acumula outros.
                # proxies None: intranet é rede local, não passa por proxy do sistema.
                r = requests.request(metodo, url, headers=headers, timeout=kw.get("timeout", 60),
                                     allow_redirects=True, proxies={"http": None, "https": None},
                                     **{k: v for k, v in kw.items() if k != "timeout"})
                if "charset" not in r.headers.get("content-type", "").lower():
                    r.encoding = "utf-8"  # igual ao n8n quando a página não informa o charset
                return r
            except requests.RequestException as exc:
                ultimo = exc
                time.sleep(1)
        raise ErroIntranet(f"Falha ao acessar {url}: {ultimo}")

    def html(self, metodo: str, caminho: str, **kw) -> str:
        r = self._req(metodo, caminho, **kw)
        r.raise_for_status()
        return r.text

    def html_seguro(self, metodo: str, caminho: str, **kw) -> dict:
        """onError=continueRegularOutput: devolve {data} ou {error}."""
        try:
            return {"data": self.html(metodo, caminho, **kw)}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "data": ""}

    # ------------------------------------------------------------ login
    def login(self, usuario: str | None = None, senha: str | None = None) -> str:
        """Nós 'Abrir Login' + 'Login Intranet'."""
        usuario = usuario or Config.INTRANET_USUARIO
        senha = senha or Config.INTRANET_SENHA
        if not usuario or not senha:
            raise ErroIntranet("Usuário/senha da intranet não configurados (INTRANET_USUARIO / INTRANET_SENHA no .env)")
        self.cookie = None
        r = self._req("GET", "/home/login/")
        set_cookie = r.headers.get("set-cookie") or ""
        if not set_cookie:
            raise ErroIntranet("A intranet não devolveu cookie de sessão em /home/login/")
        self.cookie = set_cookie.split(";")[0]
        self._req("POST", "/home/login/",
                  headers={"Origin": self.base, "Referer": f"{self.base}/home/"},
                  files={k: (None, v) for k, v in [
                      ("pagina_acessada", f"{self.base}/home/app"), ("action", "login"),
                      ("usuario", usuario), ("senha", senha), ("logar", "Acessar")]})
        return self.cookie

    # ------------------------------------------------------------ consultas
    def pedido_lojas(self, pedido: str) -> str:
        """Nó 'Buscar Pedido': vdp/lojas.php (retry)."""
        return self.html("GET", f"/vdp/lojas.php?cod_empresa=11&numero={pedido}")

    def situacao_pedidos(self, pedido: str) -> dict:
        """Nós 'Cosultada Data Produto' / 'Consultar estoque (outlet)' / 'Consultar Itens ...'."""
        params = [(k, pedido if v is None else v) for k, v in _PARAMS_SITUACAO]
        return self.html_seguro("GET", "/vdp/situacao_pedidos.php", params=params, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "pt-BR,pt-PT;q=0.9,pt;q=0.8,en-US;q=0.7,en;q=0.6",
            "Referer": f"{self.base}/vdp/situacao_pedidos.php",
            "Upgrade-Insecure-Requests": "1",
        })

    def situacao_pedidos2(self, pedido: str) -> dict:
        return self.html_seguro("GET", "/pcp/situacao_pedidos2.php", params={"pedido": pedido})

    def conferir_boletos(self, data_iso: str) -> dict:
        """Nó 'Conferir Boletos' (POST form)."""
        return self.html_seguro("POST", "/pagamentos/pedidos-entrega-x-pagamento.php", data={
            "action": "search", "data_ini": data_iso, "data_fin": data_iso, "pedido": "", "mostrar": "S"})

    def lista_emails(self) -> dict:
        """Nó 'Lista de e-mails': inf/emails.php"""
        return self.html_seguro("GET", "/inf/emails.php")

    def projetos_postados(self) -> dict:
        return self.html_seguro("GET", "/liderprojeto/listar_arq_pojetos.php", headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{self.base}/liderprojeto/listar_arq_pojetos.php"})

    # ------------------------------------------------------------ alterações (respeitam MODO_TESTE)
    def abrir_form_alteracao(self, data_iso: str, pedido: str) -> dict:
        return self.html_seguro("GET", f"/vdp/altera_data_entrega.php?data={data_iso}&cod_empresa=11&pedido={pedido}")

    def alterar_data(self, url_alterar: str) -> dict:
        """Nó 'Alterar Data - Boleto 50%' (URL montada com os itens do formulário)."""
        return saida.externo("intranet", "alterar_data_entrega", {"url": url_alterar},
                             lambda: self.html_seguro("GET", url_alterar),
                             retorno_teste={"data": "[MODO_TESTE] alteração não enviada"})

    def aviso_entrega(self, pedido: str, cliente: str, dat_entrega: str, motivo: str,
                      observacao: str, tipo: str = "AE") -> dict:
        """Observação na intranet: vdp/aviso_entrega.php"""
        params = {"cod_empresa": "11", "num_pedido": pedido, "cliente": cliente,
                  "dat_entrega": dat_entrega, "motivo": motivo, "tipo": tipo, "observacao": observacao}
        return saida.externo(
            "intranet", "aviso_entrega", params,
            lambda: self.html_seguro("GET", "/vdp/aviso_entrega.php", params=params,
                                     headers={"Referer": f"{self.base}/vdp/aviso_entrega.php"}),
            retorno_teste={"data": "[MODO_TESTE] observação não enviada"})

    def get_url(self, caminho_ou_url: str, params=None) -> dict:
        return self.html_seguro("GET", caminho_ou_url, params=params)


def url_com_query(base: str, params: list[tuple[str, str]]) -> str:
    """encodeURIComponent em cada par (igual ao 'Montar URL Alteração')."""
    from urllib.parse import quote
    seguros = "!*'()"
    return base + "?" + "&".join(f"{quote(k, safe=seguros)}={quote(str(v), safe=seguros)}" for k, v in params)


__all__ = ["Intranet", "ErroIntranet", "url_com_query", "urlencode"]
