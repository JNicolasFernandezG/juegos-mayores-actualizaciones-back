"""
Subpaquete Crucigrama: generador modular con dos dificultades.

- facil: 7x7 con plantillas simétricas + pistas curadas pedagógicas.
- dificil: 11x11 por crecimiento con definiciones formales de la RAE.

El contrato de salida (theme, grid_size, cells, words, total_words, date) es el
mismo para ambos niveles; solo varía `grid_size` y la fuente de las pistas.
"""

from app.features.daily_challenges.crucigrama.generator import (
    generate_crucigrama_challenge_for_date,
)

__all__ = ["generate_crucigrama_challenge_for_date"]
