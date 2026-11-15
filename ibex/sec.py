"""Ingresos anuales consolidados desde los hechos XBRL de la SEC. Solo EEUU."""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import date

from ibex.cache import CACHE_DIR, remember
from ibex.yahoo import get_bytes

SEC_UA = {
    "User-Agent": "InversorIbex/1.0 (personal research; contact@inversoribex.local)",
    "Accept": "application/json",
    "Accept-Encoding": "identity",
}
REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
)
INCOME_CONCEPTS = (
    "NetIncomeLoss",
    "ProfitLoss",
)
ALLOWED = {"start", "end", "val", "accn", "fy", "fp", "form", "filed", "frame"}


def _sec_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=SEC_UA)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def ticker_map() -> dict[str, str]:
    def build():
        payload = json.loads(
            get_bytes("https://www.sec.gov/files/company_tickers.json", timeout=40, headers=SEC_UA)
        )
        mapping = {}
        for row in payload.values():
            ticker = str(row.get("ticker") or "").upper()
            cik = row.get("cik_str")
            if ticker and cik is not None:
                mapping[ticker] = str(int(cik)).zfill(10)
        return mapping

    return remember("sec-tickers", 7 * 24 * 3600, build, disk=True)


def _days(start: str, end: str) -> int | None:
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def _annual(concept: dict) -> list[tuple[str, float]]:
    units = (concept or {}).get("units") or {}
    facts = units.get("USD") or []
    chosen: dict[int, dict] = {}
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        if not set(fact).issubset(ALLOWED):
            continue
        if fact.get("form") not in ("10-K", "20-F", "40-F"):
            continue
        if fact.get("fp") not in ("FY", None):
            continue
        start, end = fact.get("start"), fact.get("end")
        span = _days(start, end) if start and end else None
        if span is None or not (300 <= span <= 380):
            continue
        value = fact.get("val")
        if not isinstance(value, (int, float)) or value == 0:
            continue
        year = int(fact.get("fy") or str(end)[:4])
        current = chosen.get(year)
        if current is None:
            chosen[year] = fact
            continue
        current_span = abs((_days(current.get("start"), current.get("end")) or 0) - 365)
        new_span = abs(span - 365)
        if abs(current_span - new_span) > 15:
            if new_span < current_span:
                chosen[year] = fact
        elif str(fact.get("filed") or "") >= str(current.get("filed") or ""):
            chosen[year] = fact
    rows = sorted(chosen.values(), key=lambda fact: str(fact.get("end")))
    return [(str(fact["end"]), float(fact["val"])) for fact in rows]


def _pick(usgaap: dict, concepts: tuple[str, ...], minimum: int) -> list[tuple[str, float]]:
    found = []
    for name in concepts:
        series = _annual(usgaap.get(name) or {})
        if series:
            found.append(series)
    long = [series for series in found if len(series) >= minimum]
    pool = long or found
    if not pool:
        return []
    # El ingreso consolidado es el de mayor cifra, no el de un segmento.
    pool.sort(key=lambda series: (series[-1][1], len(series)), reverse=True)
    return pool[0]


def growth_streak(values: list[float]) -> int:
    streak = 0
    for newer, older in zip(reversed(values), reversed(values[:-1])):
        if newer > older:
            streak += 1
        else:
            break
    return streak


def us_growth(symbol: str) -> dict | None:
    """Racha de ingresos anuales y beneficio del último ejercicio. None si no hay CIK."""
    ticker = symbol.upper().replace(".", "-")
    cached = CACHE_DIR / f"secgrow_{ticker}.json"
    now = time.time()
    if cached.exists():
        try:
            blob = json.loads(cached.read_text(encoding="utf-8"))
            if now - float(blob.get("_saved") or 0) < 7 * 24 * 3600:
                return blob.get("payload")
        except (OSError, ValueError, TypeError):
            pass
    mapping = ticker_map()
    cik = mapping.get(ticker)
    if not cik:
        return None

    def load():
        facts = _sec_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        usgaap = (facts.get("facts") or {}).get("us-gaap") or {}
        revenue = _pick(usgaap, REVENUE_CONCEPTS, 6)
        income = _pick(usgaap, INCOME_CONCEPTS, 2)
        if len(revenue) < 6:
            return None
        values = [value for _, value in revenue]
        streak = growth_streak(values)
        latest_income = income[-1][1] if income else None
        income_then = None
        if income and len(revenue) > 5:
            target_year = revenue[-6][0][:4]
            for when, value in income:
                if when[:4] == target_year:
                    income_then = value
        latest = values[-1]
        previous = values[-2]
        return {
            "streak": streak,
            "years": [when[:4] for when, _ in revenue[-7:]],
            "revenue": values[-7:],
            "revenue_yoy": (latest / previous - 1) * 100 if previous else None,
            "net_income": latest_income,
            "income_up_vs_5y": (
                None if latest_income is None or not income_then else latest_income > income_then
            ),
        }

    try:
        payload = load()
    except Exception:
        if cached.exists():
            try:
                return json.loads(cached.read_text(encoding="utf-8")).get("payload")
            except (OSError, ValueError, TypeError):
                return None
        raise
    try:
        cached.write_text(
            json.dumps({"_saved": now, "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass
    return payload
