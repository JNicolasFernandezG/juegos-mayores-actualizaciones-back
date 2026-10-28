"""
Valida y prueba patrones 10x10 escritos a mano.
Uso: .venv/Scripts/python.exe scripts/test_hand_patterns.py
"""
import random
import sys
from collections import Counter

sys.path.insert(0, ".")

from app.features.daily_challenges.crucigrama.solver import (
    _parse_template_slots,
    _solve_crucigrama_backtracking,
)

R = C = 10

CANDIDATES = {
    "A": [
        "#...##...#",
        "...#....#.",
        "..#..##..#",
        ".#.....#..",
        "..........",
        "..........",
        ".#.....#..",
        "..#..##..#",
        "...#....#.",
        "#...##...#",
    ],
    "B": [
        "##..##..##",
        ".##....##.",
        "#..#..#..#",
        "....##....",
        ".#......#.",
        ".#......#.",
        "....##....",
        "#..#..#..#",
        ".##....##.",
        "##..##..##",
    ],
    "C": [
        "#..##..#..",
        "#..#....#.",
        "..##..##..",
        ".#.#..#.#.",
        "..#....#..",
        "..#....#..",
        ".#.#..#.#.",
        "..##..##..",
        ".#....#..#",
        "..##..##..",
    ],
    "D": [
        ".##....##.",
        "#..##..#..",
        "..#....#..",
        "##......##",
        ".#......#.",
        ".#......#.",
        "##......##",
        "..#....#..",
        "#..##..#..",
        ".##....##.",
    ],
}


def check(name, pat):
    sym = all(pat[r][c] == pat[R - 1 - r][C - 1 - c] for r in range(R) for c in range(C))
    slots, inter = _parse_template_slots(pat)
    dist = Counter(s["len"] for s in slots)
    nwords = len(slots)
    minslot = min(dist) if dist else 0
    mid = sum(v for l, v in dist.items() if 4 <= l <= 9)
    print(f"[{name}] sym={sym} words={nwords} min_len={minslot} dist={dict(sorted(dist.items()))}")
    if not sym:
        return
    if minslot < 3:
        print(f"    -> REJECT: runa < 3 letras")
        return
    sol = _solve_crucigrama_backtracking(
        slots, inter, random.Random("hand" + name), prefer_curated=False, max_nodes=250000
    )
    print(f"    -> solved={sol is not None}")


for k, v in CANDIDATES.items():
    check(k, v)
