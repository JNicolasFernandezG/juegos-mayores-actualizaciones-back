"""Validación rápida del generador de crucigrama por crecimiento (sin RAE)."""
import random
import sys

sys.path.insert(0, ".")

from app.features.daily_challenges.crucigrama import solver as _solver
from app.features.daily_challenges.crucigrama.growth import generate_growth_board

_solver._init_word_index()
DICT = set()
for L in _solver._WORDS_BY_LEN:
    DICT.update(_solver._WORDS_BY_LEN[L])
print("indice:", {k: len(v) for k, v in _solver._WORDS_BY_LEN.items()})


def validate(rows, n):
    # 1. sin corridas de 2 letras; 2. toda corrida >=2 es palabra del diccionario
    def runs(seq):
        out = []
        i = 0
        while i < len(seq):
            if seq[i] != "#":
                j = i
                while j < len(seq) and seq[j] != "#":
                    j += 1
                if j - i >= 2:
                    out.append("".join(seq[i:j]))
                i = j
            else:
                i += 1
        return out

    all_words = []
    for r in range(n):
        all_words += runs(list(rows[r]))
    for c in range(n):
        all_words += runs([rows[r][c] for r in range(n)])

    bad = [w for w in all_words if len(w) < 3 or w not in DICT]
    return all_words, bad


def crossings(rows, n):
    cnt = 0
    for r in range(n):
        for c in range(n):
            if rows[r][c] == "#":
                continue
            h = (c > 0 and rows[r][c - 1] != "#") or (c < n - 1 and rows[r][c + 1] != "#")
            v = (r > 0 and rows[r - 1][c] != "#") or (r < n - 1 and rows[r + 1][c] != "#")
            if h and v:
                cnt += 1
    return cnt


ok = 0
for d in range(1, 21):
    date = f"2026-11-{d:02d}"
    rng = random.Random(f"crucigrama_{date}_dificil")
    res = generate_growth_board(11, rng, min_words=15, max_words=28)
    if res is None:
        print(f"{date}: FALLO (None)")
        continue
    rows, words = res
    all_words, bad = validate(rows, 11)
    cr = crossings(rows, 11)
    dist = {}
    for w in words:
        dist[len(w["word"])] = dist.get(len(w["word"]), 0) + 1
    status = "OK" if not bad and len(words) >= 15 and cr >= 5 else "MAL"
    if status == "OK":
        ok += 1
    print(f"{date}: palabras={len(words)} cruces={cr} dist={dict(sorted(dist.items()))} {status}")
    if bad:
        print("   palabras invalidas:", bad[:5])

print(f"\nRESUMEN: {ok}/20 tableros válidos")
