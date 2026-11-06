import pytest
from app.features.narrative.schemas.catalog_schemas import TagCreateRequest, TagUpdateRequest
from app.features.narrative.admin.crud_service import (
    crear_o_actualizar_tag,
    obtener_tags,
    obtener_tag_por_id,
    eliminar_tag
)

@pytest.mark.asyncio
async def test_crud_tags_narrativos(test_db):
    # 1. Crear tag
    nuevo_tag = TagCreateRequest(
        _id="tag_test_estrategia",
        universo_id="corte_medieval",
        nombre="Estrategia Test",
        descripcion="Tag de prueba para validar CRUD",
        color="#3b82f6",
        categoria="militar"
    )
    creado = await crear_o_actualizar_tag(nuevo_tag)
    assert creado.id == "tag_test_estrategia"
    assert creado.nombre == "Estrategia Test"

    # 2. Obtener por ID
    recuperado = await obtener_tag_por_id("tag_test_estrategia")
    assert recuperado is not None
    assert recuperado.color == "#3b82f6"

    # 3. Listar tags
    tags = await obtener_tags(universo_id="corte_medieval")
    assert any(t.id == "tag_test_estrategia" for t in tags)

    # 4. Eliminar tag
    eliminado = await eliminar_tag("tag_test_estrategia")
    assert eliminado is True

    # 5. Verificar que ya no existe
    post_del = await obtener_tag_por_id("tag_test_estrategia")
    assert post_del is None
