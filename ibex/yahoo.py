"""Llamadas a Yahoo Finance. Cotizaciones diferidas, sin licencia de tiempo real."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
from typing import Any

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}

_lock = threading.Lock()
_state: dict[str, Any] = {"opener": None, "crumb": None}


def get_bytes(url: str, timeout: int = 25, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str, timeout: int = 25, headers: dict | None = None) -> Any:
    return json.loads(get_bytes(url, timeout=timeout, headers=headers))


def _opener():
    if _state["opener"] is None:
        jar = http.cookiejar.CookieJar()
        _state["opener"] = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return _state["opener"]


def crumb(force: bool = False) -> str:
    if _state["crumb"] and not force:
        return _state["crumb"]
    opener = _opener()
    try:
        opener.open(urllib.request.Request("https://fc.yahoo.com", headers=UA), timeout=15).read()
    except urllib.error.HTTPError:
        pass
    except urllib.error.URLError:
        pass
    with opener.open(
        urllib.request.Request("https://query1.finance.yahoo.com/v1/test/getcrumb", headers=UA),
        timeout=15,
    ) as resp:
        token = resp.read().decode().strip()
    if not token or token.startswith("{") or token.startswith("<"):
        raise RuntimeError("Yahoo no entregó la credencial de consulta")
    _state["crumb"] = token
    return token


def post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    last_error: Exception | None = None
    with _lock:
        for force in (False, True):
            token = crumb(force=force)
            full = url + ("&" if "?" in url else "?") + "crumb=" + urllib.parse.quote(token)
            req = urllib.request.Request(
                full,
                data=json.dumps(payload).encode(),
                headers={**UA, "Content-Type": "application/json"},
            )
            try:
                with _opener().open(req, timeout=timeout) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as exc:
                last_error = exc
                _state["crumb"] = None
                if exc.code != 401:
                    detail = exc.read()[:300].decode("utf-8", "replace")
                    raise RuntimeError(f"Yahoo respondió {exc.code}: {detail}") from exc
    raise RuntimeError(f"Yahoo rechazó la consulta: {last_error}")


def unpack(cell: Any) -> Any:
    if isinstance(cell, dict):
        for key in ("lasttwelvemonths", "quarterly", "annual", "raw"):
            value = cell.get(key)
            if isinstance(value, dict):
                value = value.get("raw")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        return None
    if isinstance(cell, bool):
        return cell
    if isinstance(cell, (int, float)):
        return float(cell)
    if isinstance(cell, str):
        return cell
    return None


def visualize(query: dict, fields: list[str], sort_field: str, sort_type: str = "DESC", size: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    body = {
        "offset": offset,
        "size": size,
        "sortField": sort_field,
        "sortType": sort_type,
        "quoteType": "EQUITY",
        "includeFields": fields,
        "query": query,
    }
    data = post_json(
        "https://query1.finance.yahoo.com/v1/finance/visualization?lang=en-US&region=US",
        body,
    )
    finance = data.get("finance") or {}
    if finance.get("error"):
        raise RuntimeError(str(finance["error"]))
    result = (finance.get("result") or [None])[0] or {}
    documents = result.get("documents") or []
    if not documents:
        return [], int(result.get("total") or 0)
    doc = documents[0]
    ids = [col.get("id") for col in doc.get("columns") or []]
    rows = []
    for raw in doc.get("rows") or []:
        if not isinstance(raw, list):
            continue
        item = {}
        for cid, cell in zip(ids, raw):
            if cid:
                item[cid] = unpack(cell)
        rows.append(item)
    return rows, int(result.get("total") or len(rows))


SCREEN_FIELDS = [
    "ticker",
    "companyshortname",
    "region",
    "sector",
    "exchange",
    "intradaymarketcap",
    "intradayprice",
    "percentchange",
    "fiftytwowkpercentchange",
    "lastclose52weekhigh.lasttwelvemonths",
    "peratio.lasttwelvemonths",
    "forward_dividend_yield",
    "returnonequity.lasttwelvemonths",
    "netincomemargin.lasttwelvemonths",
    "grossprofitmargin.lasttwelvemonths",
    "ebitdamargin.lasttwelvemonths",
    "totaldebtequity.lasttwelvemonths",
    "totalrevenues1yrgrowth.lasttwelvemonths",
    "epsgrowth.lasttwelvemonths",
    "consecutive_years_of_dividend_growth_count",
    "dilutedepscontinuingoperations.lasttwelvemonths",
]


def screen(operands: list[dict], sort_field: str, sort_type: str = "DESC", size: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    query = {"operator": "AND", "operands": operands}
    return visualize(query, SCREEN_FIELDS, sort_field, sort_type, size, offset)


def spark(symbols: list[str], range_: str = "1mo", interval: str = "1d") -> dict[str, dict]:
    if not symbols:
        return {}
    found: dict[str, dict] = {}
    for start in range(0, len(symbols), 15):
        chunk = symbols[start : start + 15]
        encoded = ",".join(urllib.parse.quote(symbol, safe="") for symbol in chunk)
        url = (
            "https://query1.finance.yahoo.com/v7/finance/spark?symbols="
            + encoded
            + f"&range={range_}&interval={interval}"
        )
        payload = get_json(url, timeout=25)
        for item in (payload.get("spark") or {}).get("result") or []:
            response = item.get("response") or []
            if not response:
                continue
            block = response[0]
            meta = block.get("meta") or {}
            symbol = meta.get("symbol") or item.get("symbol")
            if not symbol:
                continue
            closes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            stamps = block.get("timestamp") or []
            points = []
            for stamp, close in zip(stamps, closes):
                if isinstance(close, (int, float)) and isinstance(stamp, (int, float)):
                    points.append({"t": int(stamp), "c": float(close)})
            found[symbol.upper()] = {"meta": meta, "points": points}
        if start + 15 < len(symbols):
            time.sleep(0.15)
    return found


def chart(symbol: str, range_: str = "1y", interval: str = "1d") -> dict:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol, safe="")
        + f"?range={range_}&interval={interval}&includePrePost=false"
    )
    payload = get_json(url, timeout=25)
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        error = (payload.get("chart") or {}).get("error") or {}
        raise RuntimeError(error.get("description") or f"Sin gráfico para {symbol}")
    meta = result.get("meta") or {}
    stamps = result.get("timestamp") or []
    closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    points = []
    for stamp, close in zip(stamps, closes):
        if isinstance(close, (int, float)) and isinstance(stamp, (int, float)):
            points.append({"t": int(stamp), "c": float(close)})
    return {"meta": meta, "points": points}


def quote_summary(symbol: str) -> dict:
    modules = ",".join(
        [
            "price",
            "summaryDetail",
            "financialData",
            "defaultKeyStatistics",
            "assetProfile",
            "calendarEvents",
            "earningsTrend",
            "recommendationTrend",
        ]
    )
    url = (
        "https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
        + urllib.parse.quote(symbol, safe="")
        + f"?modules={modules}&formatted=false"
    )
    with _lock:
        token = crumb()
        full = url + "&crumb=" + urllib.parse.quote(token)
        req = urllib.request.Request(full, headers=UA)
        with _opener().open(req, timeout=25) as resp:
            payload = json.load(resp)
    result = ((payload.get("quoteSummary") or {}).get("result") or [None])[0]
    if not result:
        error = (payload.get("quoteSummary") or {}).get("error")
        raise RuntimeError(str(error or f"Sin ficha para {symbol}"))
    return result


def search(query: str, quotes: int = 8) -> list[dict]:
    url = (
        "https://query1.finance.yahoo.com/v1/finance/search?q="
        + urllib.parse.quote(query)
        + f"&quotesCount={quotes}&newsCount=0&listsCount=0&enableFuzzyQuery=false"
    )
    payload = get_json(url, timeout=15)
    rows = []
    for item in payload.get("quotes") or []:
        if item.get("quoteType") not in ("EQUITY", "ETF", "INDEX", "MUTUALFUND"):
            continue
        rows.append(
            {
                "symbol": item.get("symbol"),
                "name": item.get("shortname") or item.get("longname") or item.get("symbol"),
                "exchange": item.get("exchDisp") or item.get("exchange"),
                "type": item.get("quoteType") or item.get("typeDisp"),
                "region": (item.get("region") or "").lower() or None,
            }
        )
    return rows


def annual_series(symbol: str, kind: str) -> list[tuple[str, float]]:
    now = int(time.time())
    url = (
        "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
        + urllib.parse.quote(symbol, safe="")
        + f"?symbol={urllib.parse.quote(symbol)}&type={kind}&period1=946684800&period2={now}"
    )
    payload = get_json(url, timeout=25)
    points: list[tuple[str, float]] = []
    for block in (payload.get("timeseries") or {}).get("result") or []:
        for point in block.get(kind) or []:
            if not isinstance(point, dict):
                continue
            raw = ((point.get("reportedValue") or {}).get("raw"))
            when = point.get("asOfDate")
            if isinstance(raw, (int, float)) and when:
                points.append((str(when), float(raw)))
    points.sort(key=lambda item: item[0])
    return points


def raw_number(value: Any) -> float | None:
    if isinstance(value, dict):
        inner = value.get("raw")
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return float(inner)
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
