"""Benchmark statistics (Ticket-04 part 1). Pure stdlib, no I/O.

compute(dts_ms) -> {"frames", "avg_fps", "p1_low_fps", "frame_ms_p95"}  (all but frames rounded to 1 decimal)

- avg_fps       = 1000 * N / sum(dt)
- p1_low_fps    = k = max(1, ceil(0.01 * N)); mean of the k largest dt; 1000 / that mean
- frame_ms_p95  = nearest-rank 95th percentile: sorted(dt)[ceil(0.95 * N) - 1]
"""
import math


def _ceil(x):
    """ceil with a tiny tolerance so 0.01 * 100 (= 1.0000000000000002 in floats) stays 1."""
    return int(math.ceil(round(x, 9)))


def compute(dts_ms):
    dts = [float(d) for d in dts_ms]
    n = len(dts)
    if n == 0:
        raise ValueError("no frames measured")
    if any(not (0 <= d < math.inf) for d in dts):     # also rejects NaN
        raise ValueError("frame times must be finite and >= 0")
    total = sum(dts)
    if total <= 0:
        raise ValueError("frame times sum to zero")
    k = max(1, _ceil(0.01 * n))
    worst = sorted(dts, reverse=True)[:k]
    if sum(worst) <= 0:
        raise ValueError("frame times sum to zero")
    p95 = sorted(dts)[_ceil(0.95 * n) - 1]
    return {
        "frames": n,
        "avg_fps": round(1000.0 * n / total, 1),
        "p1_low_fps": round(1000.0 / (sum(worst) / k), 1),
        "frame_ms_p95": round(p95, 1),
    }
