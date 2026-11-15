"""Índices, termómetro, sentimiento, noticias, resultados y ficha."""

from __future__ import annotations

import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from ibex.cache import remember
from ibex.yahoo import chart, get_bytes, get_json, post_json, quote_summary, raw_number, spark

SESSIONS = {
    "us": ("America/New_York", 9 * 60 + 30, 16 * 60),
    "ca": ("America/Toronto", 9 * 60 + 30, 16 * 60),
    "london": ("Europe/London", 8 * 60, 16 * 60 + 30),
    "eu": ("Europe/Madrid", 9 * 60, 17 * 60 + 30),
    "zurich": ("Europe/Zurich", 9 * 60, 17 * 60 + 20),
    "tokyo": ("Asia/Tokyo", 9 * 60, 15 * 60),
    "hk": ("Asia/Hong_Kong", 9 * 60 + 30, 16 * 60),
    "shanghai": ("Asia/Shanghai", 9 * 60 + 30, 15 * 60),
    "seoul": ("Asia/Seoul", 9 * 60, 15 * 60 + 30),
    "sydney": ("Australia/Sydney", 10 * 60, 16 * 60),
    "india": ("Asia/Kolkata", 9 * 60 + 15, 15 * 60 + 30),
}

# symbol, código corto, nombre, zona, sesión
INDICES = [
    ("^GSPC", "SPX", "S&P 500", "América", "us"),
    ("^DJI", "DJI", "Dow Jones", "América", "us"),
    ("^IXIC", "NDX", "Nasdaq Composite", "América", "us"),
    ("^RUT", "RUT", "Russell 2000", "América", "us"),
    ("^GSPTSE", "TSX", "TSX", "América", "ca"),
    ("^MXX", "IPC", "IPC México", "América", "us"),
    ("^BVSP", "IBOV", "Bovespa", "América", "us"),
    ("^IBEX", "IBEX", "IBEX 35", "Europa", "eu"),
    ("^STOXX50E", "SX5E", "Euro Stoxx 50", "Europa", "eu"),
    ("^GDAXI", "DAX", "DAX", "Europa", "eu"),
    ("^FCHI", "CAC", "CAC 40", "Europa", "eu"),
    ("^FTSE", "FTSE", "FTSE 100", "Europa", "london"),
    ("FTSEMIB.MI", "MIB", "FTSE MIB", "Europa", "eu"),
    ("^AEX", "AEX", "AEX", "Europa", "eu"),
    ("^SSMI", "SMI", "SMI", "Europa", "zurich"),
    ("^OMX", "OMX", "OMX Estocolmo", "Europa", "eu"),
    ("^N225", "NKY", "Nikkei 225", "Asia-Pacífico", "tokyo"),
    ("^HSI", "HSI", "Hang Seng", "Asia-Pacífico", "hk"),
    ("000001.SS", "SHCOMP", "Shanghái", "Asia-Pacífico", "shanghai"),
    ("^KS11", "KOSPI", "KOSPI", "Asia-Pacífico", "seoul"),
    ("^AXJO", "ASX", "ASX 200", "Asia-Pacífico", "sydney"),
    ("^BSESN", "SENSEX", "Sensex", "Asia-Pacífico", "india"),
    ("^TWII", "TWSE", "Taiex", "Asia-Pacífico", "hk"),
    ("^NSEI", "NIFTY", "Nifty 50", "Asia-Pacífico", "india"),
]

REFERENCES = [
    ("^VIX", "VIX", "Volatilidad VIX", "Referencias", "us"),
    ("^TNX", "US10Y", "Bono EEUU 10 años", "Referencias", "us"),
    ("^IRX", "US3M", "Letras EEUU 3 meses", "Referencias", "us"),
    ("^TYX", "US30Y", "Bono EEUU 30 años", "Referencias", "us"),
    ("DX-Y.NYB", "DXY", "Índice dólar", "Referencias", "us"),
    ("EURUSD=X", "EURUSD", "Euro / dólar", "Referencias", "eu"),
    ("GC=F", "ORO", "Oro", "Referencias", "us"),
    ("BZ=F", "BRENT", "Brent", "Referencias", "eu"),
    ("CL=F", "WTI", "WTI", "Referencias", "us"),
]

SECTORS = [
    ("XLK", "Tecnología"),
    ("XLC", "Comunicación"),
    ("XLY", "Consumo cíclico"),
    ("XLP", "Consumo básico"),
    ("XLF", "Finanzas"),
    ("XLI", "Industria"),
    ("XLE", "Energía"),
    ("XLB", "Materiales"),
    ("XLV", "Salud"),
    ("XLRE", "Inmobiliario"),
    ("XLU", "Servicios públicos"),
]

FEEDS = [
    ("mercado", "Mercado", "https://news.google.com/rss/search?q=bolsa+OR+mercados+OR+IBEX+OR+%22Wall+Street%22&hl=es&gl=ES&ceid=ES:es"),
    ("eeuu", "EEUU", "https://news.google.com/rss/search?q=%22Wall+Street%22+OR+%22S%26P+500%22+OR+Nasdaq+OR+Fed&hl=es&gl=ES&ceid=ES:es"),
    ("europa", "Europa", "https://news.google.com/rss/search?q=IBEX+OR+DAX+OR+%22Euro+Stoxx%22+OR+%22bolsa+europea%22&hl=es&gl=ES&ceid=ES:es"),
    ("resultados", "Resultados", "https://news.google.com/rss/search?q=%22presenta+resultados%22+OR+%22resultados+empresariales%22+OR+%22beneficio+neto%22&hl=es&gl=ES&ceid=ES:es"),
    ("dividendos", "Dividendos", "https://news.google.com/rss/search?q=dividendo+OR+%22recompra+de+acciones%22+OR+%22pay+out%22&hl=es&gl=ES&ceid=ES:es"),
]

RATING_ES = {
    "extreme fear": "pánico",
    "fear": "miedo",
    "neutral": "neutro",
    "greed": "codicia",
    "extreme greed": "euforia",
}


def session_state(key: str, now: datetime) -> str:
    zone_name, open_m, close_m = SESSIONS[key]
    local = now.astimezone(ZoneInfo(zone_name))
    if local.weekday() >= 5:
        return "cerrado"
    minutes = local.hour * 60 + local.minute
    if open_m <= minutes < close_m:
        return "abierto"
    return "cerrado"


def sessions(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    labels = [
        ("us", "Nueva York"),
        ("ca", "Toronto"),
        ("london", "Londres"),
        ("eu", "Madrid"),
        ("tokyo", "Tokio"),
    ]
    rows = []
    for key, label in labels:
        zone = ZoneInfo(SESSIONS[key][0])
        local = now.astimezone(zone)
        rows.append(
            {
                "id": key,
                "label": label,
                "state": session_state(key, now),
                "clock": local.strftime("%H:%M"),
            }
        )
    return rows


def _pct(last: float | None, prev: float | None) -> float | None:
    if last is None or prev in (None, 0):
        return None
    return (last / prev - 1) * 100


def _yield_points(symbol: str, price: float | None) -> float | None:
    if price is None:
        return None
    if symbol in ("^TNX", "^IRX", "^TYX", "^FVX") and price > 20:
        return price / 10
    return price


def indices() -> dict:
    def build():
        now = datetime.now(timezone.utc)
        book = INDICES + REFERENCES
        raw = spark([row[0] for row in book], range_="1mo", interval="1d")
        rows = []
        missing = []
        for symbol, code, name, zone, session in book:
            hit = raw.get(symbol.upper())
            if not hit or not hit["points"]:
                missing.append(symbol)
                continue
            points = hit["points"]
            meta = hit["meta"]
            last = points[-1]["c"]
            prev = points[-2]["c"] if len(points) > 1 else None
            month = points[0]["c"] if len(points) > 1 else None
            price = _yield_points(symbol, last)
            rows.append(
                {
                    "symbol": symbol,
                    "code": code,
                    "name": name,
                    "zone": zone,
                    "session": session_state(session, now) if session in SESSIONS else None,
                    "price": price,
                    "currency": (meta.get("currency") or ""),
                    "change_pct": _pct(last, prev),
                    "month_pct": _pct(last, month),
                    "spark": [point["c"] for point in points][-22:],
                }
            )
        return {
            "asof": now.isoformat(),
            "source": "Yahoo Finance",
            "note": "Cotizaciones diferidas. El bono a 10 años se muestra en porcentaje de rentabilidad, no en precio.",
            "sessions": sessions(now),
            "items": rows,
            "missing": missing,
            "stale": False,
            "error": None if rows else "Sin índices",
        }

    return remember("indices", 60, build)


def _breadth() -> dict | None:
    from ibex.screen import listed_us, region_clause, _gte, _gt, _lt

    up_ops = [region_clause("us"), listed_us(), _gte("intradaymarketcap", 5_000_000_000), _gt("percentchange", 0)]
    down_ops = [region_clause("us"), listed_us(), _gte("intradaymarketcap", 5_000_000_000), _lt("percentchange", 0)]
    from ibex.yahoo import visualize

    _up, up_total = visualize({"operator": "AND", "operands": up_ops}, ["ticker"], "intradaymarketcap", "DESC", 1)
    _down, down_total = visualize({"operator": "AND", "operands": down_ops}, ["ticker"], "intradaymarketcap", "DESC", 1)
    total = up_total + down_total
    if total <= 0:
        return None
    return {"up": up_total, "down": down_total, "pct_up": up_total / total * 100}


def fear_greed() -> dict:
    def build():
        payload = get_json(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            timeout=20,
            headers={"Referer": "https://edition.cnn.com/markets/fear-and-greed"},
        )
        block = payload.get("fear_and_greed") or {}
        score = block.get("score")
        rating = str(block.get("rating") or "").lower()
        return {
            "score": round(float(score), 1) if isinstance(score, (int, float)) else None,
            "rating": rating,
            "label": RATING_ES.get(rating, rating or "sin dato"),
            "asof": block.get("timestamp"),
            "previous": {
                "cierre": block.get("previous_close"),
                "semana": block.get("previous_1_week"),
                "mes": block.get("previous_1_month"),
                "año": block.get("previous_1_year"),
            },
            "source": "CNN Fear & Greed",
        }

    return remember("fear-greed", 15 * 60, build)


def _vix_score(price: float | None) -> float | None:
    if price is None:
        return None
    if price <= 12:
        return 85
    if price >= 40:
        return 8
    # 12 → 85, 20 → 50, 32 → 20
    return max(8, min(85, 85 - (price - 12) * (65 / 20)))


def _day_score(change: float | None) -> float | None:
    if change is None:
        return None
    return max(5, min(95, 50 + change * 18))


def thermometer() -> dict:
    def build():
        board = indices()
        fear = fear_greed()
        try:
            breadth = _breadth()
        except Exception as exc:  # noqa: BLE001
            breadth = None
            breadth_error = str(exc)
        else:
            breadth_error = None
        by_symbol = {row["symbol"]: row for row in board["items"]}
        vix = (by_symbol.get("^VIX") or {}).get("price")
        tnx = (by_symbol.get("^TNX") or {}).get("price")
        irx = (by_symbol.get("^IRX") or {}).get("price")
        curve = None if tnx is None or irx is None else tnx - irx
        focus = ["^GSPC", "^IXIC", "^GSPTSE", "^STOXX50E", "^GDAXI", "^IBEX", "^FTSE"]
        changes = [by_symbol[symbol]["change_pct"] for symbol in focus if symbol in by_symbol and by_symbol[symbol]["change_pct"] is not None]
        day = sum(changes) / len(changes) if changes else None
        parts = []
        if fear.get("score") is not None:
            parts.append(("Miedo y codicia", fear["score"], 0.35))
        if breadth:
            parts.append(("Amplitud EEUU", breadth["pct_up"], 0.25))
        vix_s = _vix_score(vix)
        if vix_s is not None:
            parts.append(("Volatilidad", vix_s, 0.2))
        day_s = _day_score(day)
        if day_s is not None:
            parts.append(("Sesgo del día", day_s, 0.2))
        weight = sum(part[2] for part in parts) or 1
        temperature = round(sum(value * w for _, value, w in parts) / weight, 1) if parts else None
        if temperature is None:
            label = "sin dato"
        elif temperature < 25:
            label = "pánico"
        elif temperature < 40:
            label = "miedo"
        elif temperature < 60:
            label = "neutro"
        elif temperature < 75:
            label = "codicia"
        else:
            label = "euforia"
        sector_raw = spark([row[0] for row in SECTORS], range_="5d", interval="1d")
        sectors = []
        for symbol, name in SECTORS:
            hit = sector_raw.get(symbol.upper())
            if not hit or len(hit["points"]) < 2:
                continue
            last = hit["points"][-1]["c"]
            prev = hit["points"][-2]["c"]
            sectors.append({"symbol": symbol, "name": name, "change_pct": _pct(last, prev)})
        sectors.sort(key=lambda row: row["change_pct"] or -999, reverse=True)
        return {
            "asof": datetime.now(timezone.utc).isoformat(),
            "temperature": temperature,
            "label": label,
            "parts": [{"name": name, "score": round(value, 1), "weight": weight_} for name, value, weight_ in parts],
            "fear": fear,
            "breadth": breadth,
            "breadth_error": breadth_error,
            "vix": vix,
            "us10y": tnx,
            "us3m": irx,
            "curve": curve,
            "day_change": day,
            "dollar": (by_symbol.get("DX-Y.NYB") or {}).get("change_pct"),
            "gold": (by_symbol.get("GC=F") or {}).get("change_pct"),
            "brent": (by_symbol.get("BZ=F") or {}).get("change_pct"),
            "sectors": sectors,
            "sessions": board["sessions"],
            "note": (
                "La temperatura mezcla el índice de miedo y codicia de CNN, "
                "el porcentaje de grandes valores de EEUU que suben hoy, el VIX y el promedio del día en siete índices. "
                "50 es neutro. No es una señal de compra ni de venta."
            ),
            "stale": False,
            "error": None,
        }

    return remember("termometro", 120, build)


def sentiment() -> dict:
    def build():
        thermo = thermometer()
        vix_chart = []
        try:
            block = chart("^VIX", range_="6mo", interval="1d")
            vix_chart = [point["c"] for point in block["points"]]
        except Exception:
            vix_chart = []
        return {
            "asof": thermo["asof"],
            "temperature": thermo["temperature"],
            "label": thermo["label"],
            "fear": thermo["fear"],
            "breadth": thermo["breadth"],
            "vix": thermo["vix"],
            "vix_spark": vix_chart[-90:],
            "curve": thermo["curve"],
            "us10y": thermo["us10y"],
            "day_change": thermo["day_change"],
            "parts": thermo["parts"],
            "note": thermo["note"],
            "stale": False,
            "error": None,
        }

    return remember("sentimiento", 120, build)


def _parse_feed(xml_bytes: bytes, section: str, title: str, limit: int = 12) -> dict:
    root = ElementTree.fromstring(xml_bytes)
    items = []
    seen = set()
    for node in root.findall(".//item"):
        raw_title = html.unescape((node.findtext("title") or "")).strip()
        raw_title = re.sub(r"<[^>]+>", "", raw_title)
        link = (node.findtext("link") or "").strip()
        source_el = node.find("source")
        source = html.unescape(source_el.text).strip() if source_el is not None and source_el.text else ""
        if source and raw_title.endswith(" - " + source):
            raw_title = raw_title[: -(len(source) + 3)].strip()
        elif not source and " - " in raw_title:
            raw_title, source = raw_title.rsplit(" - ", 1)
            raw_title = raw_title.strip()
            source = source.strip()
        key = raw_title.casefold()
        if not raw_title or key in seen or not link.startswith("http"):
            continue
        seen.add(key)
        published = None
        pub_raw = node.findtext("pubDate")
        if pub_raw:
            try:
                published = parsedate_to_datetime(pub_raw).isoformat()
            except (TypeError, ValueError, OverflowError):
                published = None
        items.append({"title": raw_title, "source": source or "Google News", "url": link, "published": published})
        if len(items) >= limit:
            break
    return {"id": section, "title": title, "items": items}


def news() -> dict:
    def build():
        sections = []
        errors = []

        def one(feed):
            section, title, url = feed
            try:
                return _parse_feed(get_bytes(url, timeout=18), section, title), None
            except Exception as exc:  # noqa: BLE001
                return {"id": section, "title": title, "items": []}, f"{title}: {exc}"

        with ThreadPoolExecutor(max_workers=5) as pool:
            for section, error in pool.map(one, FEEDS):
                sections.append(section)
                if error:
                    errors.append(error)
        order = {feed[0]: index for index, feed in enumerate(FEEDS)}
        sections.sort(key=lambda section: order.get(section["id"], 99))
        return {
            "asof": datetime.now(timezone.utc).isoformat(),
            "source": "Google News",
            "note": "Titulares en español agregados por Google News. Abre la fuente original.",
            "sections": sections,
            "warnings": errors,
            "stale": False,
            "error": None if any(section["items"] for section in sections) else "; ".join(errors),
        }

    return remember("noticias", 5 * 60, build)


def company_news(query: str) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + re.sub(r"\s+", "+", query.strip())
        + "+when:14d&hl=es&gl=ES&ceid=ES:es"
    )
    try:
        parsed = _parse_feed(get_bytes(url, timeout=15), "empresa", query, limit=8)
        return parsed["items"]
    except Exception:
        return []


def _earnings_region(region: str, cap: float, start: str, end: str) -> list[dict]:
    body = {
        "sortType": "DESC",
        "entityIdType": "sp_earnings",
        "sortField": "intradaymarketcap",
        "includeFields": [
            "ticker",
            "companyshortname",
            "intradaymarketcap",
            "startdatetime",
            "startdatetimetype",
            "epsestimate",
            "epsactual",
            "epssurprisepct",
        ],
        "size": 100,
        "offset": 0,
        "query": {
            "operator": "AND",
            "operands": [
                {"operator": "EQ", "operands": ["region", region]},
                {
                    "operator": "OR",
                    "operands": [
                        {"operator": "EQ", "operands": ["eventtype", "EAD"]},
                        {"operator": "EQ", "operands": ["eventtype", "ERA"]},
                    ],
                },
                {"operator": "GTE", "operands": ["startdatetime", start]},
                {"operator": "LTE", "operands": ["startdatetime", end]},
                {"operator": "GTE", "operands": ["intradaymarketcap", cap]},
            ],
        },
    }
    data = post_json("https://query1.finance.yahoo.com/v1/finance/visualization?lang=en-US&region=US", body)
    finance = data.get("finance") or {}
    if finance.get("error"):
        raise RuntimeError(str(finance["error"]))
    result = (finance.get("result") or [None])[0] or {}
    documents = result.get("documents") or []
    rows = (documents[0].get("rows") if documents else None) or []
    items = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        symbol = str(row[0] or "").upper()
        if not symbol:
            continue
        when_raw = str(row[3] or "")
        try:
            when_dt = datetime.fromisoformat(when_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        timing = str(row[4] or "TNS").upper()
        if timing not in ("BMO", "AMC", "TNS"):
            timing = "TNS"
        actual = raw_number(row[6]) if len(row) > 6 else None
        surprise = raw_number(row[7]) if len(row) > 7 and actual is not None else None
        items.append(
            {
                "symbol": symbol,
                "name": str(row[1] or symbol),
                "region": region,
                "market_cap": raw_number(row[2]),
                "date": when_dt.date().isoformat(),
                "session": timing,
                "eps_estimate": raw_number(row[5]) if len(row) > 5 else None,
                "eps_actual": actual,
                "surprise_pct": surprise,
            }
        )
    return items


def _dedupe_earnings(items: list[dict]) -> list[dict]:
    """Una fila por empresa y día. Fuera las cotizaciones numeradas y el mercado abierto."""
    from ibex.screen import _name_key

    kept = []
    for item in items:
        symbol = item.get("symbol") or ""
        if not symbol or symbol[0].isdigit() or symbol.endswith((".F", ".XC", ".IL", ".SG", ".MU", ".DU", ".HA", ".HM", ".NE")):
            continue
        kept.append(item)
    groups: dict[tuple, list[dict]] = {}
    for item in kept:
        groups.setdefault((_name_key(item.get("name") or ""), item["date"]), []).append(item)

    def rank(item: dict) -> tuple:
        symbol = item["symbol"]
        home = 0 if "." not in symbol else 1
        return (home, -(item.get("market_cap") or 0))

    chosen = []
    for peers in groups.values():
        peers.sort(key=rank)
        chosen.append(peers[0])
    return chosen


def earnings() -> dict:
    def build():
        ny = datetime.now(ZoneInfo("America/New_York")).date()
        start = (ny - timedelta(days=1)).isoformat()
        end = (ny + timedelta(days=21)).isoformat()
        regions = [
            ("us", 8_000_000_000),
            ("ca", 3_000_000_000),
            ("gb", 3_000_000_000),
            ("de", 3_000_000_000),
            ("fr", 3_000_000_000),
            ("es", 2_000_000_000),
            ("nl", 3_000_000_000),
            ("ch", 3_000_000_000),
            ("it", 2_000_000_000),
            ("se", 2_000_000_000),
        ]
        items = []
        errors = []
        seen = set()
        for region, cap in regions:
            try:
                batch = _earnings_region(region, cap, start, end)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{region}: {exc}")
                continue
            for item in batch:
                key = (item["symbol"], item["date"])
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
        session_rank = {"BMO": 0, "TNS": 1, "AMC": 2}
        items = _dedupe_earnings(items)
        items.sort(key=lambda item: (item["date"], session_rank[item["session"]], -(item["market_cap"] or 0)))
        return {
            "asof": datetime.now(timezone.utc).isoformat(),
            "source": "Yahoo Finance",
            "start": start,
            "end": end,
            "note": (
                "Presentaciones de resultados de las próximas tres semanas en EEUU, Canadá y las plazas grandes de Europa. "
                "Antes de abrir, tras el cierre, o sin hora. El consenso de beneficio es el de Yahoo, no un análisis de esta web."
            ),
            "items": items,
            "warnings": errors,
            "stale": False,
            "error": None if items else "; ".join(errors) or "Sin calendario",
        }

    return remember("resultados-v2", 3 * 3600, build)


def _pct_fraction(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100


def _trend_rows(summary: dict) -> list[dict]:
    trend = ((summary.get("earningsTrend") or {}).get("trend")) or []
    labels = {"0q": "Trimestre en curso", "+1q": "Próximo trimestre", "0y": "Año en curso", "+1y": "Año siguiente"}
    rows = []
    for item in trend:
        period = item.get("period")
        if period not in labels:
            continue
        earnings = item.get("earningsEstimate") or {}
        revenue = item.get("revenueEstimate") or {}
        rows.append(
            {
                "period": labels[period],
                "end": item.get("endDate"),
                "eps": raw_number(earnings.get("avg")),
                "eps_year_ago": raw_number(earnings.get("yearAgoEps")),
                "eps_growth": _pct_fraction(raw_number(item.get("growth"))),
                "revenue": raw_number(revenue.get("avg")),
                "revenue_growth": _pct_fraction(raw_number(revenue.get("growth"))),
                "analysts": earnings.get("numberOfAnalysts"),
            }
        )
    return rows


def _reco(summary: dict) -> dict | None:
    trend = ((summary.get("recommendationTrend") or {}).get("trend")) or []
    if not trend:
        return None
    latest = trend[0]
    return {
        "period": latest.get("period"),
        "strong_buy": latest.get("strongBuy"),
        "buy": latest.get("buy"),
        "hold": latest.get("hold"),
        "sell": latest.get("sell"),
        "strong_sell": latest.get("strongSell"),
    }


def _earnings_when(values) -> str | None:
    if not values:
        return None
    first = values[0]
    if isinstance(first, dict):
        raw = first.get("raw")
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, timezone.utc).date().isoformat()
        fmt = first.get("fmt")
        return str(fmt) if fmt else None
    if isinstance(first, (int, float)):
        return datetime.fromtimestamp(first, timezone.utc).date().isoformat()
    return str(first) if first else None


def ficha(symbol: str) -> dict:
    symbol = symbol.strip()
    if not symbol or len(symbol) > 24 or not re.fullmatch(r"[A-Za-z0-9.\-=^]+", symbol):
        raise ValueError("Ticker no válido")

    def build():
        drawn = chart(symbol, range_="1y", interval="1d")
        meta = drawn["meta"]
        summary = {}
        summary_error = None
        try:
            summary = quote_summary(symbol)
        except Exception as exc:  # noqa: BLE001
            summary_error = str(exc)
        price = summary.get("price") or {}
        detail = summary.get("summaryDetail") or {}
        financial = summary.get("financialData") or {}
        profile = summary.get("assetProfile") or {}
        stats = summary.get("defaultKeyStatistics") or {}
        calendar = (summary.get("calendarEvents") or {}).get("earnings") or {}
        earnings_date = _earnings_when(calendar.get("earningsDate"))
        roe = raw_number(financial.get("returnOnEquity"))
        margin = raw_number(financial.get("profitMargins"))
        growth = raw_number(financial.get("revenueGrowth"))
        dividend_yield = raw_number(detail.get("dividendYield")) or raw_number(detail.get("trailingAnnualDividendYield"))
        debt = raw_number(financial.get("debtToEquity"))
        if debt is not None and abs(debt) > 10:
            debt = debt / 100
        name = (
            price.get("longName")
            or meta.get("longName")
            or price.get("shortName")
            or meta.get("shortName")
            or symbol
        )
        points = drawn["points"]
        last = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        currency = meta.get("currency") or price.get("currency") or ""
        high = meta.get("fiftyTwoWeekHigh")
        low = meta.get("fiftyTwoWeekLow")
        dividend_rate = raw_number(detail.get("dividendRate"))
        market_cap = raw_number(price.get("marketCap")) or meta.get("marketCap")
        if currency in ("GBp", "GBX"):
            def _pence(value):
                return None if value is None else value / 100.0

            last = _pence(last)
            prev = _pence(prev)
            high = _pence(high)
            low = _pence(low)
            dividend_rate = _pence(dividend_rate)
            points = [{"t": point["t"], "c": point["c"] / 100.0} for point in points]
            currency = "GBP"
        headlines = company_news(str(name))
        return {
            "symbol": meta.get("symbol") or symbol.upper(),
            "name": name,
            "exchange": price.get("exchangeName") or meta.get("exchangeName"),
            "currency": currency,
            "price": last,
            "change_pct": _pct(last, prev),
            "previous_close": prev,
            "fifty_two_high": high,
            "fifty_two_low": low,
            "market_cap": market_cap,
            "pe": raw_number(detail.get("trailingPE")) or raw_number(stats.get("trailingPE")),
            "forward_pe": raw_number(detail.get("forwardPE")) or raw_number(stats.get("forwardPE")),
            "dividend_yield": _pct_fraction(dividend_yield),
            "dividend_rate": dividend_rate,
            "roe": _pct_fraction(roe),
            "margin": _pct_fraction(margin),
            "revenue_growth": _pct_fraction(growth),
            "debt": debt,
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "country": profile.get("country"),
            "summary": profile.get("longBusinessSummary"),
            "earnings_date": earnings_date,
            "trend": _trend_rows(summary),
            "recommendation": _reco(summary),
            "points": points[-180:],
            "news": headlines,
            "summary_error": summary_error,
            "asof": datetime.now(timezone.utc).isoformat(),
            "source": "Yahoo Finance",
            "note": "El consenso de analistas es el recuento de Yahoo. No es una recomendación de Inversor Íbex.",
        }

    return remember(f"ficha-{symbol.upper()}", 5 * 60, build)
