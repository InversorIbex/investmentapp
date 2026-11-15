"""Cartera modelo de papel. Reglas públicas. No es una recomendación."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ibex.market import fear_greed
from ibex.screen import quality_universe
from ibex.yahoo import spark

ROOT = Path(__file__).resolve().parent.parent
# En Vercel la cartera de papel no sobrevive a otra instancia: no hay disco persistente.
if os.environ.get("VERCEL"):
    PATH = Path(tempfile.gettempdir()) / "ibex-portfolio.json"
else:
    PATH = ROOT / "data" / "portfolio.json"
_lock = threading.Lock()
BASE_EUR = 100_000.0
MADRID = ZoneInfo("Europe/Madrid")

FX_SYMBOLS = {
    "USD": "EURUSD=X",
    "GBP": "EURGBP=X",
    "CAD": "EURCAD=X",
    "CHF": "EURCHF=X",
    "SEK": "EURSEK=X",
    "DKK": "EURDKK=X",
    "NOK": "EURNOK=X",
}
BENCH = [
    ("^GSPC", "S&P 500", 0.50),
    ("^STOXX50E", "Euro Stoxx 50", 0.30),
    ("^GSPTSE", "TSX", 0.20),
]

RULES = [
    "Papel de 100.000 euros al inicio, en diez partes iguales. Sin comisiones y sin impuestos. No es dinero real.",
    "El universo es el de Calidad: bolsa de origen, ROE por encima del 8% y margen neto por encima del 4%.",
    "Se eligen 10 nombres con la puntuación publicada. Máximo dos por sector. Se buscan al menos cuatro de EEUU, tres de Europa y uno de Canadá si pasan de 55 puntos.",
    "Cada día laborable, hora de Madrid, hay como mucho un cambio. Se vende la peor posición solo si una de fuera la supera en 8 puntos o más y respeta el cupo de sector.",
    "Si el índice de miedo de CNN está por debajo de 25, no se vende nada que siga en 45 puntos o más.",
    "La referencia es 50% S&P 500, 30% Euro Stoxx 50 y 20% TSX, pasados a euros con el cambio del día. Los festivos no se descuentan.",
]


def _now() -> datetime:
    return datetime.now(MADRID)


def _load() -> dict | None:
    if not PATH.exists():
        return None
    return json.loads(PATH.read_text(encoding="utf-8"))


def _save(book: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")


def _quotes(symbols: list[str]) -> dict[str, dict]:
    raw = spark(symbols, range_="5d", interval="1d")
    found = {}
    for symbol in symbols:
        hit = raw.get(symbol.upper())
        if not hit or not hit["points"]:
            continue
        meta = hit["meta"]
        price = meta.get("regularMarketPrice") or hit["points"][-1]["c"]
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        found[symbol.upper()] = {
            "price": float(price),
            "currency": meta.get("currency") or "USD",
            "name": meta.get("shortName") or meta.get("longName") or symbol,
        }
    return found


def _fx_from(quotes: dict[str, dict]) -> dict[str, float]:
    prices = {}
    for code, symbol in FX_SYMBOLS.items():
        hit = quotes.get(symbol.upper())
        if not hit:
            raise RuntimeError(f"Sin cambio {symbol}")
        prices[code] = hit["price"]
    return prices


def _need_quotes(extra: list[str]) -> dict[str, dict]:
    symbols = list(dict.fromkeys([*FX_SYMBOLS.values(), *[row[0] for row in BENCH], *extra]))
    return _quotes(symbols)


def _unit(currency: str, price: float) -> tuple[str, float]:
    if currency in ("GBp", "GBX"):
        return "GBP", price / 100.0
    return currency or "USD", price


def _to_eur(amount_local: float, currency: str, fx: dict[str, float]) -> float:
    code, amount = _unit(currency, amount_local)
    if code == "EUR":
        return amount
    rate = fx.get(code)
    if not rate:
        raise RuntimeError(f"Sin cambio a euros para {code}")
    return amount / rate


def _shares_for(eur: float, price: float, currency: str, fx: dict[str, float]) -> float:
    code, unit_price = _unit(currency, price)
    if unit_price <= 0:
        raise RuntimeError("Precio no válido")
    if code == "EUR":
        local = eur
    else:
        local = eur * fx[code]
    shares = local / unit_price
    if currency in ("GBp", "GBX"):
        return shares
    return shares


def _position_value(holding: dict, quote: dict, fx: dict[str, float]) -> float:
    return _to_eur(holding["shares"] * quote["price"], quote["currency"], fx)


def _select(rows: list[dict]) -> list[dict]:
    scored = [row for row in rows if row.get("score") is not None]
    picked: list[dict] = []
    sectors: dict[str, int] = {}

    def take(row: dict, sector_cap: int) -> bool:
        if any(item["symbol"] == row["symbol"] for item in picked):
            return False
        sector = row.get("sector") or "Otros"
        if sectors.get(sector, 0) >= sector_cap:
            return False
        picked.append(row)
        sectors[sector] = sectors.get(sector, 0) + 1
        return True

    quotas = (("us", 4), ("eu", 3), ("ca", 1))
    for group, count in quotas:
        got = 0
        for row in scored:
            if row.get("group") != group or row["score"] < 55:
                continue
            if take(row, 2):
                got += 1
            if got >= count:
                break
    for row in scored:
        if len(picked) >= 10:
            break
        if row["score"] < 50:
            continue
        take(row, 2)
    for row in scored:
        if len(picked) >= 10:
            break
        take(row, 3)
    for row in scored:
        if len(picked) >= 10:
            break
        if any(item["symbol"] == row["symbol"] for item in picked):
            continue
        picked.append(row)
    return picked[:10]


def _holding_from(row: dict, eur: float, fx: dict[str, float], quote: dict) -> dict:
    shares = _shares_for(eur, quote["price"], quote["currency"], fx)
    return {
        "symbol": row["symbol"],
        "name": row.get("name") or quote["name"],
        "sector": row.get("sector") or "",
        "sector_label": row.get("sector_label") or row.get("sector") or "—",
        "group": row.get("group") or "",
        "region_label": row.get("region_label") or "",
        "shares": shares,
        "currency": quote["currency"],
        "cost_eur": eur,
        "entry_price": quote["price"],
        "score": row.get("score"),
    }


def _lookup_score(symbol: str, universe: list[dict]) -> dict | None:
    for row in universe:
        if row["symbol"] == symbol:
            return row
    return None


def _worst(holdings: list[dict], universe: list[dict]) -> tuple[dict, float]:
    worst = holdings[0]
    worst_score = 10_000.0
    for holding in holdings:
        row = _lookup_score(holding["symbol"], universe)
        score = row["score"] if row else 40.0
        holding["score"] = score
        if score < worst_score:
            worst = holding
            worst_score = score
    return worst, worst_score


def _candidate(holdings: list[dict], universe: list[dict], worst_symbol: str) -> dict | None:
    held = {item["symbol"] for item in holdings}
    sectors: dict[str, int] = {}
    for holding in holdings:
        if holding["symbol"] == worst_symbol:
            continue
        sectors[holding.get("sector") or ""] = sectors.get(holding.get("sector") or "", 0) + 1
    for row in universe:
        if row["symbol"] in held:
            continue
        sector = row.get("sector") or ""
        if sectors.get(sector, 0) >= 2:
            continue
        return row
    return None


def _bench_levels(quotes: dict[str, dict], fx: dict[str, float]) -> dict[str, float]:
    levels = {}
    for symbol, _name, _weight in BENCH:
        quote = quotes.get(symbol.upper())
        if not quote:
            raise RuntimeError(f"Sin índice {symbol}")
        levels[symbol] = _to_eur(quote["price"], quote["currency"], fx)
    return levels


def _blend(levels: dict[str, float], base: dict[str, float]) -> float:
    total = 0.0
    for symbol, _name, weight in BENCH:
        total += weight * (levels[symbol] / base[symbol])
    return total * 100


def _mark(book: dict, quotes: dict[str, dict], fx: dict[str, float]) -> dict:
    value = 0.0
    lines = []
    for holding in book["holdings"]:
        quote = quotes.get(holding["symbol"].upper())
        if not quote:
            raise RuntimeError(f"Sin precio de {holding['symbol']}")
        holding["currency"] = quote["currency"]
        worth = _position_value(holding, quote, fx)
        value += worth
        gain = None if not holding.get("cost_eur") else (worth / holding["cost_eur"] - 1) * 100
        day = None
        lines.append(
            {
                **holding,
                "price": quote["price"],
                "value_eur": round(worth, 2),
                "weight": None,
                "gain_pct": round(gain, 2) if gain is not None else None,
                "day_pct": day,
            }
        )
    for line in lines:
        line["weight"] = round(line["value_eur"] / value * 100, 1) if value else None
    levels = _bench_levels(quotes, fx)
    base = book["benchmark_eur"]
    curve_point = {
        "date": _now().date().isoformat(),
        "value_eur": round(value, 2),
        "portfolio": round(value / BASE_EUR * 100, 2),
        "blend": round(_blend(levels, base), 2),
        "spx": round(levels["^GSPC"] / base["^GSPC"] * 100, 2),
        "stoxx": round(levels["^STOXX50E"] / base["^STOXX50E"] * 100, 2),
        "tsx": round(levels["^GSPTSE"] / base["^GSPTSE"] * 100, 2),
    }
    previous = next((point for point in reversed(book["curve"]) if point["date"] != curve_point["date"]), None)
    if previous and previous.get("value_eur"):
        curve_point["day_pct"] = round((value / previous["value_eur"] - 1) * 100, 2)
    else:
        curve_point["day_pct"] = 0.0
    if book["curve"] and book["curve"][-1]["date"] == curve_point["date"]:
        book["curve"][-1] = curve_point
    else:
        book["curve"].append(curve_point)
    book["last_value_eur"] = curve_point["value_eur"]
    return {"lines": lines, "point": curve_point, "levels": levels}


def _decide(book: dict, universe: list[dict], fear: dict, quotes: dict[str, dict], fx: dict[str, float]) -> dict:
    today = _now().date().isoformat()
    if any(row["date"] == today for row in book["decisions"]):
        return book["decisions"][-1]
    weekend = _now().weekday() >= 5
    if weekend:
        decision = {
            "date": today,
            "action": "mantener",
            "sold": None,
            "bought": None,
            "reason": "Fin de semana. La regla no cambia la cartera.",
        }
        book["decisions"].append(decision)
        return decision
    worst, worst_score = _worst(book["holdings"], universe)
    outsider = _candidate(book["holdings"], universe, worst["symbol"])
    fear_score = fear.get("score")
    blocked = fear_score is not None and fear_score < 25 and worst_score >= 45
    gap = (outsider["score"] - worst_score) if outsider else None
    if outsider and gap is not None and gap >= 8 and not blocked:
        quote = quotes.get(worst["symbol"].upper())
        if not quote:
            raise RuntimeError(f"Sin precio de {worst['symbol']}")
        outsider_quote = quotes.get(outsider["symbol"].upper())
        if not outsider_quote:
            extra = _quotes([outsider["symbol"]])
            outsider_quote = extra.get(outsider["symbol"].upper())
            quotes.update(extra)
        if not outsider_quote:
            raise RuntimeError(f"Sin precio de {outsider['symbol']}")
        proceeds = _position_value(worst, quote, fx)
        newbie = _holding_from(outsider, proceeds, fx, outsider_quote)
        book["holdings"] = [item for item in book["holdings"] if item["symbol"] != worst["symbol"]]
        book["holdings"].append(newbie)
        decision = {
            "date": today,
            "action": "cambiar",
            "sold": {"symbol": worst["symbol"], "name": worst["name"], "score": worst_score},
            "bought": {"symbol": newbie["symbol"], "name": newbie["name"], "score": outsider["score"]},
            "reason": (
                f"Se vende {worst['name']} ({worst['symbol']}, {worst_score:.0f} puntos) y se compra "
                f"{newbie['name']} ({newbie['symbol']}, {outsider['score']:.0f}). "
                f"La diferencia es de {gap:.0f} puntos, por encima de los 8 que exige la regla, "
                f"y el sector admite el hueco."
            ),
        }
    else:
        if blocked and outsider and gap is not None and gap >= 8:
            reason = (
                f"Se mantiene. {outsider['name']} supera a {worst['name']} "
                f"({outsider['score']:.0f} frente a {worst_score:.0f}), pero el miedo de CNN está en "
                f"{fear_score:.0f} y la posición sigue en {worst_score:.0f} puntos. En pánico no se vende."
            )
        elif outsider:
            reason = (
                f"Se mantiene. La mejor idea de fuera es {outsider['name']} "
                f"({outsider['score']:.0f}) y la peor posición es {worst['name']} ({worst_score:.0f}). "
                "No hay 8 puntos de diferencia, o el cupo de sector no deja el cambio."
            )
        else:
            reason = "Se mantiene. No hay un nombre de fuera que respete el cupo de sector."
        decision = {
            "date": today,
            "action": "mantener",
            "sold": None,
            "bought": None,
            "reason": reason,
        }
    book["decisions"].append(decision)
    return decision


def _open_book(rows: list[dict], quotes: dict[str, dict], fx: dict[str, float]) -> tuple[dict, dict[str, dict]]:
    picked = _select(rows)
    if len(picked) < 8:
        raise RuntimeError("No hay bastantes empresas con puntuación para abrir la cartera")
    missing = [row["symbol"] for row in picked if row["symbol"].upper() not in quotes]
    if missing:
        quotes = {**quotes, **_quotes(missing)}
    each = BASE_EUR / len(picked)
    holdings = []
    for row in picked:
        quote = quotes.get(row["symbol"].upper())
        if not quote:
            raise RuntimeError(f"Sin precio de {row['symbol']}")
        holdings.append(_holding_from(row, each, fx, quote))
    base = _bench_levels(quotes, fx)
    today = _now().date().isoformat()
    names = ", ".join(item["symbol"] for item in holdings)
    book = {
        "inception": today,
        "base_eur": BASE_EUR,
        "disclaimer": "Cartera de papel con reglas fijas. No es una recomendación de inversión ni una invitación a comprar o vender.",
        "rules": RULES,
        "holdings": holdings,
        "decisions": [
            {
                "date": today,
                "action": "abrir",
                "sold": None,
                "bought": None,
                "reason": f"Cartera inicial de {len(holdings)} nombres por puntuación y cupos: {names}.",
            }
        ],
        "curve": [],
        "benchmark_eur": base,
    }
    return book, quotes


def view() -> dict:
    with _lock:
        universe = quality_universe()
        rows = universe.get("items") or []
        book = _load()
        symbols = [row["symbol"] for row in (book["holdings"] if book else rows[:12])]
        quotes = _need_quotes(symbols)
        fx = _fx_from(quotes)
        if book is None:
            book, quotes = _open_book(rows, quotes, fx)
        fear = {}
        try:
            fear = fear_greed()
        except Exception as exc:  # noqa: BLE001
            fear = {"score": None, "label": "sin dato", "error": str(exc)}
        decision = _decide(book, rows, fear, quotes, fx)
        marked = _mark(book, quotes, fx)
        book["updated"] = datetime.now(timezone.utc).isoformat()
        _save(book)
        point = marked["point"]
        for line in marked["lines"]:
            row = _lookup_score(line["symbol"], rows)
            if row:
                line["score"] = row["score"]
                line["pe"] = row.get("pe")
                line["dividend_yield"] = row.get("dividend_yield")
                line["change_pct"] = row.get("change_pct")
        return {
            "asof": book["updated"],
            "inception": book["inception"],
            "base_eur": BASE_EUR,
            "disclaimer": book["disclaimer"],
            "rules": book["rules"],
            "value_eur": point["value_eur"],
            "day_pct": point["day_pct"],
            "portfolio_index": point["portfolio"],
            "blend_index": point["blend"],
            "vs_blend": round(point["portfolio"] - point["blend"], 2),
            "decision": decision,
            "fear": {"score": fear.get("score"), "label": fear.get("label")},
            "holdings": marked["lines"],
            "curve": book["curve"][-180:],
            "benchmarks": {
                "spx": point["spx"],
                "stoxx": point["stoxx"],
                "tsx": point["tsx"],
                "blend": point["blend"],
            },
            "stale": False,
            "error": universe.get("error"),
        }


def summary() -> dict:
    try:
        full = view()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "value_eur": None}
    return {
        "value_eur": full["value_eur"],
        "day_pct": full["day_pct"],
        "vs_blend": full["vs_blend"],
        "portfolio_index": full["portfolio_index"],
        "blend_index": full["blend_index"],
        "decision": full["decision"],
        "inception": full["inception"],
        "holdings": [
            {"symbol": row["symbol"], "name": row["name"], "weight": row["weight"], "gain_pct": row["gain_pct"]}
            for row in full["holdings"]
        ],
    }
