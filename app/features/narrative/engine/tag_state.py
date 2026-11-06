"""
Estado de tags con procedencia (`tags_origen`).

`tags_origen` mapea id de origen (personaje o carta) -> tags que aportó.
La baja de un personaje retira únicamente los tags que ningún otro origen activo aporta.
"""

from typing import Any, Dict, Iterable, List


def registrar_tags(run: Dict[str, Any], origen_id: str, tags: Iterable[str]) -> None:
    """Activa los tags de un origen y registra su procedencia."""
    if not origen_id:
        return
    origen = run.setdefault("tags_origen", {})
    propios = origen.setdefault(origen_id, [])
    activos = run.setdefault("tags_activos", [])
    for tag in tags:
        if not tag:
            continue
        if tag not in propios:
            propios.append(tag)
        if tag not in activos:
            activos.append(tag)


def quitar_tag(run: Dict[str, Any], tag: str) -> None:
    """Remueve un tag del estado y de toda procedencia: la baja es global."""
    if not tag:
        return
    activos = run.get("tags_activos", [])
    if tag in activos:
        activos.remove(tag)
    for propios in run.get("tags_origen", {}).values():
        if tag in propios:
            propios.remove(tag)


def quitar_origen(run: Dict[str, Any], origen_id: str) -> None:
    """Baja de un origen: apaga los tags que solo ese origen aportaba."""
    origen = run.get("tags_origen", {})
    aportados = origen.pop(origen_id, [])
    if not aportados:
        return
    ajenos = {tag for oid, tags in origen.items() if oid != origen_id for tag in tags}
    activos = run.get("tags_activos", [])
    for tag in aportados:
        if tag in ajenos:
            continue
        if tag in activos:
            activos.remove(tag)


async def sincronizar_personajes(run: Dict[str, Any], personaje_ids: Iterable[str], db) -> None:
    """Activa los tags estáticos de personajes activos que aún no tienen procedencia registrada."""
    from app.features.narrative.constants import COLL_CHARACTERS

    origen = run.setdefault("tags_origen", {})
    pendientes = [pid for pid in personaje_ids if pid and pid not in origen]
    if not pendientes:
        return

    docs = await db[COLL_CHARACTERS].find({"_id": {"$in": pendientes}}).to_list(None)
    encontrados = {str(doc["_id"]) for doc in docs}
    for doc in docs:
        registrar_tags(run, str(doc["_id"]), doc.get("tags") or [])
    for pid in pendientes:
        if pid not in encontrados:
            registrar_tags(run, pid, [])


def personajes_activos(run: Dict[str, Any]) -> List[str]:
    """Corte activa: la fuente de verdad es `afinidad`, con `corte_activa` como respaldo."""
    return list(run.get("afinidad", {}).keys()) or list(run.get("corte_activa", []))
