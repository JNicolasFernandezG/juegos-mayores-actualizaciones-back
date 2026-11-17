"""
seed_narrative.py
Bootstrap manual de contenido para el juego narrativo (Crónicas de la Corte Real).
Carga universo, personajes y cartas en una base vacía.
El arranque de la app solo asegura el universo: personajes y cartas los opera el admin.
"""

import asyncio
import logging
from datetime import datetime
from typing import List

from app.core.database import connect_to_mongo, get_database
from app.features.narrative.admin.challenge_service import generar_mes_narrativo
from app.features.narrative.constants import (
    COLL_CARDS,
    COLL_CHARACTERS,
    COLL_SETTINGS,
)
from app.features.narrative.enums import (
    CategoriaCartaEnum,
    DisparadorEnum,
    OperadorEnum,
    TipoAccionEnum,
    TipoCondicionEnum,
)
from app.features.narrative.schemas import (
    AccionSchema,
    CartaCreateRequest,
    CondicionSchema,
    EfectoSchema,
    PersonajeCreateRequest,
    RecursoDefinicionSchema,
    UniversoCreateRequest,
)

logger = logging.getLogger(__name__)

UNIVERSO_ID = "corte_medieval"


async def _insertar_si_no_existe(collection_name: str, item) -> None:
    """Siembra inicial idempotente: nunca pisa documentos existentes ni el flag ``motor``."""
    doc = item.model_dump(by_alias=True)
    await get_database()[collection_name].update_one(
        {"_id": doc["_id"]},
        {"$setOnInsert": doc},
        upsert=True,
    )


def _universo_seed() -> UniversoCreateRequest:
    return UniversoCreateRequest(
        _id=UNIVERSO_ID,
        nombre="Crónicas de la Corte Real",
        descripcion="Gobierna un reino feudal equilibrando las arcas, la fe, el ejército y el apoyo popular.",
        icono="crown",
        motor="v2",
        reciclaje_eventos_v2=True,
        recursos=[
            RecursoDefinicionSchema(clave="oro", nombre="Tesoro Real", icono="coins", min=0, max=100, inicial=50),
            RecursoDefinicionSchema(clave="pueblo", nombre="Apoyo Popular", icono="users", min=0, max=100, inicial=50),
            RecursoDefinicionSchema(clave="ejercito", nombre="Fuerza Militar", icono="shield", min=0, max=100, inicial=50),
            RecursoDefinicionSchema(clave="fe", nombre="Fervor Religioso", icono="church", min=0, max=100, inicial=50),
        ],
    )


def _personajes_seed() -> List[PersonajeCreateRequest]:
    return [
        PersonajeCreateRequest(
            _id="pj_canciller_elena",
            universo_id=UNIVERSO_ID,
            nombre="Elena de Valoria",
            titulo="Canciller del Reino",
            imagen="/assets/narrative/personajes/elena.webp",
            descripcion="Estratega política y hábil negociadora con los gremios de mercaderes.",
            pros=["+15% de oro en eventos comerciales.", "Desbloquea opciones diplomáticas pacíficas."],
            cons=["-5 de apoyo popular cuando se priorizan tropas."],
            tags=["diplomacia", "comercio", "noble"],
            afinidad_inicial=50,
            efectos=[
                EfectoSchema(
                    disparador=DisparadorEnum.CADA_MES,
                    condiciones=[],
                    accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="oro", valor=10),
                )
            ],
        ),
        PersonajeCreateRequest(
            _id="pj_comandante_marcus",
            universo_id=UNIVERSO_ID,
            nombre="Marcus Garra de Hierro",
            titulo="Capitán de la Guardia",
            imagen="/assets/narrative/personajes/marcus.webp",
            descripcion="Veterano de mil batallas. Mantiene el orden y la frontera con disciplina férrea.",
            pros=["+15 de Fuerza Militar inmediata al reclutarlo.", "Aumenta chances de éxito en combate."],
            cons=["Consume 5 de oro cada mes para el pago de su guardia."],
            tags=["militar", "combate", "orden"],
            afinidad_inicial=50,
            efectos=[
                EfectoSchema(
                    disparador=DisparadorEnum.AL_OBTENER,
                    condiciones=[],
                    accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="ejercito", valor=15),
                ),
                EfectoSchema(
                    disparador=DisparadorEnum.CADA_MES,
                    condiciones=[],
                    accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="oro", valor=-5),
                ),
            ],
        ),
        PersonajeCreateRequest(
            _id="pj_obispo_tomas",
            universo_id=UNIVERSO_ID,
            nombre="Hermano Tomás",
            titulo="Obispo de la Catedral",
            imagen="/assets/narrative/personajes/tomas.webp",
            descripcion="Guía espiritual respetado por el clero y las masas campesinas.",
            pros=["Aumenta la Fe mensualmente.", "Reduce el descontento en épocas de sequía."],
            cons=["Desconfía de la ciencia y exige diezmos regulares."],
            tags=["fe", "religion", "moral"],
            afinidad_inicial=50,
            efectos=[
                EfectoSchema(
                    disparador=DisparadorEnum.CADA_MES,
                    condiciones=[],
                    accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="fe", valor=5),
                )
            ],
        ),
        PersonajeCreateRequest(
            _id="pj_alquimista_vera",
            universo_id=UNIVERSO_ID,
            nombre="Vera la Erudita",
            titulo="Alquimista de la Corte",
            imagen="/assets/narrative/personajes/vera.webp",
            descripcion="Estudiosa de pociones, remedios botánicos y secretos de la materia.",
            pros=["Cura plagas y suministra remedios al pueblo.", "Desbloquea opciones secretas científicas."],
            cons=["Sus experimentos levantan sospechas entre los religiosos (-5 Fe inicial)."],
            tags=["ciencia", "salud", "alquimia"],
            afinidad_inicial=50,
            efectos=[
                EfectoSchema(
                    disparador=DisparadorEnum.AL_OBTENER,
                    condiciones=[],
                    accion=AccionSchema(tipo=TipoAccionEnum.OTORGAR_TAG, tag="remedios_alquimia"),
                )
            ],
        ),
        PersonajeCreateRequest(
            _id="pj_ladrona_sylvia",
            universo_id=UNIVERSO_ID,
            nombre="Sylvia Niebla",
            titulo="Maestra de Espías",
            imagen="/assets/narrative/personajes/sylvia.webp",
            descripcion="Ojos y oídos en cada callejón y taberna del reino.",
            pros=["Anticipa conspiraciones y rebeliones.", "Desbloquea opciones secretas de intriga."],
            cons=["Los nobles desconfían de su presencia en palacio."],
            tags=["espionaje", "intriga", "sombras"],
            afinidad_inicial=50,
            efectos=[
                EfectoSchema(
                    disparador=DisparadorEnum.AL_OBTENER,
                    condiciones=[],
                    accion=AccionSchema(tipo=TipoAccionEnum.OTORGAR_TAG, tag="red_espias"),
                )
            ],
        ),
    ]


def _cartas_seed() -> List[CartaCreateRequest]:
    return [
        CartaCreateRequest(
            _id="card_sello_real",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.ITEM,
            nombre="Sello Real de la Corona",
            descripcion="Permite emitir decretos supremos y confiscar bienes con autoridad divina.",
            imagen="/assets/narrative/cards/sello.webp",
            tags=["sello_real", "autoridad"],
            efectos=[EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.OTORGAR_TAG, tag="sello_real"))],
        ),
        CartaCreateRequest(
            _id="card_reserva_trigo",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.ITEM,
            nombre="Reservas de Grano de Emergencia",
            descripcion="Silos sellados que abastecen a la población en momentos de hambruna.",
            imagen="/assets/narrative/cards/trigo.webp",
            tags=["comida", "abastecimiento"],
            efectos=[EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="pueblo", valor=15))],
        ),
        CartaCreateRequest(
            _id="card_escudo_hierro",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.ITEM,
            nombre="Escudos de Hierro Forjado",
            descripcion="Equipamiento pesado que fortalece la línea defensiva del ejército.",
            imagen="/assets/narrative/cards/escudo.webp",
            tags=["defensa", "militar"],
            efectos=[EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="ejercito", valor=10))],
        ),
        CartaCreateRequest(
            _id="card_carretas_logistica",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.ITEM,
            nombre="Carretas de Logística y Transporte",
            descripcion="Mejora el desplazamiento de tropas y víveres por todo el reino.",
            imagen="/assets/narrative/cards/carreta.webp",
            tags=["logistica_militar", "transporte"],
            efectos=[EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.OTORGAR_TAG, tag="logistica_militar"))],
        ),
        CartaCreateRequest(
            _id="card_diezmo_comercial",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.BONUS,
            nombre="Arancel Aduanero Favorable",
            descripcion="Genera +10 de oro cada mes si el apoyo popular se mantiene >= 40.",
            imagen="/assets/narrative/cards/arancel.webp",
            tags=["comercio", "economia"],
            efectos=[
                EfectoSchema(
                    disparador=DisparadorEnum.CADA_MES,
                    condiciones=[CondicionSchema(tipo=TipoCondicionEnum.COMPARAR_RECURSO, clave="pueblo", operador=OperadorEnum.MAYOR_IGUAL, valor=40)],
                    accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="oro", valor=10),
                )
            ],
        ),
        CartaCreateRequest(
            _id="card_tratado_paz",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.BONUS,
            nombre="Tratado Fronterizo de No Agresión",
            descripcion="Otorga estabilidad diplomática, sumando +10 de oro y +10 de pueblo.",
            imagen="/assets/narrative/cards/tratado.webp",
            tags=["diplomacia", "paz"],
            efectos=[
                EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="oro", valor=10)),
                EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="pueblo", valor=10)),
            ],
        ),
        CartaCreateRequest(
            _id="card_festival_cosecha",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.BONUS,
            nombre="Fiesta Patronal de Otoño",
            descripcion="Organiza banquetes públicos. Gasta 10 de oro pero otorga +20 de pueblo y +10 de fe.",
            imagen="/assets/narrative/cards/festival.webp",
            tags=["moral", "fiesta"],
            efectos=[
                EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="oro", valor=-10)),
                EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="pueblo", valor=20)),
                EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="fe", valor=10)),
            ],
        ),
        CartaCreateRequest(
            _id="card_mercenarios",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.PERSONAJE,
            nombre="Compañía de Mercenarios Veteranos",
            descripcion="Espadas a sueldo: +20 de fuerza militar inmediata a cambio de 15 monedas de oro.",
            imagen="/assets/narrative/cards/mercenarios.webp",
            tags=["militar", "mercenarios"],
            efectos=[
                EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="ejercito", valor=20)),
                EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="oro", valor=-15)),
            ],
        ),
        CartaCreateRequest(
            _id="card_remedio_herbario",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.ITEM,
            nombre="Boticario de Campaña",
            descripcion="Frascos de ungüentos y tónicos que mejoran la salud y alivian heridas.",
            imagen="/assets/narrative/cards/pocion.webp",
            tags=["salud", "alquimia"],
            efectos=[EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.MODIFICAR_RECURSO, clave="pueblo", valor=10))],
        ),
        CartaCreateRequest(
            _id="card_red_espias",
            universo_id=UNIVERSO_ID,
            categoria=CategoriaCartaEnum.BONUS,
            nombre="Red de Informantes Clandestina",
            descripcion="Otorga el tag pasivo 'red_espias' para detectar conspiraciones.",
            imagen="/assets/narrative/cards/espias.webp",
            tags=["espionaje", "informacion"],
            efectos=[EfectoSchema(disparador=DisparadorEnum.AL_OBTENER, condiciones=[], accion=AccionSchema(tipo=TipoAccionEnum.OTORGAR_TAG, tag="red_espias"))],
        ),
    ]


async def seed_universo_narrativo():
    """Asegura el universo base sin tocar personajes, cartas ni contenido del admin."""
    await _insertar_si_no_existe(COLL_SETTINGS, _universo_seed())


async def seed_narrative_game():
    """Bootstrap manual de una base vacía: universo, personajes y cartas.

    El arranque no ejecuta esta función; solo llama a ``seed_universo_narrativo``.
    """
    logger.info("[NARRATIVE SEED] Iniciando siembra de contenido narrativo...")

    # 1. UNIVERSO: Crónicas de la Corte Real
    await seed_universo_narrativo()

    # 2. PERSONAJES (5 iniciales) — solo bootstrap manual, nunca desde el arranque
    for personaje in _personajes_seed():
        await _insertar_si_no_existe(COLL_CHARACTERS, personaje)

    # 3. CARTAS (10 cartas variadas) — solo bootstrap manual, nunca desde el arranque
    for carta in _cartas_seed():
        await _insertar_si_no_existe(COLL_CARDS, carta)

    # 4. GENERAR EL MES ACTUAL EN daily_challenges
    ahora = datetime.now()
    res_mes = await generar_mes_narrativo(year=ahora.year, month=ahora.month, universo_id=UNIVERSO_ID)
    logger.info(
        f"[NARRATIVE SEED] Desafíos generados para {ahora.year}-{ahora.month:02d}: "
        f"{res_mes['desafios_creados']} días listos."
    )
    logger.info("[NARRATIVE SEED] ¡Siembra de contenido completada exitosamente!")


if __name__ == "__main__":
    async def main():
        await connect_to_mongo()
        await seed_narrative_game()

    asyncio.run(main())
