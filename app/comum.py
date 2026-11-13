"""Funções repetidas em vários nós Code da v28 (traduzidas 1:1 do JavaScript)."""
import json
import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
RE_DATA_BR = re.compile(r"^\d{2}/\d{2}/\d{4}$")


# ---------------------------------------------------------------- tempo
def agora() -> datetime:
    """$now.setZone('America/Sao_Paulo')"""
    return datetime.now(TZ)


def agora_ms() -> int:
    """Date.now()"""
    return int(time.time() * 1000)


def agora_iso_utc() -> str:
    """new Date().toISOString()"""
    from datetime import timezone
    agora_utc = datetime.now(timezone.utc)
    return agora_utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora_utc.microsecond // 1000:03d}Z"


def agora_iso() -> str:
    """$now.toISO() (com fuso de Brasília)"""
    return agora().isoformat(timespec="milliseconds")


def hoje_iso() -> str:
    """$now.setZone(TZ).toFormat('yyyy-LL-dd')"""
    return agora().strftime("%Y-%m-%d")


def hoje_num() -> int:
    """Number($today.toFormat('yyyyLLdd'))"""
    return int(agora().strftime("%Y%m%d"))


def hoje_br() -> str:
    return agora().strftime("%d/%m/%Y")


def carimbo_br() -> str:
    """$now.setZone(TZ).toFormat('dd/MM/yyyy HH:mm:ss')"""
    return agora().strftime("%d/%m/%Y %H:%M:%S")


def saudacao() -> str:
    h = agora().hour
    return "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"


def data_num(d: str) -> int:
    """'dd/mm/aaaa' -> aaaammdd (Number(d.split('/').reverse().join('')))"""
    try:
        return int("".join(reversed(str(d).split("/"))))
    except ValueError:
        return 0


def parse_br(d: str) -> date:
    dia, mes, ano = (int(x) for x in str(d).split("/"))
    return date(ano, mes, dia)


def fmt_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def br_para_iso(br) -> str:
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", str(br or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def iso_ms(valor) -> int:
    """Date.parse(...) -> ms (0 se inválido)."""
    if valor in (None, ""):
        return 0
    try:
        s = str(valor).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return 0


# ---------------------------------------------------------------- feriados / dias úteis
def pascoa(ano: int) -> date:
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> set[date]:
    f = {date(ano, 1, 1), date(ano, 4, 21), date(ano, 5, 1), date(ano, 9, 7),
         date(ano, 10, 12), date(ano, 11, 2), date(ano, 11, 15), date(ano, 11, 20),
         date(ano, 12, 25)}
    f.add(pascoa(ano) - timedelta(days=2))  # Sexta-feira Santa
    return f


def eh_dia_util(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return d not in feriados_nacionais(d.year)


def adicionar_dias_uteis(d: date, quantidade: int) -> date:
    adicionados = 0
    while adicionados < quantidade:
        d = d + timedelta(days=1)
        if eh_dia_util(d):
            adicionados += 1
    return d


# ---------------------------------------------------------------- texto
def sem_acento(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if not unicodedata.combining(c))


def norm(s) -> str:
    """normalize NFD + remove acentos + espaços únicos + trim + upper"""
    return re.sub(r"\s+", " ", sem_acento(s)).strip().upper()


def limpar(texto) -> str:
    return re.sub(r"\s+", " ", re.sub(r"&nbsp;", " ", str(texto or ""), flags=re.I)).strip()


def sem_tags(texto) -> str:
    t = re.sub(r"<br\s*/?>", " ", str(texto or ""), flags=re.I)
    return limpar(re.sub(r"<[^>]+>", " ", t))


def esc(valor) -> str:
    return (str("" if valor is None else valor).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def esc3(valor) -> str:
    """Versão de esc dos nós que só trocam & < >"""
    return str("" if valor is None else valor).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def n_ped(v) -> str:
    """Último bloco de dígitos, sem zeros à esquerda (normPed / nPed / n)."""
    a = re.findall(r"\d+", str("" if v is None else v))
    return a[-1].lstrip("0") if a else ""


def primeiro_nome(nome):
    n = str(nome or "").strip()
    if not n or re.search(r"\b(LTDA|S/A|SA|ME|EIRELI|SISTEMAS|COMERCIO|INDUSTRIA)\b", n, re.I):
        return None
    p = n.split()[0]
    return p[:1].upper() + p[1:].lower()


def capitalizar(p: str) -> str:
    return p[:1].upper() + p[1:].lower() if p else p


# ---------------------------------------------------------------- telefone / documento
def normalizar_celular(raw):
    d = re.sub(r"\D", "", str("" if raw is None else raw))
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    d = d.lstrip("0")
    if len(d) == 10 and re.match(r"^[1-9][1-9][6-9]", d):
        d = d[:2] + "9" + d[2:]
    return "55" + d if re.match(r"^[1-9][1-9]9\d{8}$", d) else None


def chave_tel(raw):
    d = re.sub(r"\D", "", str("" if raw is None else raw))
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    d = d.lstrip("0")
    return d[:2] + d[-8:] if len(d) >= 10 else None


def cpf_valido(c: str) -> bool:
    if not re.match(r"^\d{11}$", c) or re.match(r"^(\d)\1{10}$", c):
        return False

    def dv(n):
        s = sum(int(c[i]) * (n + 1 - i) for i in range(n))
        r = (s * 10) % 11
        return 0 if r == 10 else r
    return dv(9) == int(c[9]) and dv(10) == int(c[10])


def cnpj_valido(c: str) -> bool:
    if not re.match(r"^\d{14}$", c) or re.match(r"^(\d)\1{13}$", c):
        return False

    def dv(n):
        p = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if n == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        s = sum(int(c[i]) * p[i] for i in range(n))
        r = s % 11
        return 0 if r < 2 else 11 - r
    return dv(12) == int(c[12]) and dv(13) == int(c[13])


def normalizar_cpf(raw):
    """Documento da intranet com 15 dígitos (v20)."""
    d = re.sub(r"\D", "", str("" if raw is None else raw))
    if len(d) == 15:
        cpf = d[:9] + d[13:]
        cnpj = d[1:] if d.startswith("0") else None
        if d[9:13] == "0000" and cpf_valido(cpf):
            return cpf
        if cnpj and cnpj_valido(cnpj):
            return cnpj
        if cpf_valido(cpf):
            return cpf
        return cnpj
    if len(d) == 10:
        return d.zfill(11)
    if len(d) in (11, 14):
        return d
    return None


# ---------------------------------------------------------------- números
def valor_br(v) -> float:
    s = re.sub(r"[^\d.-]", "", str(v).replace(".", "").replace(",", "."))
    try:
        return float(s)
    except ValueError:
        return float("nan")


def parse_qtd(q) -> float:
    s = str("" if q is None else q).strip()
    try:
        return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    except ValueError:
        return 1.0


def fmt_num(x: float) -> str:
    """Número como o JS imprime (2 e não 2.0)."""
    return str(int(x)) if float(x).is_integer() else str(x)


def linha_item(it: dict) -> str:
    nome = re.sub(r"\s+", " ", str(it.get("descricao") or "").split(" - ")[0]).strip()
    q = parse_qtd(it.get("quantidade"))
    return f"• {fmt_num(q) + 'x ' if q > 1 else ''}{nome}"


def lista_txt(arr: list) -> str:
    return f"{', '.join(arr[:-1])} e {arr[-1]}" if len(arr) > 1 else (arr[0] if arr else "")


# ---------------------------------------------------------------- JSON
def dumps(obj) -> str:
    """JSON.stringify (sem espaços, mantendo acentos)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def loads(s, padrao=None):
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s) if s not in (None, "") else padrao
    except (TypeError, ValueError):
        return padrao


def unicos(seq):
    """[...new Set(seq)] preservando a ordem"""
    vistos, saida = set(), []
    for x in seq:
        k = json.dumps(x, sort_keys=True, default=str) if isinstance(x, (dict, list)) else x
        if k not in vistos:
            vistos.add(k)
            saida.append(x)
    return saida
