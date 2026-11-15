"""Inversor Íbex. Terminal local del inversor particular.

Solo escucha en 127.0.0.1. Las cotizaciones son diferidas.
No es asesoramiento ni una recomendación de inversión.
"""

from __future__ import annotations

import json
import os
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ibex.market import earnings, ficha, indices, news, sentiment, thermometer
from ibex.portfolio import summary, view as portfolio_view
from ibex.screen import dividends, gangas, quality_universe, run_screen
from ibex.yahoo import search

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "public"
HOST = "127.0.0.1"
PORT = 8787

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
}


def _float(params: dict, key: str) -> float | None:
    raw = (params.get(key) or [None])[0]
    if raw in (None, ""):
        return None
    return float(raw)


def build_home() -> dict:
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {
            "thermo": pool.submit(thermometer),
            "news": pool.submit(news),
            "earnings": pool.submit(earnings),
            "book": pool.submit(summary),
        }
        parts = {}
        errors = []
        for key, job in jobs.items():
            try:
                parts[key] = job.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{key}: {exc}")
                parts[key] = {}
    board = {}
    try:
        board = indices()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"indices: {exc}")
    wanted = ["^IBEX", "^STOXX50E", "^GSPC", "^GSPTSE", "^FTSE", "^GDAXI"]
    by_symbol = {row["symbol"]: row for row in board.get("items") or []}
    cards = [by_symbol[symbol] for symbol in wanted if symbol in by_symbol]
    headlines = parts["news"].get("sections") or []
    mercado = next((section for section in headlines if section.get("id") == "mercado"), {"items": []})
    thermo = parts["thermo"]
    return {
        "asof": thermo.get("asof") or board.get("asof"),
        "sessions": thermo.get("sessions") or board.get("sessions") or [],
        "temperature": thermo.get("temperature"),
        "label": thermo.get("label"),
        "fear": thermo.get("fear"),
        "breadth": thermo.get("breadth"),
        "vix": thermo.get("vix"),
        "curve": thermo.get("curve"),
        "sectors": (thermo.get("sectors") or [])[:6],
        "indices": cards,
        "news": (mercado.get("items") or [])[:6],
        "earnings": (parts["earnings"].get("items") or [])[:6],
        "portfolio": parts["book"],
        "warnings": errors,
        "error": None,
    }


def build_screener(params: dict) -> dict:
    region = ((params.get("region") or ["us"])[0] or "us").lower()
    allowed = {
        "us", "ca", "eu", "de", "fr", "gb", "es", "it", "nl", "ch", "se", "dk", "be", "fi", "no", "pt", "at", "ie",
    }
    if region not in allowed:
        region = "us"
    cap_bn = _float(params, "cap")
    cap = (cap_bn if cap_bn is not None else 10) * 1_000_000_000
    # Londres se filtra en peniques. 10.000 millones de libras son 1e12 peniques.
    if region == "gb":
        cap *= 100
    size = int(_float(params, "size") or 40)
    return run_screen(
        region=region,
        sector=((params.get("sector") or [""])[0] or ""),
        cap=max(cap, 0),
        pe_max=_float(params, "pe"),
        yield_min=_float(params, "dy"),
        roe_min=_float(params, "roe"),
        growth_min=_float(params, "growth"),
        change_min=_float(params, "chg_min"),
        change_max=_float(params, "chg_max"),
        sort_field=((params.get("sort") or ["intradaymarketcap"])[0] or "intradaymarketcap"),
        sort_dir=((params.get("dir") or ["desc"])[0] or "desc").lower(),
        size=size,
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[ibex] {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/favicon.ico":
            path = "/favicon.svg"
        try:
            if path.startswith("/api/"):
                self._api(path, parse_qs(parsed.query))
                return
            self._static(path)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(exc)}, 500)

    def _static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        target = (STATIC / path.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")
            return
        self._send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))

    def _api(self, path: str, params: dict) -> None:
        payload, code = api_payload(path, params)
        self._json(payload, code)


def api_payload(path: str, params: dict) -> tuple[dict, int]:
    if path == "/api/home":
        return build_home(), 200
    if path == "/api/indices":
        return indices(), 200
    if path == "/api/screener":
        return build_screener(params), 200
    if path == "/api/gangas":
        return gangas(), 200
    if path == "/api/calidad":
        return quality_universe(), 200
    if path == "/api/dividendos":
        return dividends(), 200
    if path == "/api/termometro":
        return thermometer(), 200
    if path == "/api/noticias":
        return news(), 200
    if path == "/api/resultados":
        return earnings(), 200
    if path == "/api/sentimiento":
        return sentiment(), 200
    if path == "/api/cartera":
        return portfolio_view(), 200
    if path == "/api/buscar":
        query = ((params.get("q") or [""])[0] or "").strip()
        return {"items": search(query) if len(query) >= 1 else []}, 200
    if path == "/api/ficha":
        symbol = ((params.get("symbol") or [""])[0] or "").strip()
        return ficha(symbol), 200
    return {"error": "Ruta no encontrada"}, 404


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Inversor Íbex en {url}")
    if os.environ.get("IBEX_OPEN", "1") != "0":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
