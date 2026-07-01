"""
Preços do mercado da Steam para o TBH: Task Bar Hero (appid 3678970).

Mantém um cache local (precos_mercado.json) com o MENOR preço de venda
(lowest "sell_price") de cada item, em BRL (centavos), raspado da API pública
/market/search/render/ (paginada de 10 em 10) e revalidado por idade.

De-para nome-do-jogo -> market_hash_name:
  - equipamento: "<Nome canônico> (<Grade>) A"  (ex.: "Shine Boots (Legendary) A")
  - material/scroll/coin/soulstone: o próprio nome canônico (ex.: "Soulstone - Hell")
Só itens com listagem ativa têm preço; os demais devolvem None (ex.: equipamento
Common/Uncommon/Rare não é vendável, ou simplesmente não há listagem agora).
"""
import json
import os
import re
import time
import urllib.request

import itens_taskbarhero as ith

APPID = 3678970
MOEDA = 7  # BRL
IDADE_MAX_H = 2  # re-raspa se o cache for mais velho que isto
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "precos_mercado.json")

_GRADE_MKT = {"common": "Common", "uncommon": "Uncommon", "rare": "Rare",
              "legendary": "Legendary", "immortal": "Immortal", "arcana": "Arcana",
              "beyond": "Beyond", "celestial": "Celestial", "divine": "Divine",
              "cosmic": "Cosmic"}


# --- de-para: nome do jogo (normalizado) -> nome canônico (com espaços) ------
def _canon_equip():
    m = {}
    for raw in ith._RAW.values():
        for g in re.finditer(r"Lv(\d+)\s+([A-Za-z][A-Za-z' ]*?)(?=\s*Lv\d+|$)", raw):
            m[ith._normalizar(g.group(2))] = g.group(2).strip()
    return m


def _canon_mat():
    # chave (normalizado, grade): alguns materiais só diferem por DÍGITOS no nome
    # (Kingdom 1st/10th/50th/100th Anniversary Coin) e o normalizador tira dígitos,
    # então colidem — o grade desempata.
    m = {}
    for por_grade in ith._MATERIAIS.values():
        for grade, nomes in por_grade.items():
            for n in nomes:
                m[(ith._normalizar(n), grade)] = n
    return m


_CANON_EQUIP = _canon_equip()
_CANON_MAT = _canon_mat()


def market_hash_name(nome, grade, nivel=None):
    """market_hash_name candidato p/ (nome, grade), ou None se nome desconhecido."""
    norm = ith._normalizar(nome)
    g = (grade or "").lower()
    if (norm, g) in _CANON_MAT:
        return _CANON_MAT[(norm, g)]       # material/scroll/coin/soulstone
    if norm in _CANON_EQUIP:
        gm = _GRADE_MKT.get(g)
        if gm:
            return f"{_CANON_EQUIP[norm]} ({gm}) A"
    # material com nome ÚNICO mas grade lida errada: cai no único candidato
    cands = {v for (nn, _gg), v in _CANON_MAT.items() if nn == norm}
    if len(cands) == 1:
        return next(iter(cands))
    return None


# --- cache de preços --------------------------------------------------------
_precos = None  # {market_hash_name: centavos}


def _raspar():
    """Raspa TODA a lista do mercado (BRL). Devolve {hash_name: centavos}."""
    base = (f"https://steamcommunity.com/market/search/render/?query=&appid={APPID}"
            f"&norender=1&currency={MOEDA}&count=100&start={{}}")
    precos = {}
    start = 0
    falhas = 0
    while True:
        try:
            with urllib.request.urlopen(base.format(start), timeout=25) as r:
                d = json.load(r)
        except Exception:
            falhas += 1
            if falhas > 8:
                break
            time.sleep(4)
            continue
        res = d.get("results") or []
        if not res:
            break
        for x in res:
            if x.get("sell_price"):
                precos[x["hash_name"]] = x["sell_price"]
        start += len(res)
        if start >= d.get("total_count", 0):
            break
        time.sleep(1.2)
    return precos


def atualizar(forcar=False, verbose=False):
    """Garante o cache de preços (re-raspa se velho/ausente). Devolve o dict
    {market_hash_name: centavos}. Em falha de rede, cai no cache velho se houver."""
    global _precos
    if _precos is not None and not forcar:
        return _precos
    if not forcar and os.path.exists(CACHE):
        try:
            c = json.load(open(CACHE))
            if time.time() - c.get("ts", 0) < IDADE_MAX_H * 3600:
                _precos = c["precos"]
                return _precos
        except Exception:
            pass
    if verbose:
        print("  atualizando preços do mercado (Steam)...", flush=True)
    precos = _raspar()
    if precos:
        try:
            json.dump({"ts": time.time(), "moeda": MOEDA, "precos": precos},
                      open(CACHE, "w"), ensure_ascii=False)
        except Exception:
            pass
        _precos = precos
    elif os.path.exists(CACHE):
        _precos = json.load(open(CACHE)).get("precos", {})  # rede falhou: usa velho
    return _precos or {}


def valor_cents(nome, grade, nivel=None):
    """Menor preço de venda (centavos BRL) do item, ou None se sem listagem."""
    mhn = market_hash_name(nome, grade, nivel)
    if not mhn:
        return None
    return atualizar().get(mhn)


def fmt(cents):
    """Centavos -> 'R$ 12,34'."""
    return f"R$ {cents / 100:.2f}".replace(".", ",")
