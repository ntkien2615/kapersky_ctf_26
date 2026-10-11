import os
import sys

from sudokrypt_core import BLOCK_SIZE, SudoKrypt


MAX_LINE = 512
ASCII_BANNER = r"""
 ___         _       _ __                 _
/ __> _ _  _| | ___ | / / _ _  _ _  ___ _| |_
\__ \| | |/ . |/ . \|  \ | '_>| | || . \ | |
<___/`___|\___|\___/|_\_\|_|  `_. ||  _/ |_|
                              <___'|_|"""


class LineTooLong(ValueError):
    pass


def make_banner(core):
    return (
        ASCII_BANNER
        + "\n\nQueries left: %d\n\n" % core.remaining
        + "1) encrypt one block\n"
        + "2) peek at Stacy's homework (once)\n"
        + "3) how many queries are left\n"
        + "4) get me out\n"
    )


def parse_plaintext(line):
    line = line.strip()
    if len(line) != BLOCK_SIZE * 2:
        raise ValueError("need exactly 32 hex characters")
    try:
        return bytes.fromhex(line)
    except ValueError:
        raise ValueError("that is not hexadecimal")


def send(text):
    sys.stdout.buffer.write(text.encode())
    sys.stdout.buffer.flush()


def read_line():
    data = sys.stdin.buffer.readline(MAX_LINE + 1)
    if not data:
        raise EOFError
    if len(data) > MAX_LINE and not data.endswith(b"\n"):
        while data and not data.endswith(b"\n"):
            data = sys.stdin.buffer.readline(MAX_LINE + 1)
        raise LineTooLong("input line is too long")
    return data.decode("ascii", errors="replace").rstrip("\r\n")


def encrypt(core):
    if core.remaining <= 0:
        send("error: query limit exceeded\n")
        return
    send("plaintext hex> ")
    plaintext = parse_plaintext(read_line())
    ciphertext = core.encrypt_block(plaintext)
    send("ciphertext: %s\n" % ciphertext.hex())
    send("queries left: %d\n" % core.remaining)


def menu(core):
    send(make_banner(core))
    while True:
        send("> ")
        try:
            prikol = read_line().strip().lower()
            if prikol in ("1", "encrypt", "enc"):
                encrypt(core)
            elif prikol in ("2", "flag", "target"):
                ciphertext = core.encrypt_flag()
                send("encrypted flag: %s\n" % ciphertext.hex())
            elif prikol in ("3", "status"):
                send("queries left: %d\n" % core.remaining)
            elif prikol in ("4", "quit", "exit"):
                send("bye\n")
                return
            elif prikol:
                send("error: try one of the menu numbers\n")
        except (LineTooLong, ValueError, RuntimeError) as error:
            send("error: %s\n" % error)


def main():
    core = SudoKrypt(
        os.environ.get("CHALLENGE_SEED", '0'),
        os.environ.get("FLAG", 'kaspersky{testflag}'),
        int(os.environ.get("QUERY_LIMIT", "96")),
    )
    try:
        menu(core)
    except (EOFError, OSError):
        pass


if __name__ == "__main__":
    main()
