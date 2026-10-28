"""
Búsqueda rápida de patrones 11x11 solucionables usando filas válidas precomputadas.
Criterio: >= 15 palabras, >= 5 intersecciones, longitudes 3-10, <= 10 palabras de 3 letras.
"""
import json
import random
import sys
import time
from collections import Counter

sys.path.insert(0, ".")

from app.features.daily_challenges.crucigrama.solver import (
    _parse_template_slots,
    _solve_crucigrama_backtracking,
)

C = 11
OUT = "scripts/patrones_11x11_found.json"


def valid_runs(bits):
    runs = []
    i = 0
    while i < C:
        if not bits[i]:
            j = i
            while j < C and not bits[j]:
                j += 1
            runs.append(j - i)
            i = j
        else:
            i += 1
    return all(3 <= r <= 10 for r in runs)


ROWS = []
for mask in range(1 << C):
    bits = [bool(mask >> c & 1) for c in range(C)]
    if valid_runs(bits):
        ROWS.append("".join("#" if b else "." for b in bits))
PAL = [r for r in ROWS if r == r[::-1]]


def column_runs_ok(grid):
    for c in range(C):
        r = 0
        while r < C:
            if grid[r][c] != "#":
                s = r
                while r < C and grid[r][c] != "#":
                    r += 1
                if r - s < 3 or r - s > 10:
                    return False
            else:
                r += 1
    return True


def crossings(grid):
    slots, inter = _parse_template_slots(grid)
    crossed = sum(1 for s in slots if inter[s["id"]])
    return crossed


def gen(rng):
    while True:
        top = [rng.choice(ROWS) for _ in range(5)]
        center = rng.choice(PAL)
        grid = top + [center] + [top[4][::-1], top[3][::-1], top[2][::-1], top[1][::-1], top[0][::-1]]
        if not column_runs_ok(grid):
            continue
        slots, _ = _parse_template_slots(grid)
        dist = Counter(s["len"] for s in slots)
        nw = len(slots)
        if nw < 15:
            continue
        if dist.get(3, 0) > 10:
            continue
        return grid


def main():
    rng = random.Random(20261024)
    found = []
    tried = 0
    t0 = time.time()
    target = 10
    while len(found) < target and tried < 100000:
        tried += 1
        pat = gen(rng)
        slots, inter = _parse_template_slots(pat)
        nw = len(slots)
        dist = Counter(s["len"] for s in slots)
        ncross = sum(1 for s in slots if inter[s["id"]])
        if ncross < 5:
            continue
        sol = _solve_crucigrama_backtracking(
            slots, inter, rng, prefer_curated=False, max_nodes=200000
        )
        if sol is not None:
            found.append({"pattern": pat, "words": nw, "crossed": ncross, "dist": dict(sorted(dist.items()))})
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(found, f, ensure_ascii=False, indent=2)
            print(f"[{len(found)}] words={nw} crossed={ncross} dist={dict(sorted(dist.items()))} tried={tried} {time.time()-t0:.0f}s", flush=True)
            for row in pat:
                print("  ", row, flush=True)
        if tried % 2000 == 0:
            print(f"  ... tried={tried} found={len(found)} {time.time()-t0:.0f}s", flush=True)
    print(f"Done tried={tried} found={len(found)}", flush=True)


if __name__ == "__main__":
    main()
