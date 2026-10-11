#!/usr/bin/env python3
"""
Solution for SudoKrypt challenge (100% Deterministic Algebraic Attack - No Brute Force)

Vulnerabilities & Cryptanalytic Steps:
1. Chosen-Plaintext Structure:
   - In queries 0..15, we send plaintext with bytes `[(k << 4) | k] * 16`.
     Every word's top nibble is directly `q_perm[k]`. This recovers the full `q_perm` and `q_inv`.
   - In queries 16..95, we send plaintext with bytes `[(i << 4) | i for i in range(16)]`.
     Because lane `i` has distinct label `q_perm[i]`, the top nibble of `words[0]` immediately
     reveals the exact rotation: `rotation = q_inv[words[0] >> 12]`. Zero rotation ambiguity!

2. Algebraic Stream Value Extraction:
   - For `symbol = 0`, `symbol_inv[0] = C` (16 possible values for `C`).
   - Using S-box invertibility and field relations:
       `sbox_low = 11 * (2 * row_field - col_field + C) mod 16`
       `low = SBOX_INV[sbox_low]`
       `mask = (row_field - sbox_low) mod 16`
       `high = check ^ SBOX[...]`
     Every word uniquely maps to a stream value. Only the true `C` satisfies `block_rotation` across all blocks.

3. Linear Recurrence & Spectrum Recovery:
   - The PRNG sequence `V[t][l] = sum_j c_{l,j} * n_j^t (mod 4093)` satisfies a linear recurrence of degree 56:
       `V[t+56][l] + c_1 * V[t+55][l] + ... + c_56 * V[t][l] = 0 (mod 4093)`
   - All 16 lanes share the same characteristic polynomial `P(x) = x^56 + c_1 x^55 + ... + c_56`.
   - Across 80 blocks and 16 lanes, we have 24 * 16 = 384 equations for 56 variables. We solve via Gaussian elimination mod 4093.
   - The roots of `P(x) = 0` in GF(4093) give all 56 spectrum nodes `nodes`!

4. Exact PRNG State & Flag Decryption:
   - We solve the Vandermonde linear system to obtain all initial coefficients `coefficients`.
   - We reconstruct `symbol_perm` via `symbol_permutation_from_model(nodes, coefficients)`.
   - We advance the reconstructed PRNG 96 steps, apply `fold_for_flag()`, and decrypt all flag blocks directly.
"""

import socket
import subprocess
import sys
from sudokrypt_core import (
    unpack_rank_words, split_word, SBOX, inverse_permutation, rotl4,
    block_rotation, FIELD, GENERATOR, SPECTRUM_SIZE, BLOCK_SIZE, pkcs7_unpad,
    symbol_permutation_from_model, SpectrumGenerator
)


class OracleClient:
    def __init__(self, host=None, port=None, local=False):
        self.local = local
        if local:
            self.proc = subprocess.Popen(
                [sys.executable, "server.py"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            self.buffer = b""

    def recv_until(self, delimiter):
        if self.local:
            buf = b""
            while delimiter not in buf:
                ch = self.proc.stdout.read(1)
                if not ch:
                    raise EOFError("Local process terminated")
                buf += ch
            return buf.decode("ascii", errors="replace")
        else:
            while delimiter not in self.buffer:
                data = self.sock.recv(4096)
                if not data:
                    raise ConnectionError("Connection closed")
                self.buffer += data
            idx = self.buffer.index(delimiter) + len(delimiter)
            result = self.buffer[:idx].decode("ascii", errors="replace")
            self.buffer = self.buffer[idx:]
            return result

    def send_line(self, line):
        data = (line + "\n").encode()
        if self.local:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        else:
            self.sock.sendall(data)

    def encrypt_block(self, pt_bytes):
        self.send_line("1")
        self.recv_until(b"plaintext hex> ")
        self.send_line(pt_bytes.hex())
        res = self.recv_until(b"> ")
        for line in res.splitlines():
            if line.startswith("ciphertext: "):
                return bytes.fromhex(line.split(": ")[1].strip())
        raise RuntimeError(f"Unexpected response: {res}")

    def get_flag(self):
        self.send_line("2")
        res = self.recv_until(b"> ")
        for line in res.splitlines():
            if line.startswith("encrypted flag: "):
                return bytes.fromhex(line.split(": ")[1].strip())
        raise RuntimeError(f"Unexpected response: {res}")

    def close(self):
        if self.local:
            self.proc.terminate()
        else:
            self.sock.close()


def solve_system(A, b, mod):
    """Solve linear system Ax = b (mod mod) using Gaussian elimination"""
    n, m = len(A), len(A[0])
    M = [[A[i][j] % mod for j in range(m)] + [b[i] % mod] for i in range(n)]
    row = 0
    for col in range(m):
        piv = None
        for r in range(row, n):
            if M[r][col] != 0:
                piv = r
                break
        if piv is None:
            continue
        M[row], M[piv] = M[piv], M[row]
        inv = pow(M[row][col], -1, mod)
        for c in range(col, m + 1):
            M[row][c] = (M[row][c] * inv) % mod
        for r in range(n):
            if r != row and M[r][col] != 0:
                factor = M[r][col]
                for c in range(col, m + 1):
                    M[r][c] = (M[r][c] - factor * M[row][c]) % mod
        row += 1
    return [M[i][m] for i in range(m)]


def decode_inner_word(word, stream_value, q_inv, symbol_perm):
    q_label, row_field, col_field, check_field = split_word(word)
    q = q_inv[q_label]
    high = stream_value >> 8
    mask = (stream_value >> 4) & 15
    low = stream_value & 15
    row_code = SBOX[low]
    base_col = (col_field - 2 * mask) & 15
    symbol = symbol_perm[(row_code + base_col) & 15]
    return (q << 4) | ((symbol + q) & 15)


def solve(host="tcp.sasc.tf", port=31415, local=False):
    print(f"[*] Starting algebraic SudoKrypt solver (local={local})...")
    client = OracleClient(host=host, port=port, local=local)
    client.recv_until(b"> ")

    try:
        # Step 1: Send 96 chosen-plaintext queries
        print("[*] Sending 96 structured oracle queries...")
        cts = []

        # Queries 0..15: all bytes = (k << 4) | k to learn q_perm
        for k in range(16):
            pt = bytes([(k << 4) | k] * 16)
            cts.append(client.encrypt_block(pt))

        # Queries 16..95: byte i = (i << 4) | i to enforce unambiguous rotation
        for k in range(16, 96):
            pt = bytes([(i << 4) | i for i in range(16)])
            cts.append(client.encrypt_block(pt))

        print("[*] Requesting encrypted flag...")
        flag_ct = client.get_flag()
        print(f"[+] Received encrypted flag ({len(flag_ct)} bytes)")

        # Step 2: Recover q_perm & q_inv
        q_perm = [None] * 16
        for k in range(16):
            words = unpack_rank_words(cts[k])
            q_perm[k] = split_word(words[0])[0]
        q_inv = inverse_permutation(q_perm)
        print(f"[+] Recovered q_perm: {q_perm}")

        # Step 3: Recover C = symbol_inv[0] and exact stream values for blocks 16..95
        SBOX_INV = inverse_permutation(SBOX)

        def eval_stream_80(C):
            vals_80 = []
            for k in range(16, 96):
                words = unpack_rank_words(cts[k])
                rot = q_inv[split_word(words[0])[0]]
                unrot = [words[(rank - rot) & 15] for rank in range(16)]
                row_vals = []
                for i in range(16):
                    q_label, row_f, col_f, chk = split_word(unrot[i])
                    sbox_low = (11 * (2 * row_f - col_f + C)) & 15
                    low = SBOX_INV[sbox_low]
                    mask = (row_f - sbox_low) & 15
                    base_col = (C - sbox_low) & 15
                    high = chk ^ SBOX[(sbox_low ^ rotl4(base_col, 1) ^ i ^ low) & 15]
                    val = (high << 8) | (mask << 4) | low
                    if val >= FIELD:
                        return None
                    row_vals.append(val)
                if block_rotation(row_vals, k) != rot:
                    return None
                vals_80.append(row_vals)
            return vals_80

        found_C = None
        vals_80 = None
        for C in range(16):
            res = eval_stream_80(C)
            if res is not None:
                found_C = C
                vals_80 = res
                break

        if found_C is None:
            raise RuntimeError("[-] Failed to find matching symbol_inv[0]")
        print(f"[+] Recovered symbol_inv[0] = {found_C} and 80 blocks of stream values")

        # Step 4: Solve linear recurrence for characteristic polynomial
        print("[*] Solving linear recurrence system mod 4093...")
        A, b = [], []
        for t in range(80 - SPECTRUM_SIZE):
            for l in range(16):
                A.append([vals_80[t + SPECTRUM_SIZE - 1 - i][l] for i in range(SPECTRUM_SIZE)])
                b.append((-vals_80[t + SPECTRUM_SIZE][l]) % FIELD)

        sol = solve_system(A, b, FIELD)
        poly = [1] + sol

        # Step 5: Find 56 spectrum nodes (roots of characteristic polynomial)
        print("[*] Computing roots of characteristic polynomial...")
        nodes = []
        for x in range(1, FIELD):
            val = 0
            for c in poly:
                val = (val * x + c) % FIELD
            if val == 0:
                nodes.append(x)
        nodes = sorted(nodes)
        if len(nodes) != SPECTRUM_SIZE:
            raise RuntimeError(f"Expected {SPECTRUM_SIZE} nodes, found {len(nodes)}")
        print(f"[+] Recovered all {len(nodes)} spectrum nodes")

        # Step 6: Recover all initial lane coefficients via Vandermonde inversion
        print("[*] Reconstructing initial PRNG coefficients...")
        V_mat = [[pow(node, t, FIELD) for node in nodes] for t in range(SPECTRUM_SIZE)]
        coefficients = []
        for l in range(16):
            b_l = [vals_80[t][l] for t in range(SPECTRUM_SIZE)]
            c_16 = solve_system(V_mat, b_l, FIELD)
            c_orig = [(c_16[j] * pow(pow(nodes[j], 16, FIELD), -1, FIELD)) % FIELD for j in range(SPECTRUM_SIZE)]
            coefficients.append(c_orig)
        print("[+] Reconstructed all 16x56 PRNG coefficients")

        # Step 7: Build model, advance PRNG to 96, fold_for_flag, and decrypt flag
        print("[*] Advancing PRNG and decrypting flag...")
        symbol_perm = symbol_permutation_from_model(nodes, coefficients)
        recon_prng = SpectrumGenerator(nodes, coefficients)
        for _ in range(96):
            recon_prng.next_block()
        recon_prng.fold_for_flag()

        flag_blocks = []
        for blk_idx in range(0, len(flag_ct), 32):
            blk = flag_ct[blk_idx:blk_idx + 32]
            words = unpack_rank_words(blk)
            blk_num = recon_prng.block_number
            vals = recon_prng.next_block()
            rot = block_rotation(vals, blk_num)
            unrot = [words[(rank - rot) & 15] for rank in range(16)]
            pt_bytes = bytes([decode_inner_word(unrot[i], vals[i], q_inv, symbol_perm) for i in range(16)])
            flag_blocks.append(pt_bytes)

        flag = pkcs7_unpad(b"".join(flag_blocks)).decode("utf-8", errors="replace")
        print("\n" + "=" * 60)
        print(f"[+] FLAG: {flag}")
        print("=" * 60 + "\n")
        return flag

    finally:
        client.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "local":
        solve(local=True)
    elif len(sys.argv) >= 3:
        solve(host=sys.argv[1], port=int(sys.argv[2]))
    else:
        solve(local=True)