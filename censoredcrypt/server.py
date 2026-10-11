import json
import os
import re
import secrets
import sys
import traceback

import supercoolcryptolib as crypto


FLAG = os.environ.get("FLAG", 'kaspersky{testflag}')
TARGET_MSG = b"give_me_gift"
MAX_MESSAGE = 512
MAX_LINE = 2048
MAX_COMMANDS = 48
MAX_UINT_DIGITS = len(str(crypto.P))

HEX_RE = re.compile(r"[0-9a-f]+")
UINT_RE = re.compile(r"0|[1-9][0-9]*")


class RequestError(Exception):
    pass


def parse_hex(token):
    if not token or len(token) % 2 or len(token) > MAX_MESSAGE * 2:
        raise RequestError
    if HEX_RE.fullmatch(token) is None:
        raise RequestError
    return bytes.fromhex(token)


def parse_uint(token):
    if len(token) > MAX_UINT_DIGITS or UINT_RE.fullmatch(token) is None:
        raise RequestError
    return int(token)


def sign_message(session, message):
    if secrets.compare_digest(message, TARGET_MSG):
        raise RequestError
    try:
        return session.sign(message)
    except crypto.CryptoError as exc:
        raise RequestError from exc


def send_line(stream, value):
    stream.write(value.encode("ascii") + b"\n")
    stream.flush()


def send_json(stream, value):
    send_line(stream, json.dumps(value, separators=(",", ":"), sort_keys=True))


def read_command(stream):
    raw = stream.readline(MAX_LINE + 2)
    if raw == b"":
        return None
    if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
        raise RequestError

    raw = raw[:-1]
    if raw.endswith(b"\r"):
        raw = raw[:-1]
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RequestError from exc


def run_session(reader, writer):
    session = crypto.Session()
    send_line(writer, "Censored diagnostics, probably fine")
    send_line(writer, "Try: PUB | SIGN <hex> | SUBMIT <hex> <R> <s>")

    for _ in range(MAX_COMMANDS):
        try:
            line = read_command(reader)
            if line is None:
                return
            match line.split(" "):
                case ["PUB"]:
                    send_json(writer, session.public())
                case ["QUIT"]:
                    send_json(writer, {"ok": True})
                    return
                case ["SIGN", encoded_message]:
                    message = parse_hex(encoded_message)
                    send_json(writer, sign_message(session, message))
                case ["SUBMIT", encoded_message, encoded_commitment, encoded_response]:
                    message = parse_hex(encoded_message)
                    commitment = parse_uint(encoded_commitment)
                    response = parse_uint(encoded_response)
                    prikol = secrets.compare_digest(
                        message, TARGET_MSG
                    ) and session.verify(message, commitment, response)
                    if prikol:
                        send_json(writer, {"ok": True, "flag": FLAG})
                    else:
                        send_json(
                            writer, {"ok": False, "error": "that signature did not work"}
                        )
                    return
                case _:
                    raise RequestError
        except RequestError:
            send_json(writer, {"ok": False, "error": "could not make sense of that"})
        except (TimeoutError, OSError):
            return
        except Exception:
            traceback.print_exc()
            send_json(writer, {"ok": False, "error": "internal error"})
            return


def main():
    run_session(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
