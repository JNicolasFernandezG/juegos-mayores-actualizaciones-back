"""
Ayuda para diseñar patrones 10x10 simétricos: deriva la mitad inferior
por rotación 180° y reporta rachas y cantidad de palabras.
Uso: .venv/Scripts/python.exe scripts/design_10x10.py
"""
import sys
from collections import Counter

sys.path.insert(0, ".")

from app.features.daily_challenges.crucigrama.solver import _parse_template_slots

C = 10


def full_grid(top5):
    r0, r1, r2, r3, r4 = top5
    return [
        r0, r1, r2, r3, r4,
        r4[::-1], r3[::-1], r2[::-1], r1[::-1], r0[::-1],
    ]


def report(name, top5):
    pat = full_grid(top5)
    slots, _ = _parse_template_slots(pat)
    dist = Counter(s["len"] for s in slots)
    nwords = len(slots)
    minslot = min(dist) if dist else 0
    mid = sum(v for l, v in dist.items() if 4 <= l <= 9)
    flag = "OK" if (minslot >= 3 and 15 <= nwords <= 28 and mid >= 0.7 * nwords) else "  "
    print(f"[{name}] {flag} words={nwords} min={minslot} mid%={100*mid/max(nwords,1):.0f} dist={dict(sorted(dist.items()))}")
    for row in pat:
        print("    " + row)
    print()


if __name__ == "__main__":
    designs = {
        "P1": [
            ".#......#.",
            "#..#..#..#",
            "..##..##..",
            "....##....",
            "#..#..#..#",
        ],
        "P2": [
            "##......##",
            ".#..#..#..",
            "#..##..#..",
            ".#......#.",
            "..##..##..",
        ],
        "P3": [
            "#..##..#..",
            ".#....#..#",
            "##..#.##..",
            "..#..#...#",
            ".#..##..#.",
        ],
        "P4": [
            "..##....#.",
            ".#...#.#..",
            "....##....",
            "#.#....#.#",
            ".#..##..#.",
        ],
        "P5": [
            "....#.....",
            ".#...#...#",
            "..#..##...",
            "....##....",
            "#..#...#..",
        ],
    }
    for k, v in designs.items():
        report(k, v)
