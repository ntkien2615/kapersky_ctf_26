import hashlib
import math
import secrets

Q = 56943867286217719900381165402398914282249753669969277324317866129442103427931
P = int(
    "3208569992654097029874886628514649940445900165916684862559147199757985368713"
    "8931974252405760465713832098438366560090334259043863701072717924442921511392"
    "6993954732957463239260121063324930303649085605339506996135407091384304964309"
    "8594080051977280799750395720646831575096881593671141488864605061222360696668"
    "0429605086790154720834966569271153411601609706803920537201013107292302284214"
    "9124234618577003245540364604210872114040789375292291178868211922059724870104"
    "5037976255815131970330475258143140677407162561290773655319202348381082935795"
    "6326468496833859933757519816487640449508934738652772555227972427287723106838"
    "146432037"
)
G = int(
    "3853486746405019517983964174400780719206352733835706155301210082008773351315"
    "3834932861450566628895509166895380969816667839908342459007232421881477812769"
    "0205613522193042605017918503406950350736241781688038450145141265695918616271"
    "5861632265904974164877742245389853680063241838893680405831211357886590343688"
    "0933366150891456058162603651731418844228780313039693558407879913367046768129"
    "6676740902381645512275721633877953758072689579335695406646081542636783496708"
    "9826721471753375041661762502890782900496814569298476341840438922725671303038"
    "7373057895889061751699242795060847508605423606514420838413126294521085746744"
    "33657492"
)

MAX_SIGS = 36

LUT_SIZE = 1 << 15
PATCH_BITS = 12
RESID_BITS = 6
PROFILE_BITS = PATCH_BITS + RESID_BITS
PROFILE_MOD = 1 << PROFILE_BITS
PHASE_STEPS = 1 << 12
AFFINE_DEN = 1024
SHIFT_DEN = 128
TAU = 2.0 * math.pi
P_BYTES = (P.bit_length() + 7) // 8

assert (P - 1) % Q == 0
assert 1 < G < P
assert pow(G, Q, P) == 1


class CryptoError(Exception):
    pass


def radius(theta):
    return (
        (1 + 0.25 * math.sin(3 * theta + math.pi)) ** 1.4
        + 2 * math.exp(-((theta - math.pi / 2) / 0.3) ** 2)
    )


class Calibration:
    def __init__(self, cid, matrix, shift, step, direction):
        self.calibration_id = cid
        self.affine_num = matrix
        self.shift_num = shift
        self.phase_step = step
        self.direction = direction

    @classmethod
    def create(cls):
        cid = secrets.token_bytes(16)
        matrix = (
            1280 + secrets.randbelow(512),
            secrets.randbelow(257) - 128,
            secrets.randbelow(257) - 128,
            960 + secrets.randbelow(512),
        )
        shift = (
            secrets.randbelow(1025) - 512,
            secrets.randbelow(1025) - 512,
        )
        step = secrets.randbelow(PHASE_STEPS)
        direction = secrets.randbits(1)
        return cls(cid, matrix, shift, step, direction)

    @property
    def phase(self):
        return TAU * self.phase_step / PHASE_STEPS

    def public(self):
        mask = hashlib.sha256(
            b"calibration\x00" + self.calibration_id
        ).digest()
        return {
            "id": self.calibration_id.hex(),
            "affine_num": [
                [self.affine_num[0], self.affine_num[1]],
                [self.affine_num[2], self.affine_num[3]],
            ],
            "affine_den": AFFINE_DEN,
            "shift_num": list(self.shift_num),
            "shift_den": SHIFT_DEN,
            "phase_code": self.phase_step
            ^ (int.from_bytes(mask[:2], "big") & (PHASE_STEPS - 1)),
            "direction_code": self.direction ^ (mask[2] & 1),
        }


class PathProfile:
    def __init__(self, calibration):
        self.calibration = calibration
        pts = [self.point(TAU * i / LUT_SIZE) for i in range(LUT_SIZE + 1)]
        length = [0.0]
        for i in range(LUT_SIZE):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            length.append(length[-1] + math.hypot(x1 - x0, y1 - y0))
        self.sigma = [x / length[-1] for x in length]

    def point(self, theta):
        if theta < 0.0 or theta > TAU:
            theta %= TAU
        r = radius(theta)
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        a11, a12, a21, a22 = self.calibration.affine_num
        b1, b2 = self.calibration.shift_num
        u = (a11 * x + a12 * y) / AFFINE_DEN + b1 / SHIFT_DEN
        v = (a21 * x + a22 * y) / AFFINE_DEN + b2 / SHIFT_DEN
        return u, v

    def at(self, theta):
        pos = min(math.nextafter(float(LUT_SIZE), 0.0), theta / TAU * LUT_SIZE)
        i = int(pos)
        part = pos - i
        return self.sigma[i] * (1.0 - part) + self.sigma[i + 1] * part

    def diagnostic_bucket(self, value):
        position = min(LUT_SIZE - 1, int((value + 0.5) / PROFILE_MOD * LUT_SIZE))
        left = max(0, position - 1)
        right = min(LUT_SIZE, position + 1)
        slope = (self.sigma[right] - self.sigma[left]) * LUT_SIZE
        return min(255, int(abs(slope) * 96.0))


def challenge_hash(message, commitment):
    material = (
        b"challenge\x00"
        + len(message).to_bytes(4, "big")
        + message
        + commitment.to_bytes(P_BYTES, "big")
    )
    return int.from_bytes(hashlib.sha256(material).digest(), "big") % Q


def telemetry_mask(calibration_id, commitment, label, bits):
    material = (
        b"telemetry\x00"
        + calibration_id
        + commitment.to_bytes(P_BYTES, "big")
        + label
    )
    return int.from_bytes(hashlib.sha256(material).digest(), "big") & (
        (1 << bits) - 1
    )


class Session:
    def __init__(self, secret_key=None, calibration=None):
        self.secret_key = secrets.randbelow(Q - 1) + 1 if secret_key is None else secret_key
        if not 1 <= self.secret_key < Q:
            raise ValueError("secret key outside subgroup scalar range")
        self.public_key = pow(G, self.secret_key, P)
        self.calibration = calibration or Calibration.create()
        self.profile = PathProfile(self.calibration)
        self.remaining = MAX_SIGS
        self.used_nonces = set()

    def public(self):
        return {
            "ok": True,
            "p": str(P),
            "q": str(Q),
            "g": str(G),
            "y": str(self.public_key),
            "quota": self.remaining,
            "calibration": self.calibration.public(),
        }

    def _path_parameter(self, nonce):
        theta = TAU * (nonce / Q)
        traversed = TAU - theta if self.calibration.direction else theta
        return (traversed + self.calibration.phase) % TAU

    def _diagnostic_blob(self, nonce, commitment):
        parameter = self._path_parameter(nonce)
        sigma = self.profile.at(parameter)
        profile_value = min(PROFILE_MOD - 1, int(math.floor(sigma * PROFILE_MOD)))
        patch = profile_value >> RESID_BITS
        resid = profile_value & ((1 << RESID_BITS) - 1)
        curvature = self.profile.diagnostic_bucket(profile_value)
        iterations = 4 + ((profile_value ^ (profile_value >> 7)) % 4)
        basin = ((profile_value >> 9) ^ iterations) & 7
        cid = self.calibration.calibration_id
        health = hashlib.sha256(
            b"health\x00"
            + cid
            + commitment.to_bytes(P_BYTES, "big")
            + profile_value.to_bytes(3, "big")
        ).hexdigest()[:16]
        return {
            "patch": patch
            ^ telemetry_mask(cid, commitment, b"patch", PATCH_BITS),
            "resid": resid
            ^ telemetry_mask(cid, commitment, b"resid", RESID_BITS),
            "curv": curvature
            ^ telemetry_mask(cid, commitment, b"curv", 8),
            "basin": basin ^ telemetry_mask(cid, commitment, b"basin", 3),
            "iters": iterations,
            "health": health,
        }

    def _sign_with_nonce(self, message, nonce):
        if not 1 <= nonce < Q:
            raise ValueError("nonce outside subgroup scalar range")
        commitment = pow(G, nonce, P)
        challenge = challenge_hash(message, commitment)
        response = (nonce + challenge * self.secret_key) % Q
        return {
            "ok": True,
            "R": str(commitment),
            "s": str(response),
            "diag": self._diagnostic_blob(nonce, commitment),
            "remaining": self.remaining,
        }

    def sign(self, message):
        if self.remaining <= 0:
            raise CryptoError
        self.remaining -= 1
        while True:
            nonce = secrets.randbelow(Q - 1) + 1
            if nonce not in self.used_nonces:
                self.used_nonces.add(nonce)
                return self._sign_with_nonce(message, nonce)

    def verify(self, message, commitment, response):
        if not 1 < commitment < P or not 0 <= response < Q:
            return False
        if pow(commitment, Q, P) != 1:
            return False
        challenge = challenge_hash(message, commitment)
        left = pow(G, response, P)
        right = commitment * pow(self.public_key, challenge, P) % P
        return left == right
