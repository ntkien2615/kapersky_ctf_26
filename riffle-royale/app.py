import argparse
import hmac
import os
import re
import secrets
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from server import TARGET_INDEX, generate_instance

FLAG = os.environ.get("FLAG", "kaspersky{testflag}")
TTL = 300
MAX_BODY = 2048
MAX_GAMES = 2048
GAMES = {}
LOCK = threading.Lock()
NUMBER = re.compile(r"[0-9]{1,80}")
ROOT = Path(__file__).parent
FILES = {
    "/": ("web/index.html", "text/html"),
    "/index.html": ("web/index.html", "text/html"),
    "/app.css": ("web/app.css", "text/css"),
    "/app.js": ("web/app.js", "text/javascript"),
}
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY
app.json.sort_keys = False


def clean_games(now):
    for key, game in list(GAMES.items()):
        if game["until"] < now:
            del GAMES[key]


def new_game():
    now = time.monotonic()
    game = generate_instance()
    token = secrets.token_urlsafe(24)
    with LOCK:
        clean_games(now)
        if len(GAMES) >= MAX_GAMES:
            del GAMES[next(iter(GAMES))]
        GAMES[token] = {
            "until": now + TTL,
            "hand": game["hand_values"],
        }
    return {
        "id": token,
        "samples": [str(value) for value in game["observations"]],
        "target": TARGET_INDEX,
        "ttl": TTL,
    }


def reply(status, data):
    response = jsonify(data)
    response.status_code = status
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


@app.after_request
def disable_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(RequestEntityTooLarge)
def body_too_large(_error):
    return reply(400, {"ok": False, "message": "that bet is way too big"})


@app.get("/")
@app.get("/index.html")
@app.get("/app.css")
@app.get("/app.js")
def static_file():
    name, mime = FILES[request.path]
    return send_file(ROOT / name, mimetype=mime)


@app.get("/api/deal")
def deal():
    return reply(200, new_game())


@app.post("/api/submit")
def submit():
    size = request.content_length
    if size is None or size < 2 or size > MAX_BODY:
        return reply(400, {"ok": False, "message": "the dealer cannot read that"})

    try:
        data = request.get_json(silent=True)
        game_id = data["id"]
        slot = data["slot"]
        value = data["value"]
        if type(game_id) is not str or type(slot) is not int or type(value) is not str:
            raise ValueError
        if slot not in (0, 1) or NUMBER.fullmatch(value) is None or str(int(value)) != value:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return reply(400, {"ok": False, "message": "the dealer cannot read that"})

    now = time.monotonic()
    with LOCK:
        clean_games(now)
        game = GAMES.pop(game_id, None)

    if game is None:
        return reply(410, {"ok": False, "message": "round is over"})

    prikol = str(game["hand"][slot])
    if hmac.compare_digest(value, prikol):
        return reply(200, {"ok": True, "message": FLAG})
    return reply(200, {"ok": False, "message": "nope. the house keeps it"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=14159)
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
