"""
Busca patrones simétricos 10x10 solucionables para el Crucigrama difícil.
Todas las rachas (H y V) deben tener longitud >= 3.
Guarda los patrones encontrados en scripts/patrones_10x10_found.json.
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

R = C = 10
OUT = "scripts/patrones_10x10_found.json"


def symmetric(pattern):
    return all(
        pattern[r][c] == pattern[R - 1 - r][C - 1 - c]
        for r in range(R)
        for c in range(C)
    )


def runs_ok(pattern):
    """Todas las rachas horizontales y verticales con longitud >= 3."""
    for r in range(R):
        c = 0
        while c < C:
            if pattern[r][c] != "#":
                start = c
                while c < C and pattern[r][c] != "#":
                    c += 1
                if c - start < 3:
                    return False
            else:
                c += 1
    for c in range(C):
        r = 0
        while r < R:
            if pattern[r][c] != "#":
                start = r
                while r < R and pattern[r][c] != "#":
                    r += 1
                if r - start < 3:
                    return False
            else:
                r += 1
    return True


def gen_random_pattern(rng):
    """Patrón 10x10 con simetría 180°, rachas >= 3 y 15-28 palabras."""
    for _ in range(3000):
        target_blocks = rng.randint(20, 32)
        grid = [["."] * C for _ in range(R)]
        blocks = 0
        cells = [(r, c) for r in range(R) for c in range(C)]
        rng.shuffle(cells)
        for r, c in cells:
            if blocks >= target_blocks:
                break
            r2, c2 = R - 1 - r, C - 1 - c
            if (r, c) == (r2, c2):
                continue
            if grid[r][c] == "#" or grid[r2][c2] == "#":
                continue
            grid[r][c] = "#"
            grid[r2][c2] = "#"
            blocks += 2
            pat = ["".join(row) for row in grid]
            if not runs_ok(pat):
                grid[r][c] = "."
                grid[r2][c2] = "."
                blocks -= 2
        pat = ["".join(row) for row in grid]
        if not symmetric(pat):
            continue
        slots, _ = _parse_template_slots(pat)
        nwords = len(slots)
        dist = Counter(s["len"] for s in slots)
        if not (15 <= nwords <= 28):
            continue
        mid = sum(v for l, v in dist.items() if 4 <= l <= 9)
        if mid < 0.7 * nwords:
            continue
        return pat
    return None


def main():
    rng = random.Random(20261023)
    found = []
    tried = 0
    t0 = time.time()
    target = 10
    while len(found) < target and tried < 3000:
        tried += 1
        pat = gen_random_pattern(rng)
        if pat is None:
            continue
        slots, inter = _parse_template_slots(pat)
        nwords = len(slots)
        dist = Counter(s["len"] for s in slots)
        sol = _solve_crucigrama_backtracking(
            slots, inter, rng, prefer_curated=False, max_nodes=150000
        )
        if sol is not None:
            found.append({"pattern": pat, "words": nwords, "dist": dict(sorted(dist.items()))})
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(found, f, ensure_ascii=False, indent=2)
            print(f"[{len(found)}] words={nwords} dist={dict(sorted(dist.items()))} (tried={tried}, {time.time()-t0:.0f}s)")
            for row in pat:
                print("  ", row)
        if tried % 100 == 0:
            print(f"  ... tried={tried}, found={len(found)}, {time.time()-t0:.0f}s", flush=True)
    print(f"\nDone. tried={tried} found={len(found)} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
