"""Screener, calidad, dividendos y gangas."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ibex.cache import remember
from ibex.catalog import EU_REGIONS, KINGS, REGION_ES, SECTOR_ES, SP500_ARISTOCRATS
from ibex.sec import growth_streak, us_growth
from ibex.yahoo import annual_series, screen, spark

FIELDS_NOTE = "Cifras de Yahoo Finance, diferidas. La racha de dividendo es el campo de Yahoo, no un cálculo propio."


def _eq(field: str, value) -> dict:
    return {"operator": "eq", "operands": [field, value]}


def _gt(field: str, value: float) -> dict:
    return {"operator": "gt", "operands": [field, value]}


def _gte(field: str, value: float) -> dict:
    return {"operator": "gte", "operands": [field, value]}


def _lt(field: str, value: float) -> dict:
    return {"operator": "lt", "operands": [field, value]}


def region_clause(region: str) -> dict:
    if region == "eu":
        return {"operator": "or", "operands": [_eq("region", code) for code in EU_REGIONS]}
    return _eq("region", region)


def listed_us() -> dict:
    return {
        "operator": "or",
        "operands": [
            _eq("exchange", "NMS"),
            _eq("exchange", "NYQ"),
        ],
    }


def _num(row: dict, key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _debt_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    # En este screener Yahoo entrega la deuda/capital como porcentaje (84 = 0,84x).
    if abs(value) > 10:
        return value / 100.0
    return value


def normalize(row: dict, region_hint: str) -> dict:
    region = (row.get("region") or region_hint or "").lower()
    if region_hint == "eu" and region in ("", "eu"):
        group = "eu"
    elif region == "us":
        group = "us"
    elif region == "ca":
        group = "ca"
    elif region in EU_REGIONS:
        group = "eu"
    else:
        group = region or region_hint
    price = _num(row, "intradayprice")
    high = _num(row, "lastclose52weekhigh")
    market_cap = _num(row, "intradaymarketcap")
    symbol = str(row.get("ticker") or "").upper()
    exchange = row.get("exchange") or ""
    currency = row.get("currency") or ""
    # Londres llega en peniques: 13.982 GBp son 139,82 libras. La capitalización usa la misma unidad.
    if exchange.upper() == "LSE" or symbol.endswith(".L"):
        if price is not None:
            price = price / 100.0
        if high is not None:
            high = high / 100.0
        if market_cap is not None:
            market_cap = market_cap / 100.0
        currency = "GBP"
    drawdown = None
    if price and high and high > 0:
        drawdown = (price / high - 1) * 100
    sector = row.get("sector") or ""
    years = _num(row, "consecutive_years_of_dividend_growth_count")
    return {
        "symbol": symbol,
        "name": row.get("companyshortname") or symbol,
        "region": region or region_hint,
        "group": group,
        "region_label": REGION_ES.get(region or region_hint, (region or region_hint or "").upper()),
        "sector": sector,
        "sector_label": SECTOR_ES.get(sector, sector or "—"),
        "exchange": exchange,
        "price": price,
        "currency": currency,
        "change_pct": _num(row, "percentchange"),
        "change_52w": _num(row, "fiftytwowkpercentchange"),
        "drawdown_pct": drawdown,
        "market_cap": market_cap,
        "pe": _num(row, "peratio"),
        "dividend_yield": _num(row, "forward_dividend_yield"),
        "roe": _num(row, "returnonequity"),
        "margin": _num(row, "netincomemargin"),
        "gross_margin": _num(row, "grossprofitmargin"),
        "ebitda_margin": _num(row, "ebitdamargin"),
        "debt": _debt_ratio(_num(row, "totaldebtequity")),
        "revenue_growth": _num(row, "totalrevenues1yrgrowth"),
        "eps_growth": _num(row, "epsgrowth"),
        "dividend_years": int(years) if years is not None else None,
        "aristocrat": symbol in SP500_ARISTOCRATS,
        "king": symbol in KINGS or (years is not None and years >= 50),
    }


_JUNK_EXCHANGES = {"FRA", "BER", "STU", "DUS", "MUN", "HAM", "HAN", "IOB", "CXE", "AQS", "NEO"}


def tradable(item: dict) -> bool:
    """Quita CDRs, cotizaciones numeradas de Londres y el mercado abierto alemán."""
    symbol = item.get("symbol") or ""
    exchange = (item.get("exchange") or "").upper()
    name = (item.get("name") or "").upper()
    if not symbol or symbol[0].isdigit():
        return False
    if " CDR" in f" {name}" or "CAD HEDGED" in name:
        return False
    if symbol.endswith(".F") or exchange in _JUNK_EXCHANGES:
        return False
    return True


_STOPWORDS = (
    "inc", "corp", "corporation", "incorporated", "ltd", "plc", "sa", "se", "ag", "nv",
    "class", "ord", "shs", "common", "stock", "company", "co", "the", "holding", "holdings",
    "group", "grp", "international", "intl", "limited", "llc", "and",
)

# Raíces de EEUU que Yahoo cuelga en Fráncfort, Zúrich o Viena aunque no entren
# en el universo de calidad (Berkshire, por ejemplo). No se usa en Canadá:
# Shopify o Enbridge sí llevan "Inc" y cotizan en casa.
_US_ROOTS_ABROAD = {
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "BRK",
    "LLY", "JPM", "V", "MA", "UNH", "XOM", "JNJ", "COST", "WMT", "PG", "HD", "KO",
    "BAC", "CRM", "NFLX", "ORCL", "AMD", "MU", "PLTR", "CSCO", "ABBV", "MRK", "PEP",
    "TMO", "ACN", "LIN", "TXN", "QCOM", "AMAT", "LRCX", "INTU", "NOW", "GE", "IBM",
    "CAT", "GS", "MS", "AXP", "CVX", "WFC", "DIS", "MCD", "ADBE", "PFE", "BA",
}


def _clean_name(name: str) -> str:
    text = re.sub(r"\s+", " ", (name or "").strip())
    text = re.sub(r"\bs\.?\s*p\.?\s*a\.?\b", " ", text, flags=re.I)
    text = re.sub(r"\bs\.?\s*a\.?\b", " ", text, flags=re.I)
    text = re.sub(r"\s+(ord|inh\.?|eo)\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s+2\.?\s*linie\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s+ser\.?\s*[ab]\b", "", text, flags=re.I)
    text = re.sub(r"\s+(class|cl)\s+[a-z0-9]\b", "", text, flags=re.I)
    text = re.sub(r"\ba/s\b", " ", text, flags=re.I)
    text = re.sub(r"\b(as|asa)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+[A-Za-z]$", "", text).strip()
    text = re.sub(r"\s+[A-Za-z]$", "", text).strip()
    return text


def _name_key(name: str) -> str:
    text = _clean_name(name).lower()
    text = re.sub(r"\b(" + "|".join(_STOPWORDS) + r")\b", " ", text)
    text = re.sub(r"[^a-z0-9]", "", text)
    return text[:22]


def _tokens(name: str) -> set[str]:
    text = _clean_name(name).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    stop = set(_STOPWORDS)
    return {token for token in text.split() if token not in stop and len(token) > 2}


def _root(symbol: str) -> str:
    return symbol.split(".")[0].split("-")[0].upper()


def _looks_american(name: str) -> bool:
    upper = f" {(name or '').upper()} "
    if any(token in upper for token in (" INC", " INC.", " CORP", " CORP.", " CORPORATION", " INCORPORATED")):
        return True
    return bool(re.search(r"\bCO\b", upper))


def _has_local_form(name: str) -> bool:
    upper = f" {_clean_name(name).upper()} "
    markers = (" SE ", " AG ", " PLC ", " NV ", " N.V ", " AB ", " ASA ", " OYJ ", " SPA ", " S.A ", " SA ")
    return any(marker in upper for marker in markers)


def _share_marker(name: str) -> str:
    parts = (name or "").strip().split()
    if parts and len(parts[-1]) == 1 and parts[-1].isalpha():
        return parts[-1].upper()
    return ""


def _europe_local(item: dict) -> bool:
    if item.get("group") != "eu":
        return True
    symbol = item.get("symbol") or ""
    name = (item.get("name") or "").upper()
    if symbol.endswith(".L") or (item.get("exchange") or "").upper() == "LSE":
        return "PLC" in name
    return symbol.endswith(
        (".DE", ".PA", ".MC", ".AS", ".MI", ".SW", ".CO", ".ST", ".HE", ".OL", ".BR", ".LS", ".VI", ".IR", ".WA")
    )


def _obvious_replica(item: dict) -> bool:
    """CDRs, preferentes y la acción extranjera colgada en otra bolsa."""
    if not tradable(item):
        return True
    name = item.get("name") or ""
    upper = name.upper()
    symbol = item.get("symbol") or ""
    region = item.get("region") or ""
    if "PREF" in upper or " PRF" in f" {upper}" or re.search(r"(^|[^A-Z])(ADR|GDR)([^A-Z]|$)", upper):
        return True
    if "PETROLEO BRASILEIRO" in upper or "PETROBRAS" in upper:
        return True
    if symbol.endswith(".TO") and "-P" in symbol:
        return True
    if symbol.endswith(".DE") and re.search(r"\d", _root(symbol)) and not _has_local_form(name):
        return True
    if region != "us" and _share_marker(name) == "R":
        return True
    if region not in ("us", "ca") and _looks_american(name):
        return True
    if region == "gb" or symbol.endswith(".L"):
        if (item.get("exchange") or "").upper() not in ("", "LSE"):
            return True
        if "PLC" not in upper:
            return True
    if region == "ca":
        if (item.get("exchange") or "").upper() not in ("", "TOR"):
            return True
        if not symbol.endswith(".TO"):
            return True
    if item.get("group") == "eu" and not _europe_local(item):
        return True
    return False


def _same_company(left: str, right: str) -> bool:
    if _name_key(left) and _name_key(left) == _name_key(right):
        return True
    shared = _tokens(left) & _tokens(right)
    return any(len(token) >= 5 for token in shared)


def _listing_rank(item: dict, peers: list[dict]) -> float:
    """Más alto, mejor: casa antes que la réplica, y a igualdad la nota."""
    name = item.get("name") or ""
    region = item.get("region") or ""
    symbol = item.get("symbol") or ""
    upper = name.upper()
    score = float(item.get("score") or 0)
    if "PLC" in upper and region == "gb":
        score += 40
    if region == "nl" and (" N.V" in upper or " NV" in f" {upper}"):
        score += 30
    others = [peer for peer in peers if peer["symbol"] != symbol]
    home_elsewhere = {"nl", "fr", "gb", "dk", "se", "it", "es", "fi", "be", "pt", "ie", "no", "ca", "us"}
    if region == "de" and any(peer.get("region") in home_elsewhere for peer in others):
        score -= 40
    if region == "at" and any(peer.get("region") != "at" for peer in others):
        score -= 40
    if region == "ch" and any(peer.get("region") in home_elsewhere for peer in others):
        score -= 25
    # En Fráncfort el código suele cambiar (RHO, IXD1). En Zúrich, si el ticker
    # es el mismo que en Alemania, la casa es la alemana (ENR).
    if region == "de" and any(peer.get("region") == "ch" and _root(peer["symbol"]) != _root(symbol) for peer in others):
        score -= 30
    if region == "ch" and any(peer.get("region") == "de" and _root(peer["symbol"]) == _root(symbol) for peer in others):
        score -= 30
    bias = {"fr": 8, "de": 7, "nl": 7, "ch": 7, "gb": 7, "es": 5, "it": 5, "se": 5, "dk": 5, "ca": 8, "us": 8}.get(region, 3)
    score += bias
    score += min((item.get("market_cap") or 0) / 1e12, 2)
    return score


def prefer_home(items: list[dict], us_roots: set[str] | None = None) -> list[dict]:
    """Una fila por empresa, en su mercado de origen y no en la réplica."""
    roots = set(us_roots or ()) | _US_ROOTS_ABROAD
    kept: list[dict] = []
    for item in items:
        if _obvious_replica(item):
            continue
        region = item.get("region") or ""
        if region in ("de", "ch", "at") and _root(item["symbol"]) in roots and not _has_local_form(item.get("name") or ""):
            continue
        kept.append(item)
    us_rows = [item for item in kept if item.get("group") == "us" and "." not in item["symbol"]]
    drop_us: set[str] = set()
    for item in kept:
        if item.get("group") == "us":
            continue
        for match in us_rows:
            if _same_company(item.get("name") or "", match.get("name") or ""):
                drop_us.add(match["symbol"])
    kept = [item for item in kept if item["symbol"] not in drop_us]
    groups: dict[str, list[dict]] = {}
    for item in kept:
        groups.setdefault(_name_key(item["name"]) or item["symbol"], []).append(item)
    chosen = []
    for peers in groups.values():
        # Une también "Roche" con "Roche Holding" si una clave es prefijo de la otra.
        chosen.append(max(peers, key=lambda item: _listing_rank(item, peers)))
    folded: list[dict] = []
    for item in sorted(chosen, key=lambda row: len(_name_key(row["name"]))):
        key = _name_key(item["name"])
        host = None
        for prev in folded:
            other = _name_key(prev["name"])
            if key and other and (key == other or (len(key) >= 5 and other.startswith(key)) or (len(other) >= 5 and key.startswith(other))):
                host = prev
                break
        if host is None:
            folded.append(item)
            continue
        pair = [host, item]
        winner = max(pair, key=lambda row: _listing_rank(row, pair))
        if winner is not host:
            folded[folded.index(host)] = winner
    return folded


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def quality_score(row: dict) -> float:
    """0 a 100. Calidad, crecimiento y un precio que no esté disparado.

    ROE 20, margen neto 15, deuda 10, crecimiento de ingresos 15,
    crecimiento del beneficio 10, PER 15, recorrido a 12 meses 10,
    años de dividendo 5. En finanzas la deuda no puntúa: el ratio no
    se compara con el de una industrial.
    """
    score = 0.0
    roe = row.get("roe")
    if roe is not None:
        score += _clamp(roe, 0, 35) / 35 * 20
    margin = row.get("margin")
    if margin is not None:
        score += _clamp(margin, 0, 28) / 28 * 15
    financial = row.get("sector") == "Financial Services"
    debt = row.get("debt")
    if financial:
        score += 6
    elif debt is not None:
        score += _clamp(1.8 - debt, 0, 1.8) / 1.8 * 10
    growth = row.get("revenue_growth")
    if growth is not None:
        score += _clamp(growth + 5, 0, 25) / 25 * 15
    eps = row.get("eps_growth")
    if eps is not None:
        score += _clamp(eps + 5, 0, 30) / 30 * 10
    pe = row.get("pe")
    if pe is None:
        score += 6
    elif pe <= 0:
        score += 0
    elif pe <= 22:
        score += 15
    elif pe <= 35:
        score += 15 - (pe - 22) / 13 * 7
    elif pe <= 55:
        score += 8 - (pe - 35) / 20 * 6
    else:
        score += 1
    change = row.get("change_52w")
    if change is not None:
        if -5 <= change <= 35:
            score += 10
        elif -25 <= change < -5 or 35 < change <= 60:
            score += 6
        elif change < -40:
            score += 2
        else:
            score += 4
    years = row.get("dividend_years") or 0
    score += _clamp(years, 0, 25) / 25 * 5
    return round(score, 1)


def run_screen(region: str, sector: str, cap: float, pe_max: float | None, yield_min: float | None, roe_min: float | None, growth_min: float | None, change_min: float | None, change_max: float | None, sort_field: str, sort_dir: str, size: int) -> dict:
    operands = [region_clause(region), _gte("intradaymarketcap", cap)]
    if region == "us":
        operands.append(listed_us())
    elif region == "ca":
        operands.append(_eq("exchange", "TOR"))
    if sector:
        operands.append(_eq("sector", sector))
    if pe_max is not None:
        operands += [_gt("peratio.lasttwelvemonths", 0), _lt("peratio.lasttwelvemonths", pe_max)]
    if yield_min is not None:
        operands.append(_gte("forward_dividend_yield", yield_min))
    if roe_min is not None:
        operands.append(_gte("returnonequity.lasttwelvemonths", roe_min))
    if growth_min is not None:
        operands.append(_gte("totalrevenues1yrgrowth.lasttwelvemonths", growth_min))
    if change_min is not None:
        operands.append(_gte("fiftytwowkpercentchange", change_min))
    if change_max is not None:
        operands.append(_lte("fiftytwowkpercentchange", change_max))
    allowed = {
        "intradaymarketcap",
        "percentchange",
        "fiftytwowkpercentchange",
        "peratio.lasttwelvemonths",
        "returnonequity.lasttwelvemonths",
        "forward_dividend_yield",
        "totalrevenues1yrgrowth.lasttwelvemonths",
        "consecutive_years_of_dividend_growth_count",
        "netincomemargin.lasttwelvemonths",
    }
    if sort_field not in allowed:
        sort_field = "intradaymarketcap"
    ask = max(1, min(size, 100))
    fetch = ask if region == "us" else min(100, max(ask * 3, 60))
    rows, total = screen(operands, sort_field, "ASC" if sort_dir == "asc" else "DESC", fetch)
    items = []
    for row in rows:
        if not row.get("ticker"):
            continue
        item = normalize(row, region)
        item["score"] = quality_score(item)
        if _obvious_replica(item):
            continue
        items.append(item)
    items = items[:ask]
    return {
        "asof": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "Yahoo Finance",
        "note": FIELDS_NOTE,
        "total": total,
        "items": items,
        "stale": False,
        "error": None,
    }


def _lte(field: str, value: float) -> dict:
    return {"operator": "lte", "operands": [field, value]}


# Bolsa de origen y suelo de capitalización en la unidad que devuelve Yahoo.
# Londres va en peniques: 1e12 peniques son 10.000 millones de libras.
_QUALITY_QUERIES = (
    ("us", 20_000_000_000, 60, None, None),
    ("ca", 8_000_000_000, 60, "TOR", 2_000_000_000_000),
    ("de", 20_000_000_000, 120, "GER", 2_000_000_000_000),
    ("fr", 15_000_000_000, 18, "PAR", None),
    ("gb", 1_000_000_000_000, 25, "LSE", None),
    ("es", 8_000_000_000, 12, "MCE", None),
    ("nl", 10_000_000_000, 12, "AMS", None),
    ("it", 8_000_000_000, 12, "MIL", None),
    ("ch", 40_000_000_000, 30, "EBS", 2_000_000_000_000),
    ("se", 80_000_000_000, 10, "STO", None),
    ("dk", 80_000_000_000, 8, "CPH", None),
    ("fi", 8_000_000_000, 6, "HEL", None),
    ("be", 8_000_000_000, 6, "BRU", None),
    ("no", 40_000_000_000, 6, "OSL", None),
    ("pt", 4_000_000_000, 5, "LIS", None),
    ("at", 5_000_000_000, 8, "VIE", 2_000_000_000_000),
    ("ie", 4_000_000_000, 6, "DUB", None),
)


def _pull_quality(region: str, cap: float, size: int, exchange: str | None, cap_max: float | None) -> tuple[list[dict], str | None]:
    def operands(use_exchange: bool) -> list[dict]:
        query = [
            region_clause(region),
            _gte("intradaymarketcap", cap),
            _gte("returnonequity.lasttwelvemonths", 8),
            _gte("netincomemargin.lasttwelvemonths", 4),
        ]
        if cap_max is not None:
            query.append(_lte("intradaymarketcap", cap_max))
        if region == "us":
            query.append(listed_us())
        if use_exchange and exchange:
            query.append(_eq("exchange", exchange))
        return query

    try:
        rows, total = screen(operands(True), "intradaymarketcap", "DESC", size)
    except Exception as exc:  # noqa: BLE001
        return [], f"{region}: {exc}"
    if total == 0 and exchange:
        try:
            rows, _total = screen(operands(False), "intradaymarketcap", "DESC", size)
        except Exception as exc:  # noqa: BLE001
            return [], f"{region}: {exc}"
    items = []
    for row in rows:
        item = normalize(row, region)
        if not item["symbol"]:
            continue
        item["score"] = quality_score(item)
        items.append(item)
    return items, None


def build_quality() -> dict:
    merged: list[dict] = []
    errors: list[str] = []
    us_roots: set[str] = set()
    for region, cap, size, exchange, cap_max in _QUALITY_QUERIES:
        items, error = _pull_quality(region, cap, size, exchange, cap_max)
        if error:
            errors.append(error)
            continue
        if region == "us":
            us_roots = {_root(item["symbol"]) for item in items}
        merged.extend(items)
    unique = prefer_home(merged, us_roots)
    unique.sort(key=lambda item: item["score"], reverse=True)
    limits = {"us": 24, "ca": 12, "eu": 40}
    capped = []
    counts: dict[str, int] = {}
    for item in unique:
        group = item.get("group") or ""
        if counts.get(group, 0) >= limits.get(group, 8):
            continue
        counts[group] = counts.get(group, 0) + 1
        capped.append(item)
    return {
        "asof": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "Yahoo Finance",
        "note": (
            "Universo líquido con ROE por encima del 8% y margen neto por encima del 4%, "
            "en la bolsa de origen: Nueva York o Nasdaq, Toronto, y las plazas europeas. "
            "Se descartan CDRs, preferentes y la misma acción repetida en Fráncfort, Zúrich o Viena. "
            "La puntuación premia rentabilidad, margen, poca deuda, crecimiento y un PER contenido. "
            "No es una recomendación de compra."
        ),
        "rules": [
            "ROE hasta 20 puntos, con tope en el 35% para que un apalancamiento contable no se lleve la nota.",
            "Margen neto hasta 15 puntos.",
            "Deuda/capital hasta 10 puntos. En bancos y aseguradoras ese ratio no se usa.",
            "Crecimiento de ingresos 15 y del beneficio por acción 10.",
            "PER hasta 15: la zona alta está entre 0 y 22 veces. Por encima de 55 casi no puntúa.",
            "Recorrido de 12 meses hasta 10: se premia lo que sube con orden, no el derrumbe ni la euforia.",
            "Años de subida del dividendo, hasta 5 puntos.",
        ],
        "items": capped,
        "universe": len(capped),
        "warnings": errors,
        "stale": False,
        "error": None if capped else "; ".join(errors) or "Sin resultados",
    }


def quality_universe() -> dict:
    return remember("calidad-v4", 30 * 60, build_quality, disk=True)


def _thin_quote(symbol: str, hit: dict) -> dict:
    points = hit["points"]
    meta = hit["meta"]
    last = points[-1]["c"]
    prev = points[-2]["c"] if len(points) > 1 else None
    change = None if prev in (None, 0) else (last / prev - 1) * 100
    return {
        "symbol": symbol,
        "name": meta.get("shortName") or meta.get("longName") or symbol,
        "region": "us",
        "group": "us",
        "region_label": "EEUU",
        "sector": "",
        "sector_label": "—",
        "exchange": meta.get("exchangeName") or "",
        "price": last,
        "currency": meta.get("currency") or "",
        "change_pct": change,
        "change_52w": None,
        "drawdown_pct": None,
        "market_cap": meta.get("marketCap"),
        "pe": None,
        "dividend_yield": None,
        "roe": None,
        "margin": None,
        "gross_margin": None,
        "ebitda_margin": None,
        "debt": None,
        "revenue_growth": None,
        "eps_growth": None,
        "dividend_years": None,
        "aristocrat": symbol in SP500_ARISTOCRATS,
        "king": symbol in KINGS,
        "score": None,
    }


def dividends() -> dict:
    def build():
        merged = []
        errors = []
        us_ops = [
            region_clause("us"),
            listed_us(),
            _gte("intradaymarketcap", 300_000_000),
            _gte("consecutive_years_of_dividend_growth_count", 10),
        ]
        offset = 0
        while offset < 300:
            try:
                rows, total = screen(
                    us_ops,
                    "consecutive_years_of_dividend_growth_count",
                    "DESC",
                    100,
                    offset,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"us: {exc}")
                break
            for row in rows:
                item = normalize(row, "us")
                if item["symbol"] and (item["king"] or item["aristocrat"] or tradable(item)):
                    merged.append(item)
            offset += 100
            if offset >= total:
                break
        # Por país: si se pide Europa entera, las réplicas con rachas de EEUU
        # ocupan el cupo y no dejan entrar a las de casa.
        for region, years, cap, size, exchange in (
            ("ca", 5, 1_000_000_000, 60, "TOR"),
            ("gb", 10, 200_000_000_000, 30, "LSE"),
            ("de", 10, 2_000_000_000, 40, "GER"),
            ("fr", 10, 2_000_000_000, 25, "PAR"),
            ("es", 10, 1_000_000_000, 20, "MCE"),
            ("nl", 10, 2_000_000_000, 20, "AMS"),
            ("ch", 10, 5_000_000_000, 20, "EBS"),
            ("it", 10, 1_000_000_000, 20, "MIL"),
            ("se", 10, 20_000_000_000, 15, "STO"),
            ("dk", 10, 20_000_000_000, 12, "CPH"),
            ("fi", 10, 2_000_000_000, 10, "HEL"),
            ("no", 10, 20_000_000_000, 10, "OSL"),
            ("be", 10, 1_000_000_000, 10, "BRU"),
            ("pt", 10, 1_000_000_000, 8, "LIS"),
            ("ie", 10, 1_000_000_000, 8, "DUB"),
        ):
            operands = [
                region_clause(region),
                _gte("intradaymarketcap", cap),
                _gte("consecutive_years_of_dividend_growth_count", years),
            ]
            if exchange:
                operands.append(_eq("exchange", exchange))
            try:
                rows, total = screen(operands, "consecutive_years_of_dividend_growth_count", "DESC", size)
                if total == 0 and exchange:
                    rows, _total = screen(operands[:-1], "consecutive_years_of_dividend_growth_count", "DESC", size)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{region}: {exc}")
                continue
            for row in rows:
                item = normalize(row, region)
                if item["symbol"] and not _obvious_replica(item):
                    merged.append(item)
        seen = set()
        unique = []
        for item in merged:
            if item["symbol"] in seen:
                continue
            seen.add(item["symbol"])
            unique.append(item)
        unique = prefer_home(unique)
        seen = {item["symbol"] for item in unique}
        official = sorted((KINGS | SP500_ARISTOCRATS) - seen)
        if official:
            try:
                raw = spark(official, range_="5d", interval="1d")
            except Exception as exc:  # noqa: BLE001
                raw = {}
                errors.append(f"cotización de listas: {exc}")
            for symbol in official:
                hit = raw.get(symbol.upper())
                if hit and hit.get("points"):
                    unique.append(_thin_quote(symbol, hit))
                    seen.add(symbol)
        missing = sorted((KINGS | SP500_ARISTOCRATS) - seen)
        return {
            "asof": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "Yahoo Finance",
            "note": (
                "Rey: censo público de 60 empresas a 1 de noviembre de 2026, con 50 años o más subiendo el dividendo. "
                "No todas están en el S&P 500. Aristócrata: 68 miembros del S&P 500 a 2 de noviembre de 2026, sin Kenvue. "
                "La columna de años es la de Yahoo y a veces se queda por debajo de la racha real. "
                "En Canadá se listan rachas de cinco años o más. En Europa, de diez o más. Esta web no recalcula los años."
            ),
            "items": unique,
            "missing_aristocrats": [symbol for symbol in missing if symbol in SP500_ARISTOCRATS],
            "missing_kings": [symbol for symbol in missing if symbol in KINGS],
            "warnings": errors,
            "stale": False,
            "error": None if unique else "; ".join(errors) or "Sin resultados",
        }

    return remember("dividendos-v5", 60 * 60, build, disk=True)


def _yahoo_streak(symbol: str) -> dict | None:
    revenue = annual_series(symbol, "annualTotalRevenue")
    income = annual_series(symbol, "annualNetIncome")
    if len(revenue) < 4:
        return None
    values = [value for _, value in revenue]
    streak = growth_streak(values)
    if streak < 3:
        return None
    latest_income = income[-1][1] if income else None
    if latest_income is not None and latest_income <= 0:
        return None
    previous = values[-2]
    return {
        "streak": streak,
        "years": [when[:4] for when, _ in revenue],
        "revenue_yoy": (values[-1] / previous - 1) * 100 if previous else None,
        "source": "Yahoo",
        "window": "4 ejercicios publicados por Yahoo",
    }


def gangas() -> dict:
    def build():
        us_ops = [
            region_clause("us"),
            listed_us(),
            _gte("intradaymarketcap", 8_000_000_000),
            _lt("fiftytwowkpercentchange", -8),
            _gt("totalrevenues1yrgrowth.lasttwelvemonths", 0),
            _gt("netincomemargin.lasttwelvemonths", 0),
        ]
        other = []
        for region, cap in (("ca", 4_000_000_000), ("eu", 5_000_000_000)):
            other.append(
                (
                    region,
                    [
                        region_clause(region),
                        _gte("intradaymarketcap", cap),
                        _lt("fiftytwowkpercentchange", -8),
                        _gt("totalrevenues1yrgrowth.lasttwelvemonths", 0),
                        _gt("netincomemargin.lasttwelvemonths", 0),
                    ],
                    20,
                )
            )
        candidates = []
        errors = []
        try:
            rows, _total = screen(us_ops, "fiftytwowkpercentchange", "ASC", 30)
            for row in rows:
                item = normalize(row, "us")
                if item["symbol"] and tradable(item):
                    item["market"] = "us"
                    candidates.append(item)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"us: {exc}")
        intl = []
        for region, operands, size in other:
            try:
                rows, _total = screen(operands, "fiftytwowkpercentchange", "ASC", size)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{region}: {exc}")
                continue
            for row in rows:
                item = normalize(row, region)
                # Londres llega en peniques: tras normalizar, 1e9 ya son 1.000 millones de libras.
                if item["symbol"] and "." in item["symbol"] and not _obvious_replica(item) and (item.get("market_cap") or 0) >= 1_000_000_000:
                    item["market"] = region
                    intl.append(item)

        checked = []

        def one_us(item):
            facts = us_growth(item["symbol"])
            time.sleep(0.12)
            return item, facts

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(one_us, item) for item in candidates]
            for future in as_completed(futures):
                try:
                    item, facts = future.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))
                    continue
                if not facts or facts["streak"] < 5:
                    continue
                if facts.get("net_income") is not None and facts["net_income"] <= 0:
                    continue
                item["streak"] = facts["streak"]
                item["streak_years"] = facts["years"]
                item["revenue_yoy_sec"] = facts.get("revenue_yoy")
                item["income_up_vs_5y"] = facts.get("income_up_vs_5y")
                item["history"] = "SEC"
                checked.append(item)

        intl_hits = []

        def one_intl(item):
            return item, _yahoo_streak(item["symbol"])

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(one_intl, item) for item in intl]
            for future in as_completed(futures):
                try:
                    item, facts = future.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))
                    continue
                if not facts:
                    continue
                item["streak"] = facts["streak"]
                item["streak_years"] = facts["years"]
                item["revenue_yoy_sec"] = facts.get("revenue_yoy")
                item["income_up_vs_5y"] = None
                item["history"] = "Yahoo"
                intl_hits.append(item)

        checked.sort(key=lambda item: (item["streak"], -(item["change_52w"] or 0)), reverse=True)
        intl_hits.sort(key=lambda item: (item["streak"], -(item["change_52w"] or 0)), reverse=True)
        return {
            "asof": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "SEC EDGAR y Yahoo Finance",
            "rule": (
                "EEUU: ingresos anuales consolidados al alza en cada uno de los últimos cinco ejercicios como mínimo "
                "(hechos 10-K de la SEC), beneficio neto último positivo, y la acción pierde más de un 8% a doce meses. "
                "Canadá y Europa: Yahoo solo publica cuatro ejercicios; se piden tres subidas seguidas, beneficio positivo "
                "y la misma caída de la acción. No es una recomendación."
            ),
            "us": checked,
            "international": intl_hits,
            "scanned_us": len(candidates),
            "warnings": errors[:8],
            "stale": False,
            "error": None,
        }

    return remember("gangas-v2", 6 * 3600, build, disk=True)
