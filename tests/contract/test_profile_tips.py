"""Consejos del perfil: lectura en el resumen y administración con CRUD."""

import pytest
import pytest_asyncio

from app.features.profile.consejos import (
    COLL_CONSEJOS,
    CONSEJOS_DEFAULT,
    asegurar_consejos_default,
)

pytestmark = pytest.mark.contract


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _consejo(**extra) -> dict:
    base = {
        "texto": "Leer todos los días ayuda a sostener la memoria.",
        "fuente": "Prueba, 2026",
        "url": "https://doi.org/10.1000/prueba",
        "orden": 10,
        "activo": True,
    }
    base.update(extra)
    return base


@pytest_asyncio.fixture
async def consejos_limpios(test_db, cleanup):
    await test_db[COLL_CONSEJOS].delete_many({})
    cleanup.add(COLL_CONSEJOS, {})
    return test_db[COLL_CONSEJOS]


@pytest.mark.asyncio
async def test_administracion_de_consejos_exige_operador(
    client, consejos_limpios, seeded_user, make_token
):
    assert (await client.get("/api/admin/profile/tips")).status_code == 401

    user = await seeded_user()
    headers = _auth(make_token(user["id"]))

    assert (await client.get("/api/admin/profile/tips", headers=headers)).status_code == 403
    assert (
        await client.post("/api/admin/profile/tips", headers=headers, json=_consejo())
    ).status_code == 403
    assert (
        await client.delete("/api/admin/profile/tips/cualquiera", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_admin_crea_edita_y_elimina_consejos(
    client, admin_override, consejos_limpios
):
    assert (await client.get("/api/admin/profile/tips")).json() == []

    creado = await client.post(
        "/api/admin/profile/tips", json=_consejo(situacion="eje_desequilibrado")
    )
    assert creado.status_code == 200, creado.text
    creado_body = creado.json()
    assert creado_body["id"]
    assert creado_body["texto"] == "Leer todos los días ayuda a sostener la memoria."
    assert creado_body["orden"] == 10
    assert creado_body["activo"] is True
    assert creado_body["situacion"] == "eje_desequilibrado"
    assert creado_body["updated_at"]

    editado = await client.put(
        f"/api/admin/profile/tips/{creado_body['id']}",
        json=_consejo(texto="  Texto nuevo  ", orden=5, activo=False),
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["texto"] == "Texto nuevo"
    assert editado.json()["orden"] == 5
    assert editado.json()["activo"] is False
    # Quitar la situación deja el consejo como general.
    assert editado.json()["situacion"] is None

    listado = (await client.get("/api/admin/profile/tips")).json()
    assert [consejo["id"] for consejo in listado] == [creado_body["id"]]

    eliminado = await client.delete(f"/api/admin/profile/tips/{creado_body['id']}")
    assert eliminado.status_code == 200, eliminado.text
    assert eliminado.json()["success"] is True
    assert (await client.get("/api/admin/profile/tips")).json() == []

    faltante = await client.delete(f"/api/admin/profile/tips/{creado_body['id']}")
    assert faltante.status_code == 404


@pytest.mark.asyncio
async def test_consejo_invalido_es_rechazado(client, admin_override, consejos_limpios):
    texto_vacio = await client.post(
        "/api/admin/profile/tips", json=_consejo(texto="   ")
    )
    assert texto_vacio.status_code == 422

    texto_excesivo = await client.post(
        "/api/admin/profile/tips", json=_consejo(texto="x" * 281)
    )
    assert texto_excesivo.status_code == 422

    url_relativa = await client.post(
        "/api/admin/profile/tips", json=_consejo(url="doi.org/10.1000/prueba")
    )
    assert url_relativa.status_code == 422

    orden_negativo = await client.post(
        "/api/admin/profile/tips", json=_consejo(orden=-1)
    )
    assert orden_negativo.status_code == 422

    situacion_desconocida = await client.post(
        "/api/admin/profile/tips", json=_consejo(situacion="inventada")
    )
    assert situacion_desconocida.status_code == 422


@pytest.mark.asyncio
async def test_resumen_expone_solo_consejos_activos_y_ordenados(
    client, consejos_limpios, seeded_user, make_token
):
    await consejos_limpios.insert_many(
        [
            _consejo(_id="segundo", orden=20),
            _consejo(_id="primero", orden=5, situacion="mes_en_mejora"),
            _consejo(_id="oculto", orden=1, activo=False),
            # Un documento legado sin la marca activo sigue siendo visible.
            {
                "_id": "legado",
                "texto": "Consejo sin marca de estado.",
                "fuente": "Prueba, 2025",
                "url": "https://doi.org/10.1000/legado",
                "orden": 30,
                # Un valor viejo o inválido no rompe el resumen: se descarta.
                "situacion": "inventada",
            },
        ]
    )
    user = await seeded_user()

    response = await client.get(
        "/api/profile/summary", headers=_auth(make_token(user["id"]))
    )

    assert response.status_code == 200, response.text
    consejos = response.json()["consejos"]
    assert [consejo["id"] for consejo in consejos] == ["primero", "segundo", "legado"]
    assert set(consejos[0]) == {"id", "texto", "fuente", "url", "situacion"}
    assert [consejo["situacion"] for consejo in consejos] == [
        "mes_en_mejora",
        None,
        None,
    ]


@pytest.mark.asyncio
async def test_siembra_solo_con_la_coleccion_vacia(consejos_limpios):
    assert await asegurar_consejos_default() == len(CONSEJOS_DEFAULT)

    sembrados = await consejos_limpios.find({}).to_list(length=None)
    assert len(sembrados) == len(CONSEJOS_DEFAULT)
    assert {doc["_id"] for doc in sembrados} == {
        consejo["_id"] for consejo in CONSEJOS_DEFAULT
    }
    assert all(doc.get("activo") is True for doc in sembrados)

    # Una segunda corrida no duplica.
    assert await asegurar_consejos_default() == 0

    # Una edición o borrado del admin no se revierte al volver a arrancar.
    primero, segundo = CONSEJOS_DEFAULT[0], CONSEJOS_DEFAULT[1]
    await consejos_limpios.update_one(
        {"_id": primero["_id"]}, {"$set": {"texto": "Editado por el operador"}}
    )
    await consejos_limpios.delete_one({"_id": segundo["_id"]})

    assert await asegurar_consejos_default() == 0
    assert (await consejos_limpios.find_one({"_id": primero["_id"]}))["texto"] == (
        "Editado por el operador"
    )
    assert await consejos_limpios.count_documents({}) == len(CONSEJOS_DEFAULT) - 1
