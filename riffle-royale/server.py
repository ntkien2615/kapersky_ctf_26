import secrets

BITS = 255
LANE_SAMPLES = 7
OBSERVATION_COUNT = LANE_SAMPLES * 2
TARGET_INDEX = (1 << 32) + 1609
MAX_GENERATION_TRIES = 256

rnd = secrets.SystemRandom()


def is_probable_prime(n, rounds=32):
    if n < 2:
        return False

    for q in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43):
        if n % q == 0:
            return n == q

    d = n - 1
    s = 0
    while not d & 1:
        d //= 2
        s += 1

    for _ in range(rounds):
        a = rnd.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def random_prime(bits):
    while True:
        p = secrets.randbits(bits) | (1 << (bits - 1)) | 3
        if is_probable_prime(p):
            return p


class Curve:
    def __init__(self, p, a, b):
        self.p = p
        self.a = a % p
        self.b = b % p

    def neg(self, point):
        if point is None:
            return None
        return point[0], -point[1] % self.p

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


def random_point(curve):
    p = curve.p
    while True:
        x = rnd.randrange(p)
        v = (x * x * x + curve.a * x + curve.b) % p
        if v == 0:
            return x, 0
        if pow(v, (p - 1) // 2, p) == 1:
            y = pow(v, (p + 1) // 4, p)
            if rnd.getrandbits(1):
                y = -y % p
            return x, y


def orbit(curve, start, step, size):
    values = []
    points = []
    for _ in range(size):
        if start is None:
            return [], []
        values.append(start[0])
        points.append(start)
        start = curve.add(start, step)
    return values, points


def generate_instance():
    for _ in range(MAX_GENERATION_TRIES):
        p = random_prime(BITS)
        a = rnd.randrange(p)
        b = rnd.randrange(p)
        if (4 * a**3 + 27 * b**2) % p == 0:
            continue

        curve = Curve(p, a, b)
        step = random_point(curve)
        if step[1] == 0:
            continue
        jump = curve.mul(TARGET_INDEX, step)

        for _ in range(MAX_GENERATION_TRIES):
            u, v = random_point(curve), random_point(curve)
            if u == v or u == curve.neg(v):
                continue

            xs0, ps0 = orbit(curve, u, step, LANE_SAMPLES)
            xs1, ps1 = orbit(curve, v, step, LANE_SAMPLES)
            if len(xs0) != LANE_SAMPLES or len(xs1) != LANE_SAMPLES:
                continue
            if len(set(xs0 + xs1)) != OBSERVATION_COUNT:
                continue
            if any(point[0] == step[0] for point in ps0 + ps1):
                continue

            target0 = curve.add(u, jump)
            target1 = curve.add(v, jump)
            if target0 is None or target1 is None or target0[0] == target1[0]:
                continue

            mask = [0] * LANE_SAMPLES + [1] * LANE_SAMPLES
            rnd.shuffle(mask)
            pos = [0, 0]
            samples = []
            lanes = (xs0, xs1)
            for lane in mask:
                samples.append(lanes[lane][pos[lane]])
                pos[lane] += 1

            targets = target0[0], target1[0]
            hand_values = targets[mask[0]], targets[1 - mask[0]]
            return {
                "observations": samples,
                "hand_values": hand_values,
            }

    raise RuntimeError("could not make instance")
