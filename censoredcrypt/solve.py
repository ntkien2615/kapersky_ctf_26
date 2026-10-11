import bisect
import hashlib
import json
import math
import secrets
import socket
import time
import gmpy2
from gmpy2 import mpfr, mpz
import supercoolcryptolib as crypto

gmpy2.get_context().precision = 400

HOST = "tcp.sasc.tf"
PORT = 41592
TARGET_MSG = b"give_me_gift"


def invert_profile(profile, sigma_val):
    i = bisect.bisect_right(profile.sigma, sigma_val) - 1
    i = max(0, min(crypto.LUT_SIZE - 1, i))
    d = profile.sigma[i + 1] - profile.sigma[i]
    part = (sigma_val - profile.sigma[i]) / d if d > 0 else 0.0
    pos = i + part
    return (pos / crypto.LUT_SIZE) * crypto.TAU


def estimate_nonce(session_pub, R, diag):
    cid = bytes.fromhex(session_pub["calibration"]["id"])
    cal_pub = session_pub["calibration"]
    mask = crypto.hashlib.sha256(b"calibration\x00" + cid).digest()
    matrix = (
        cal_pub["affine_num"][0][0],
        cal_pub["affine_num"][0][1],
        cal_pub["affine_num"][1][0],
        cal_pub["affine_num"][1][1],
    )
    shift = tuple(cal_pub["shift_num"])
    step = cal_pub["phase_code"] ^ (
        int.from_bytes(mask[:2], "big") & (crypto.PHASE_STEPS - 1)
    )
    direction = cal_pub["direction_code"] ^ (mask[2] & 1)
    cal = crypto.Calibration(cid, matrix, shift, step, direction)
    profile = crypto.PathProfile(cal)

    patch = diag["patch"] ^ crypto.telemetry_mask(cid, R, b"patch", crypto.PATCH_BITS)
    resid = diag["resid"] ^ crypto.telemetry_mask(cid, R, b"resid", crypto.RESID_BITS)
    pv = (patch << crypto.RESID_BITS) | resid

    expected_health = crypto.hashlib.sha256(
        b"health\x00"
        + cid
        + R.to_bytes(crypto.P_BYTES, "big")
        + pv.to_bytes(3, "big")
    ).hexdigest()[:16]
    assert expected_health == diag["health"], "Health check failed!"

    s_mid = (pv + 0.5) / crypto.PROFILE_MOD
    param = invert_profile(profile, s_mid)

    traversed = (param - cal.phase) % crypto.TAU
    if cal.direction:
        theta = (crypto.TAU - traversed) % crypto.TAU
    else:
        theta = traversed % crypto.TAU
    k_est = int(round((theta / crypto.TAU) * crypto.Q)) % crypto.Q
    return k_est


def lll(basis, delta=0.75):
    n = len(basis)
    m = len(basis[0])
    B = [[mpz(x) for x in row] for row in basis]
    delta = mpfr(delta)

    B_star = [[mpfr(0)] * m for _ in range(n)]
    mu = [[mpfr(0)] * n for _ in range(n)]
    gamma = [mpfr(0)] * n

    for i in range(n):
        for c in range(m):
            B_star[i][c] = mpfr(B[i][c])
        for j in range(i):
            num = sum(mpfr(B[i][c]) * B_star[j][c] for c in range(m))
            mu[i][j] = num / gamma[j]
            for c in range(m):
                B_star[i][c] -= mu[i][j] * B_star[j][c]
        gamma[i] = sum(B_star[i][c] ** 2 for c in range(m))
        mu[i][i] = mpfr(1)

    k = 1
    while k < n:
        for j in range(k - 1, -1, -1):
            if abs(mu[k][j]) > mpfr(0.5):
                q = int(round(float(mu[k][j])))
                if q != 0:
                    for c in range(m):
                        B[k][c] -= q * B[j][c]
                    for l in range(j + 1):
                        mu[k][l] -= mpfr(q) * mu[j][l]

        if gamma[k] >= (delta - mu[k][k - 1] ** 2) * gamma[k - 1]:
            k += 1
        else:
            B[k], B[k - 1] = B[k - 1], B[k]

            for c in range(m):
                B_star[k - 1][c] = mpfr(B[k - 1][c])
            for j in range(k - 1):
                num = sum(mpfr(B[k - 1][c]) * B_star[j][c] for c in range(m))
                mu[k - 1][j] = num / gamma[j]
                for c in range(m):
                    B_star[k - 1][c] -= mu[k - 1][j] * B_star[j][c]
            gamma[k - 1] = sum(B_star[k - 1][c] ** 2 for c in range(m))

            for c in range(m):
                B_star[k][c] = mpfr(B[k][c])
            for j in range(k):
                num = sum(mpfr(B[k][c]) * B_star[j][c] for c in range(m))
                mu[k][j] = num / gamma[j]
                for c in range(m):
                    B_star[k][c] -= mu[k][j] * B_star[j][c]
            gamma[k] = sum(B_star[k][c] ** 2 for c in range(m))

            for i in range(k + 1, n):
                for j in (k - 1, k):
                    num = sum(mpfr(B[i][c]) * B_star[j][c] for c in range(m))
                    mu[i][j] = num / gamma[j]

            k = max(k - 1, 1)

    return [[int(x) for x in row] for row in B], B_star, mu


def babai_cvp(B, B_star, mu, target):
    n = len(B)
    m = len(B[0])
    b = [mpfr(x) for x in target]
    res = [mpz(0)] * m
    diff = list(b)

    for i in range(n - 1, -1, -1):
        c_i = sum(diff[c] * B_star[i][c] for c in range(m)) / sum(
            B_star[i][c] ** 2 for c in range(m)
        )
        c_i_round = mpz(round(float(c_i)))
        for c in range(m):
            res[c] += c_i_round * B[i][c]
            diff[c] -= mpfr(c_i_round * B[i][c])

    return [int(x) for x in res]


def main():
    print(f"Connecting to {HOST}:{PORT}...")
    s = socket.socket()
    s.connect((HOST, PORT))
    f = s.makefile("rwb")

    line1 = f.readline().decode()
    line2 = f.readline().decode()
    print("Banner:", line1.strip(), "|", line2.strip())

    # 1. Get PUB
    f.write(b"PUB\n")
    f.flush()
    pub_line = f.readline().decode()
    pub = json.loads(pub_line)
    print("PUB received.")

    P = int(pub["p"])
    Q = int(pub["q"])
    G = int(pub["g"])
    Y = int(pub["y"])

    # 2. Collect 22 signatures
    m_sigs = 22
    print(f"Collecting {m_sigs} signatures...")
    e_list = []
    s_list = []
    k_est_list = []

    for i in range(m_sigs):
        msg = f"hello_ctf_msg_{i}".encode()
        f.write(f"SIGN {msg.hex()}\n".encode())
        f.flush()
        sig_line = f.readline().decode()
        sig = json.loads(sig_line)
        if not sig.get("ok"):
            print(f"Error getting signature: {sig}")
            return

        R = int(sig["R"])
        s_val = int(sig["s"])
        k_est = estimate_nonce(pub, R, sig["diag"])
        e = crypto.challenge_hash(msg, R)

        e_list.append(e % Q)
        s_list.append(s_val % Q)
        k_est_list.append(k_est)

    print("Signatures collected. Building lattice...")
    e0_inv = pow(e_list[0], -1, Q)
    A_list = [(e_list[i] * e0_inv) % Q for i in range(1, m_sigs)]
    C_list = [
        ((s_list[i] - k_est_list[i]) - A_list[i - 1] * (s_list[0] - k_est_list[0]))
        % Q
        for i in range(1, m_sigs)
    ]

    basis = []
    for i in range(m_sigs - 1):
        row = [0] * m_sigs
        row[i] = Q
        basis.append(row)

    row_0 = [A_list[i] for i in range(m_sigs - 1)] + [1]
    basis.append(row_0)

    target = [-C_list[i] for i in range(m_sigs - 1)] + [0]

    t0 = time.time()
    print("Running LLL + Babai CVP...")
    B_red, B_star, mu = lll(basis)
    closest = babai_cvp(B_red, B_star, mu, target)
    t1 = time.time()
    print(f"Lattice reduction finished in {t1 - t0:.2f}s")

    delta_0 = closest[-1]
    k0_rec = (k_est_list[0] + delta_0) % Q
    x_rec = ((s_list[0] - k0_rec) * e0_inv) % Q

    if pow(G, x_rec, P) == Y:
        print(f"[+] Secret key recovered successfully! x = {x_rec}")
    else:
        print("[-] Verification failed with delta_0 from CVP. Trying candidate vectors...")
        # Check rows of reduced basis in case
        recovered = False
        for row in B_red:
            for sign in [1, -1]:
                d0 = sign * row[-1]
                k0_cand = (k_est_list[0] + d0) % Q
                x_cand = ((s_list[0] - k0_cand) * e0_inv) % Q
                if pow(G, x_cand, P) == Y:
                    x_rec = x_cand
                    print(f"[+] Secret key recovered from reduced basis! x = {x_rec}")
                    recovered = True
                    break
            if recovered:
                break
        if not recovered:
            print("[-] Attack failed.")
            return

    # Forge signature on TARGET_MSG
    print(f"Forging signature on TARGET_MSG: {TARGET_MSG}...")
    k_target = secrets.randbelow(Q - 1) + 1
    R_target = pow(G, k_target, P)
    e_target = crypto.challenge_hash(TARGET_MSG, R_target)
    s_target = (k_target + e_target * x_rec) % Q

    submit_cmd = f"SUBMIT {TARGET_MSG.hex()} {R_target} {s_target}\n"
    f.write(submit_cmd.encode())
    f.flush()

    flag_resp = f.readline().decode()
    print(f"Response: {flag_resp.strip()}")

    s.close()


if __name__ == "__main__":
    main()
