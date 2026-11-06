"""
seed_narrative_v2_effects.py
Actualiza los personajes y cartas del universo canónico 'corte_medieval'
con efectos desacoplados, la primitiva mutar_estado (operaciones aditivas,
multiplicativas, porcentuales y fijas), frecuencias relativas y condiciones de aparición.
"""

import asyncio
import logging
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE_DIR)

from app.core.database import get_database, connect_to_mongo
from app.features.narrative.constants import (
    COLL_CHARACTERS,
    COLL_CARDS,
    COLL_CHALLENGES,
)
from app.features.narrative.enums import (
    CategoriaCartaEnum,
    DisparadorEnum,
    OperadorEnum,
    TipoCondicionEnum,
    TipoAccionEnum,
    OperacionMatematicaEnum,
)
from app.features.narrative.schemas.rules_schemas import (
    CondicionSchema,
    AccionReferenciadaSchema,
    ParametrosAccionSchema,
    EfectoSchema,
)

logger = logging.getLogger(__name__)
UNIVERSO_ID = "corte_medieval"


def get_updated_characters():
    return [
        {
            "_id": "pj_canciller_elena",
            "universo_id": UNIVERSO_ID,
            "nombre": "Elena de Valoria",
            "titulo": "Canciller del Reino",
            "imagen": "/assets/narrative/personajes/elena.webp",
            "descripcion": "Estratega política y hábil negociadora con los gremios de mercaderes.",
            "pros": ["Expande la capacidad del tesoro (+20 límite máximo).", "+15% de oro cada 2 meses si el pueblo está satisfecho."],
            "cons": ["Requiere estabilidad popular para que los gremios inviertan."],
            "tags": ["diplomacia", "comercio", "noble"],
            "afinidad_inicial": 50,
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="limites.oro.max",
                                operacion_matematica=OperacionMatematicaEnum.SUMAR,
                                valor=20.0,
                            ),
                        )
                    ],
                ).model_dump(),
                EfectoSchema(
                    frecuencia_id="cada_2_meses",
                    condiciones=[
                        CondicionSchema(
                            tipo=TipoCondicionEnum.COMPARAR_RECURSO,
                            clave="pueblo",
                            operador=OperadorEnum.MAYOR_IGUAL,
                            valor=40,
                        )
                    ],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="recursos.oro",
                                operacion_matematica=OperacionMatematicaEnum.PORCENTUAL,
                                valor=15.0,
                            ),
                        )
                    ],
                ).model_dump(),
            ],
            "conversaciones": [
                {"idConversacion": "conv_disputa_tesoro_militar", "probabilidad": 0.4}
            ],
        },
        {
            "_id": "pj_comandante_marcus",
            "universo_id": UNIVERSO_ID,
            "nombre": "Marcus Garra de Hierro",
            "titulo": "Capitán de la Guardia",
            "imagen": "/assets/narrative/personajes/marcus.webp",
            "descripcion": "Veterano de mil batallas. Mantiene el orden y la frontera con disciplina férrea.",
            "pros": ["+15 Ejército y absorbe 25% de bajas militares pasivas.", "Otorga tag disciplina_militar."],
            "cons": ["Consume 5 de oro mensual para el mantenimiento de su guardia."],
            "tags": ["militar", "combate", "orden"],
            "afinidad_inicial": 50,
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="ejercito", valor=15.0),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="amortiguar_danio",
                            parametros=ParametrosAccionSchema(clave="ejercito", valor=25.0),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="otorgar_tag",
                            parametros=ParametrosAccionSchema(tag="disciplina_militar"),
                        ),
                    ],
                ).model_dump(),
                EfectoSchema(
                    frecuencia_id="mensual",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="oro", valor=-5.0),
                        )
                    ],
                ).model_dump(),
            ],
            "conversaciones": [
                {"idConversacion": "conv_disputa_tesoro_militar", "probabilidad": 0.4},
                {"idConversacion": "conv_tregua_en_la_sombra", "probabilidad": 0.3},
            ],
        },
        {
            "_id": "pj_obispo_tomas",
            "universo_id": UNIVERSO_ID,
            "nombre": "Hermano Tomás",
            "titulo": "Obispo de la Catedral",
            "imagen": "/assets/narrative/personajes/tomas.webp",
            "descripcion": "Guía espiritual respetado por el clero y las masas campesinas.",
            "pros": ["Fija afinidad inicial alta (70).", "Aumenta +10 de Fe cada 2 meses."],
            "cons": ["Exige regularidad litúrgica y condena la herejía."],
            "tags": ["fe", "religion", "moral"],
            "afinidad_inicial": 70,
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="afinidad.portador",
                                operacion_matematica=OperacionMatematicaEnum.FIJAR,
                                valor=70.0,
                            ),
                        )
                    ],
                ).model_dump(),
                EfectoSchema(
                    frecuencia_id="cada_2_meses",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="fe", valor=10.0),
                        )
                    ],
                ).model_dump(),
            ],
            "conversaciones": [
                {"idConversacion": "conv_herejia_en_laboratorio", "probabilidad": 0.4}
            ],
        },
        {
            "_id": "pj_alquimista_vera",
            "universo_id": UNIVERSO_ID,
            "nombre": "Vera la Erudita",
            "titulo": "Alquimista de la Corte",
            "imagen": "/assets/narrative/personajes/vera.webp",
            "descripcion": "Estudiosa de pociones, remedios botánicos y secretos de la materia.",
            "pros": ["Otorga remedios_alquimia e incrementa variable conocimiento_alquimico.", "+15 Apoyo Popular trimestral."],
            "cons": ["Experimentos que levantan suspicacias."],
            "tags": ["ciencia", "salud", "alquimia"],
            "afinidad_inicial": 50,
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="otorgar_tag",
                            parametros=ParametrosAccionSchema(tag="remedios_alquimia"),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="variables.conocimiento_alquimico",
                                operacion_matematica=OperacionMatematicaEnum.SUMAR,
                                valor=1.0,
                            ),
                        ),
                    ],
                ).model_dump(),
                EfectoSchema(
                    frecuencia_id="cada_3_meses",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="recursos.pueblo",
                                operacion_matematica=OperacionMatematicaEnum.SUMAR,
                                valor=15.0,
                            ),
                        )
                    ],
                ).model_dump(),
            ],
            "conversaciones": [
                {"idConversacion": "conv_herejia_en_laboratorio", "probabilidad": 0.4}
            ],
        },
        {
            "_id": "pj_ladrona_sylvia",
            "universo_id": UNIVERSO_ID,
            "nombre": "Sylvia Niebla",
            "titulo": "Maestra de Espías",
            "imagen": "/assets/narrative/personajes/sylvia.webp",
            "descripcion": "Ojos y oídos en cada callejón y taberna del reino.",
            "pros": ["Otorga red_espias.", "Absorbe pasivamente 20% de pérdidas de oro."],
            "cons": ["Recelo de la alta nobleza."],
            "tags": ["espionaje", "intriga", "sombras"],
            "afinidad_inicial": 50,
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="otorgar_tag",
                            parametros=ParametrosAccionSchema(tag="red_espias"),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="amortiguar_danio",
                            parametros=ParametrosAccionSchema(clave="oro", valor=20.0),
                        ),
                    ],
                ).model_dump()
            ],
            "conversaciones": [
                {"idConversacion": "conv_tregua_en_la_sombra", "probabilidad": 0.3}
            ],
        },
    ]


def get_updated_cards():
    return [
        {
            "_id": "card_sello_real",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.ITEM.value,
            "nombre": "Sello Real de la Corona",
            "descripcion": "Autoridad suprema de la dinastía. Otorga tag sello_real y expande el límite máximo del tesoro en +30.",
            "imagen": "/assets/narrative/cards/sello.webp",
            "tags": ["sello_real", "autoridad"],
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="otorgar_tag",
                            parametros=ParametrosAccionSchema(tag="sello_real"),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="limites.oro.max",
                                operacion_matematica=OperacionMatematicaEnum.SUMAR,
                                valor=30.0,
                            ),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_reserva_trigo",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.ITEM.value,
            "nombre": "Reservas de Grano de Emergencia",
            "descripcion": "Silos protegidos: suma +20 de pueblo y establece un piso mínimo de reserva de 10.",
            "imagen": "/assets/narrative/cards/trigo.webp",
            "tags": ["comida", "abastecimiento"],
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="pueblo", valor=20.0),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="limites.pueblo.min",
                                operacion_matematica=OperacionMatematicaEnum.FIJAR,
                                valor=10.0,
                            ),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_escudo_hierro",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.ITEM.value,
            "nombre": "Escudos de Hierro Forjado",
            "descripcion": "Equipamiento pesado que reduce en un 35% las bajas militares pasivas y otorga +10 de ejército.",
            "imagen": "/assets/narrative/cards/escudo.webp",
            "tags": ["defensa", "militar"],
            "condiciones_aparicion": [
                CondicionSchema(
                    tipo=TipoCondicionEnum.COMPARAR_RECURSO,
                    clave="ejercito",
                    operador=OperadorEnum.MAYOR_IGUAL,
                    valor=25,
                ).model_dump()
            ],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="amortiguar_danio",
                            parametros=ParametrosAccionSchema(clave="ejercito", valor=35.0),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="ejercito", valor=10.0),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_diezmo_comercial",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.BONUS.value,
            "nombre": "Arancel Aduanero de la Ruta de la Seda",
            "descripcion": "Genera +20% de rendimiento porcentual de oro cada 2 meses si el tesoro tiene solvencia.",
            "imagen": "/assets/narrative/cards/arancel.webp",
            "tags": ["comercio", "economia"],
            "condiciones_aparicion": [
                CondicionSchema(
                    tipo=TipoCondicionEnum.COMPARAR_RECURSO,
                    clave="oro",
                    operador=OperadorEnum.MAYOR_IGUAL,
                    valor=40,
                ).model_dump()
            ],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="cada_2_meses",
                    condiciones=[
                        CondicionSchema(
                            tipo=TipoCondicionEnum.COMPARAR_RECURSO,
                            clave="pueblo",
                            operador=OperadorEnum.MAYOR_IGUAL,
                            valor=30,
                        ).model_dump()
                    ],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="recursos.oro",
                                operacion_matematica=OperacionMatematicaEnum.PORCENTUAL,
                                valor=20.0,
                            ),
                        )
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_tratado_paz",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.BONUS.value,
            "nombre": "Tratado Fronterizo de Paz",
            "descripcion": "Prosperidad comercial inmediata: multiplica el oro por 1.10 y otorga +15 de apoyo popular.",
            "imagen": "/assets/narrative/cards/tratado.webp",
            "tags": ["diplomacia", "paz"],
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="recursos.oro",
                                operacion_matematica=OperacionMatematicaEnum.MULTIPLICAR,
                                valor=1.10,
                            ),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="pueblo", valor=15.0),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_festival_cosecha",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.BONUS.value,
            "nombre": "Fiesta Patronal de Otoño",
            "descripcion": "Gran banquete: gasta 10 de oro pero otorga +25 de pueblo y +15 de fe.",
            "imagen": "/assets/narrative/cards/festival.webp",
            "tags": ["moral", "fiesta"],
            "condiciones_aparicion": [
                CondicionSchema(
                    tipo=TipoCondicionEnum.COMPARAR_RECURSO,
                    clave="pueblo",
                    operador=OperadorEnum.MAYOR_IGUAL,
                    valor=35,
                ).model_dump()
            ],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="oro", valor=-10.0),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="pueblo", valor=25.0),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="fe", valor=15.0),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_mercenarios",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.PERSONAJE.value,
            "nombre": "Compañía de Mercenarios Veteranos",
            "descripcion": "Espadas a sueldo: +25 ejército a cambio de 15 monedas de oro.",
            "imagen": "/assets/narrative/cards/mercenarios.webp",
            "tags": ["militar", "mercenarios"],
            "condiciones_aparicion": [
                CondicionSchema(
                    tipo=TipoCondicionEnum.COMPARAR_RECURSO,
                    clave="oro",
                    operador=OperadorEnum.MAYOR_IGUAL,
                    valor=30,
                ).model_dump()
            ],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="ejercito", valor=25.0),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="oro", valor=-15.0),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_remedio_herbario",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.ITEM.value,
            "nombre": "Boticario de Campaña",
            "descripcion": "Pociones y ungüentos que alivian epidemias: +15 de pueblo y tag salud_reino.",
            "imagen": "/assets/narrative/cards/pocion.webp",
            "tags": ["salud", "alquimia"],
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="modificar_recurso",
                            parametros=ParametrosAccionSchema(clave="pueblo", valor=15.0),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="otorgar_tag",
                            parametros=ParametrosAccionSchema(tag="salud_reino"),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_red_espias",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.BONUS.value,
            "nombre": "Red de Informantes Clandestina",
            "descripcion": "Otorga el tag red_espias y reduce un 15% de pérdidas pasivas de oro.",
            "imagen": "/assets/narrative/cards/espias.webp",
            "tags": ["espionaje", "informacion"],
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="otorgar_tag",
                            parametros=ParametrosAccionSchema(tag="red_espias"),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="amortiguar_danio",
                            parametros=ParametrosAccionSchema(clave="oro", valor=15.0),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_carretas_logistica",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.ITEM.value,
            "nombre": "Carretas de Logística y Transporte",
            "descripcion": "Mejora el despliegue militar: expande el límite de ejército en +20 y otorga logistica_militar.",
            "imagen": "/assets/narrative/cards/carreta.webp",
            "tags": ["logistica_militar", "transporte"],
            "condiciones_aparicion": [],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="otorgar_tag",
                            parametros=ParametrosAccionSchema(tag="logistica_militar"),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="limites.ejercito.max",
                                operacion_matematica=OperacionMatematicaEnum.SUMAR,
                                valor=20.0,
                            ),
                        ),
                    ],
                ).model_dump()
            ],
        },
        {
            "_id": "card_bendicion_papal",
            "universo_id": UNIVERSO_ID,
            "categoria": CategoriaCartaEnum.BONUS.value,
            "nombre": "Bula de Bendición Papal",
            "descripcion": "Consagración de la dinastía: multiplica la Fe por 1.25 y expande el límite de fe en +20.",
            "imagen": "/assets/narrative/cards/arancel.webp",
            "tags": ["fe", "religion", "sagrado"],
            "condiciones_aparicion": [
                CondicionSchema(
                    tipo=TipoCondicionEnum.COMPARAR_RECURSO,
                    clave="fe",
                    operador=OperadorEnum.MAYOR_IGUAL,
                    valor=45,
                ).model_dump()
            ],
            "efectos": [
                EfectoSchema(
                    frecuencia_id="al_obtener",
                    condiciones=[],
                    acciones=[
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="recursos.fe",
                                operacion_matematica=OperacionMatematicaEnum.MULTIPLICAR,
                                valor=1.25,
                            ),
                        ),
                        AccionReferenciadaSchema(
                            accion_id="mutar_estado",
                            parametros=ParametrosAccionSchema(
                                ruta="limites.fe.max",
                                operacion_matematica=OperacionMatematicaEnum.SUMAR,
                                valor=20.0,
                            ),
                        ),
                    ],
                ).model_dump()
            ],
        },
    ]


async def seed_v2_effects():
    await connect_to_mongo()
    db = get_database()
    print("Conectado a MongoDB...")

    # 1. Actualizar personajes (sin pisar imagen si ya fue personalizada)
    pjs = get_updated_characters()
    for p in pjs:
        set_data = {k: v for k, v in p.items() if k not in ("_id", "imagen")}
        await db[COLL_CHARACTERS].update_one(
            {"_id": p["_id"]},
            {
                "$set": set_data,
                "$setOnInsert": {"imagen": p["imagen"]}
            },
            upsert=True
        )
        print(f"[PJ] Upserted: {p['_id']} ({p['nombre']})")

    # 2. Actualizar cartas (sin pisar imagen si ya fue personalizada)
    cards = get_updated_cards()
    for c in cards:
        set_data = {k: v for k, v in c.items() if k not in ("_id", "imagen")}
        await db[COLL_CARDS].update_one(
            {"_id": c["_id"]},
            {
                "$set": set_data,
                "$setOnInsert": {"imagen": c["imagen"]}
            },
            upsert=True
        )
        print(f"[CARD] Upserted: {c['_id']} ({c['nombre']})")

    # 3. Asegurar que las cartas estén en los challenges activos de corte_medieval
    card_ids = [c["_id"] for c in cards]
    await db[COLL_CHALLENGES].update_many(
        {"game_id": "narrativo", "config.universo_id": UNIVERSO_ID},
        {"$addToSet": {"config.pool_cartas_mensuales_ids": {"$each": card_ids}}},
    )
    print("Challenges actualizados con nuevo pool de cartas.")
    print("¡ACTUALIZACIÓN V2 COMPLETADA EXITOSAMENTE!")


if __name__ == "__main__":
    asyncio.run(seed_v2_effects())
