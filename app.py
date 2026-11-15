"""Entrada de Vercel. En este ordenador se sigue arrancando con server.py."""

from flask import Flask, jsonify, request

from server import api_payload

app = Flask(__name__)
app.json.ensure_ascii = False


@app.get("/api/<path:name>")
def api(name: str):
    params = {key: request.args.getlist(key) for key in request.args}
    try:
        payload, code = api_payload("/api/" + name, params)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    return jsonify(payload), code
