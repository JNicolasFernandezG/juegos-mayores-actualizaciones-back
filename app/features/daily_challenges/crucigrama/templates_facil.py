"""
Catálogo de plantillas estructurales simétricas 7x7 para el Crucigrama fácil.
"""

from typing import Any, Dict, List

CRUCIGRAMA_TEMPLATES: List[Dict[str, Any]] = [
  {
    "id": 1,
    "theme": "Afectos y Familia",
    "pattern": [
      ".......",
      ".###.##",
      ".###.#.",
      ".###.#.",
      ".###.#.",
      "###....",
      "#######"
    ],
    "fallback_grid": [
      "HERMANO",
      "I###B##",
      "J###R#V",
      "O###A#I",
      "S###Z#D",
      "###ROSA",
      "#######"
    ]
  },
  {
    "id": 2,
    "theme": "La Cocina Criolla",
    "pattern": [
      "....###",
      "###.###",
      "#.#.##.",
      "#.#.##.",
      "#......",
      "#.####.",
      "#.####."
    ],
    "fallback_grid": [
      "ROSA###",
      "###G###",
      "#S#U##S",
      "#O#A##O",
      "#PASTEL",
      "#A####A",
      "#S####R"
    ]
  },
  {
    "id": 3,
    "theme": "En el Jardín",
    "pattern": [
      ".......",
      "####.#.",
      ".....#.",
      "##.#.#.",
      "##.#.#.",
      "##.#.##",
      "##.####"
    ],
    "fallback_grid": [
      "PLANTAS",
      "####I#O",
      "VERDE#L",
      "##O#M#A",
      "##S#P#R",
      "##A#O##",
      "##S####"
    ]
  },
  {
    "id": 4,
    "theme": "Costumbres y Mate",
    "pattern": [
      "#####.#",
      "....#.#",
      "##.##.#",
      "##.##.#",
      "......#",
      "##.####",
      ".....##"
    ],
    "fallback_grid": [
      "#####C#",
      "MATE#I#",
      "##I##E#",
      "##E##L#",
      "CAMINO#",
      "##P####",
      "AROMA##"
    ]
  },
  {
    "id": 5,
    "theme": "Tiempo y Recuerdos",
    "pattern": [
      "#.#####",
      "#.####.",
      "#.##.#.",
      "#.##.#.",
      ".......",
      "####.#.",
      "##....#"
    ],
    "fallback_grid": [
      "#N#####",
      "#O####A",
      "#C##V#G",
      "#H##E#U",
      "MEMORIA",
      "####D#S",
      "##AYER#"
    ]
  },
  {
    "id": 6,
    "theme": "Animales Nobles",
    "pattern": [
      ".......",
      "##.###.",
      "##.#.#.",
      "#....#.",
      "####.#.",
      "####.##",
      "####.##"
    ],
    "fallback_grid": [
      "TERNERO",
      "##O###V",
      "##S#N#E",
      "#GATO#J",
      "####C#A",
      "####H##",
      "####E##"
    ]
  },
  {
    "id": 7,
    "theme": "En la Escuela",
    "pattern": [
      ".......",
      "##.###.",
      "##.#.#.",
      "##.#.#.",
      "##.#.#.",
      "#.....#",
      "#######"
    ],
    "fallback_grid": [
      "LECCION",
      "##A###O",
      "##M#A#C",
      "##I#U#H",
      "##N#L#E",
      "#SOLAR#",
      "#######"
    ]
  },
  {
    "id": 8,
    "theme": "Ríos y Valles",
    "pattern": [
      ".###.##",
      ".###.#.",
      ".......",
      ".###.#.",
      ".###.#.",
      "######.",
      "#......"
    ],
    "fallback_grid": [
      "N###P##",
      "O###L#L",
      "CASCADA",
      "H###Z#G",
      "E###A#U",
      "######N",
      "#PIEDRA"
    ]
  },
  {
    "id": 9,
    "theme": "El Firmamento",
    "pattern": [
      "###.###",
      "###.#.#",
      ".##.#.#",
      ".##.#.#",
      "......#",
      ".####.#",
      "....###"
    ],
    "fallback_grid": [
      "###V###",
      "###E#R#",
      "S##R#A#",
      "O##D#Y#",
      "LUCERO#",
      "A####S#",
      "ROSA###"
    ]
  },
  {
    "id": 10,
    "theme": "Ropa y Abrigo",
    "pattern": [
      ".......",
      ".#.####",
      ".#.####",
      ".#.....",
      ".######",
      ".######",
      ".....##"
    ],
    "fallback_grid": [
      "CHALECO",
      "O#L####",
      "R#M####",
      "A#AMIGO",
      "Z######",
      "O######",
      "NOCHE##"
    ]
  },
  {
    "id": 11,
    "theme": "La Panadería",
    "pattern": [
      "#......",
      "######.",
      "######.",
      "##.###.",
      "#......",
      "##.####",
      "#......"
    ],
    "fallback_grid": [
      "#TRENZA",
      "######R",
      "######O",
      "##M###M",
      "#PANERA",
      "##S####",
      "#CAMINO"
    ]
  },
  {
    "id": 12,
    "theme": "Calles del Barrio",
    "pattern": [
      "##.####",
      "##.###.",
      "#....#.",
      "##.#.#.",
      ".......",
      "##.#.##",
      "####.##"
    ],
    "fallback_grid": [
      "##F####",
      "##L###V",
      "#ROSA#I",
      "##R#M#D",
      "AVENIDA",
      "##S#G##",
      "####O##"
    ]
  },
  {
    "id": 13,
    "theme": "En el Teatro",
    "pattern": [
      "......#",
      "##.####",
      "##.####",
      "##.....",
      "##.###.",
      "######.",
      "#......"
    ],
    "fallback_grid": [
      "MUSICA#",
      "##O####",
      "##L####",
      "##AROMA",
      "##R###L",
      "######M",
      "#BUTACA"
    ]
  },
  {
    "id": 14,
    "theme": "Cosas del Mar",
    "pattern": [
      "####.##",
      "##.#.##",
      "......#",
      ".#.#.##",
      ".#.####",
      ".#.....",
      "#######"
    ],
    "fallback_grid": [
      "####F##",
      "##P#A##",
      "VELERO#",
      "I#A#O##",
      "D#Z####",
      "A#AMIGO",
      "#######"
    ]
  },
  {
    "id": 15,
    "theme": "Hierbas y Aromas",
    "pattern": [
      "#####.#",
      "#.....#",
      "#####.#",
      ".####.#",
      ".......",
      ".####.#",
      ".....##"
    ],
    "fallback_grid": [
      "#####C#",
      "#AROMA#",
      "#####M#",
      "R####I#",
      "OREGANO",
      "S####O#",
      "AMIGO##"
    ]
  },
  {
    "id": 16,
    "theme": "Peces y Agua",
    "pattern": [
      ".##.###",
      ".##.###",
      ".......",
      ".##.#.#",
      ".####.#",
      "#.....#",
      "#######"
    ],
    "fallback_grid": [
      "P##A###",
      "L##G###",
      "ANZUELO",
      "Z##A#A#",
      "A####G#",
      "#CIELO#",
      "#######"
    ]
  },
  {
    "id": 17,
    "theme": "Herramientas",
    "pattern": [
      ".#.#.##",
      ".#.#.##",
      "......#",
      ".#.#.##",
      "##.....",
      "##.####",
      "#######"
    ],
    "fallback_grid": [
      "R#T#F##",
      "O#U#O##",
      "SIERRA#",
      "A#R#J##",
      "##CLAVO",
      "##A####",
      "#######"
    ]
  },
  {
    "id": 18,
    "theme": "Verduras y Huerta",
    "pattern": [
      "#.....#",
      "####.#.",
      ".###.#.",
      ".###.#.",
      ".......",
      ".###.#.",
      ".###.#."
    ],
    "fallback_grid": [
      "#PLAZA#",
      "####A#B",
      "N###P#A",
      "O###A#T",
      "CEBOLLA",
      "H###L#T",
      "E###O#A"
    ]
  },
  {
    "id": 19,
    "theme": "Dulzuras Caseras",
    "pattern": [
      ".......",
      ".#.####",
      ".#.####",
      ".#.....",
      ".######",
      "....###",
      "#######"
    ],
    "fallback_grid": [
      "ALFAJOR",
      "Z#L####",
      "U#A####",
      "C#NOCHE",
      "A######",
      "ROSA###",
      "#######"
    ]
  },
  {
    "id": 20,
    "theme": "Medios de Viaje",
    "pattern": [
      "......#",
      "####.#.",
      "#......",
      "#.##.#.",
      "#.####.",
      "#.####.",
      "#.#####"
    ],
    "fallback_grid": [
      "MALETA#",
      "####R#S",
      "#BOLETO",
      "#A##N#L",
      "#R####A",
      "#C####R",
      "#O#####"
    ]
  },
  {
    "id": 21,
    "theme": "Instrumentos",
    "pattern": [
      ".......",
      "###.###",
      "###.#.#",
      "###.#.#",
      "#......",
      "#####.#",
      "......#"
    ],
    "fallback_grid": [
      "CUERDAS",
      "###I###",
      "###T#C#",
      "###M#I#",
      "#FLORES",
      "#####L#",
      "CAMINO#"
    ]
  },
  {
    "id": 22,
    "theme": "El Dormitorio",
    "pattern": [
      "......#",
      "#####.#",
      "#.###.#",
      "......#",
      "#.#.###",
      "#.#.###",
      "###.###"
    ],
    "fallback_grid": [
      "SABANA#",
      "#####L#",
      "#R###M#",
      "COLCHA#",
      "#S#A###",
      "#A#M###",
      "###A###"
    ]
  },
  {
    "id": 23,
    "theme": "Colores Vivos",
    "pattern": [
      ".......",
      "#####.#",
      "#.....#",
      "#.###.#",
      "#.###.#",
      "#.....#",
      "#######"
    ],
    "fallback_grid": [
      "CELESTE",
      "#####I#",
      "#VERDE#",
      "#I###M#",
      "#D###P#",
      "#AMIGO#",
      "#######"
    ]
  },
  {
    "id": 24,
    "theme": "Paseos y Senderos",
    "pattern": [
      "......#",
      "####.##",
      "##.#.##",
      "##.#.##",
      "#....##",
      "##.####",
      "#......"
    ],
    "fallback_grid": [
      "COLINA#",
      "####O##",
      "##A#C##",
      "##M#H##",
      "#AIRE##",
      "##G####",
      "#BOSQUE"
    ]
  },
  {
    "id": 25,
    "theme": "Flores Silvestres",
    "pattern": [
      ".......",
      ".#####.",
      ".###.#.",
      ".###.#.",
      ".#.....",
      "####.##",
      "####.##"
    ],
    "fallback_grid": [
      "VIOLETA",
      "E#####M",
      "R###M#I",
      "D###A#G",
      "E#TALLO",
      "####V##",
      "####A##"
    ]
  },
  {
    "id": 26,
    "theme": "La Alacena",
    "pattern": [
      ".......",
      "##.###.",
      "##.#.#.",
      "##.#.#.",
      ".....#.",
      "####.##",
      "####.##"
    ],
    "fallback_grid": [
      "LENTEJA",
      "##O###M",
      "##C#A#I",
      "##H#R#G",
      "CIELO#O",
      "####M##",
      "####A##"
    ]
  },
  {
    "id": 27,
    "theme": "Sonidos del Día",
    "pattern": [
      "#......",
      "######.",
      "##.....",
      "#.####.",
      ".......",
      "#.#####",
      "#.#####"
    ],
    "fallback_grid": [
      "#CHARLA",
      "######R",
      "##RADIO",
      "#R####M",
      "NOTICIA",
      "#S#####",
      "#A#####"
    ]
  },
  {
    "id": 28,
    "theme": "Plantas de Hogar",
    "pattern": [
      "###.###",
      "###.###",
      "#.#.##.",
      "#.#.##.",
      ".......",
      "#.####.",
      ".....#."
    ],
    "fallback_grid": [
      "###V###",
      "###E###",
      "#C#R##A",
      "#I#D##R",
      "HELECHO",
      "#L####M",
      "SOLAR#A"
    ]
  },
  {
    "id": 29,
    "theme": "Juegos de Salón",
    "pattern": [
      "###....",
      "###.###",
      "#......",
      "#.#.#.#",
      "#.#.#.#",
      "#.###.#",
      "#.###.#"
    ],
    "fallback_grid": [
      "###VIDA",
      "###E###",
      "#CARTAS",
      "#I#D#M#",
      "#E#E#I#",
      "#L###G#",
      "#O###O#"
    ]
  },
  {
    "id": 30,
    "theme": "Oficios Nobles",
    "pattern": [
      "......#",
      "#####.#",
      "#.###.#",
      "#.###.#",
      ".......",
      "#.###.#",
      "#....##"
    ],
    "fallback_grid": [
      "MEDICO#",
      "#####F#",
      "#S###I#",
      "#O###C#",
      "ALBANIL",
      "#A###O#",
      "#ROSA##"
    ]
  },
  {
    "id": 31,
    "theme": "El Río Paraná",
    "pattern": [
      ".####.#",
      ".#.##.#",
      ".#.##.#",
      ".#.##.#",
      "......#",
      ".#.####",
      "##....."
    ],
    "fallback_grid": [
      "A####A#",
      "G#T##M#",
      "U#I##I#",
      "A#E##G#",
      "DORADO#",
      "A#R####",
      "##AROMA"
    ]
  }
]
