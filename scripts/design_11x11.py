"""
Diseña patrones 11x11 simétricos (mitad superior + fila central palíndromo).
Reporta rachas y solucionabilidad.
"""
import random
import sys
from collections import Counter

sys.path.insert(0, ".")

from app.features.daily_challenges.crucigrama.solver import (
    _parse_template_slots,
    _solve_crucigrama_backtracking,
)

C = 11


def full(top5, center):
    r0, r1, r2, r3, r4 = top5
    return [
        r0, r1, r2, r3, r4, center,
        r4[::-1], r3[::-1], r2[::-1], r1[::-1], r0[::-1],
    ]


def report(name, top5, center, solve=False, budget=200000):
    pat = full(top5, center)
    slots, inter = _parse_template_slots(pat)
    dist = Counter(s["len"] for s in slots)
    nw = len(slots)
    minslot = min(dist) if dist else 0
    maxslot = max(dist) if dist else 0
    mid = sum(v for l, v in dist.items() if 4 <= l <= 9)
    ok = minslot >= 3 and maxslot <= 10
    print(f"[{name}] words={nw} min={minslot} max={maxslot} mid%={100*mid/max(nw,1):.0f} dist={dict(sorted(dist.items()))} {'VALID' if ok else 'BAD'}")
    for row in pat:
        print("    " + row)
    if ok and solve:
        sol = _solve_crucigrama_backtracking(
            slots, inter, random.Random(name), prefer_curated=False, max_nodes=budget
        )
        print(f"    -> solved={sol is not None}")
    print()


if __name__ == "__main__":
    # intentos de diseño: filas superiores (5) + fila central
    designs = {
        "D1": ([
            "#..##....#.",
            "#........#.",
            "...#....#..",
            "..#..##..#.",
            ".#...#...#.",
        ], "....#.#...."),
        "D2": ([
            "##..##..##.",
            ".#....#...#",
            "#.#......#.",
            "..#.##..#..",
            "...#..#..#.",
        ], ".#...#...#."),
    }
    for k, (t, c) in designs.items():
        report(k, t, c, solve=True)
