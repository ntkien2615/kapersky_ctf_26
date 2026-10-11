import itertools
import json
import math
import ssl
import time
import urllib.request


SERVER_URL = "https://riffle-royale.task.sasc.tf"


class Curve:
    def __init__(self, p, a, b):
        self.p = p
        self.a = a % p
        self.b = b % p

    def add(self, p1, p2):
        if p1 is None:
            return p2
        if p2 is None:
            return p1
        x1, y1 = p1
        x2, y2 = p2
        p = self.p
        if x1 == x2 and (y1 + y2) % p == 0:
            return None
        if p1 == p2:
            if y1 == 0:
                return None
            k = (3 * x1 * x1 + self.a) * pow(2 * y1, -1, p) % p
        else:
            k = (y2 - y1) * pow(x2 - x1, -1, p) % p
        x3 = (k * k - x1 - x2) % p
        return x3, (k * (x1 - x3) - y1) % p

    def mul(self, n, point):
        out = None
        while n:
            if n & 1:
                out = self.add(out, point)
            point = self.add(point, point)
            n >>= 1
        return out


def get_ABC(x_prev, x_curr, x_next):
    A = x_next - 2 * x_curr + x_prev
    B = -2 * x_curr * (x_next + x_curr + x_prev)
    C = x_curr**2 * (x_next + x_prev)
    return A, B, C


def get_Q(xs, ABCs, i1, i2, i3):
    x1, x2, x3 = xs[i1], xs[i2], xs[i3]
    A1, B1, C1 = ABCs[i1 - 1]
    A2, B2, C2 = ABCs[i2 - 1]
    A3, B3, C3 = ABCs[i3 - 1]
    alpha = (x2 - x3) * A1 + (x3 - x1) * A2 + (x1 - x2) * A3
    beta = (x2 - x3) * B1 + (x3 - x1) * B2 + (x1 - x2) * B3
    gamma = (x2 - x3) * C1 + (x3 - x1) * C2 + (x1 - x2) * C3
    return alpha, beta, gamma


def resultant(q1, q2):
    a1, b1, c1 = q1
    a2, b2, c2 = q2
    return (a1 * c2 - a2 * c1) ** 2 - (a1 * b2 - a2 * b1) * (b1 * c2 - b2 * c1)


def solve():
    ctx = ssl._create_unverified_context()

    print("[*] Dealing a new game...")
    req = urllib.request.Request(f"{SERVER_URL}/api/deal")
    with urllib.request.urlopen(req, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    game_id = data["id"]
    target_index = int(data["target"])
    samples = [int(x) for x in data["samples"]]
    print(f"[+] Game ID: {game_id}")
    print(f"[+] Target index: {target_index}")
    print(f"[+] Received {len(samples)} interleaved samples.")

    t0 = time.time()
    candidates = list(itertools.combinations(range(1, 14), 6))
    found_target = None

    for comb in candidates:
        xs = [samples[0]] + [samples[i] for i in comb]
        ABCs = [get_ABC(xs[i - 1], xs[i], xs[i + 1]) for i in range(1, 6)]
        Q1 = get_Q(xs, ABCs, 1, 2, 3)
        Q2 = get_Q(xs, ABCs, 2, 3, 4)
        Q3 = get_Q(xs, ABCs, 3, 4, 5)
        r12 = resultant(Q1, Q2)
        r23 = resultant(Q2, Q3)
        g = math.gcd(r12, r23)

        if g > (1 << 200):
            Q4 = get_Q(xs, ABCs, 1, 3, 5)
            g = math.gcd(g, resultant(Q1, Q4))

            # Remove small factors from GCD
            for d in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97]:
                while g % d == 0:
                    g //= d
            for d in range(101, 10000, 2):
                while g % d == 0:
                    g //= d

            p = g
            a1, b1, c1 = Q1
            a2, b2, c2 = Q2
            mu = (a1 * b2 - a2 * b1) % p
            nu = (a1 * c2 - a2 * c1) % p
            xS = (-nu * pow(mu, -1, p)) % p

            def calc_E(x_prev, x_curr, x_next, xS):
                A, B, C = get_ABC(x_prev, x_curr, x_next)
                return (A * xS**2 + B * xS + C) % p

            E1 = calc_E(xs[0], xs[1], xs[2], xS)
            E2 = calc_E(xs[1], xs[2], xs[3], xS)

            a_rec = ((E1 - E2) * pow(2 * (xs[1] - xs[2]), -1, p)) % p
            b_rec = ((E1 - 2 * (xs[1] + xS) * a_rec) * pow(4, -1, p)) % p

            rec_curve = Curve(p, a_rec, b_rec)
            yS = pow((xS**3 + a_rec * xS + b_rec) % p, (p + 1) // 4, p)
            y0 = pow((xs[0] ** 3 + a_rec * xs[0] + b_rec) % p, (p + 1) // 4, p)

            cand_S = (xS, yS)
            cand_U = (xs[0], y0)
            if rec_curve.add(cand_U, cand_S)[0] != xs[1]:
                cand_S = (xS, -yS % p)

            jump = rec_curve.mul(target_index, cand_S)
            found_target = rec_curve.add(cand_U, jump)[0]
            print(f"[+] Reconstructed curve & target in {time.time() - t0:.3f}s: {found_target}")
            break

    if found_target is None:
        print("[-] Failed to find matching lane.")
        return

    # Submit solution for slot 0
    payload = json.dumps({"id": game_id, "slot": 0, "value": str(found_target)}).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVER_URL}/api/submit",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, context=ctx) as resp:
        resp_data = json.loads(resp.read().decode("utf-8"))
        print(f"[+] Server Response: {resp_data}")
        if resp_data.get("ok"):
            print(f"\n[+] FLAG: {resp_data.get('message')}")


if __name__ == "__main__":
    solve()
