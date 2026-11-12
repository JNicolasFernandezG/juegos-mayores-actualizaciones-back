import logging
from typing import List, Dict, Any, Optional, Union

from app.features.narrative.enums import (
    OperadorEnum,
    TipoCondicionEnum,
    TipoAccionEnum,
    TipoCalculoEnum,
    OperacionMatematicaEnum,
)
from app.features.narrative.schemas.rules_schemas import (
    CondicionSchema,
    AccionSchema,
    EfectoSchema,
    AccionReferenciadaSchema,
    PrimitivaOperacionEnum,
)
from app.features.narrative.engine.tag_state import quitar_origen, quitar_tag, registrar_tags

logger = logging.getLogger(__name__)


def evaluar_condicion(condicion: Any, run_data: Dict[str, Any]) -> bool:
    """
    Evalúa una condición individual contra el estado vivo de la partida.
    Acepta tanto una instancia de CondicionSchema como un dict de MongoDB.
    """
    if isinstance(condicion, dict):
        condicion = CondicionSchema(**condicion)

    tipo = condicion.tipo

    # 1. Comparación de Recurso Numérico (ej: "oro" >= 50)
    if tipo == TipoCondicionEnum.COMPARAR_RECURSO:
        clave = condicion.clave
        if not clave:
            return False
        recursos = run_data.get("recursos", {})
        valor_actual = float(recursos.get(clave, 0))
        valor_objetivo = float(condicion.valor or 0)
        return _comparar_valores(valor_actual, condicion.operador, valor_objetivo)

    # 2. Posesión de Personaje en la Corte Activa
    elif tipo == TipoCondicionEnum.TIENE_PERSONAJE:
        corte = list(run_data.get("afinidad", {}).keys()) or run_data.get("corte_activa", [])
        return condicion.personaje_id in corte

    # 3. Nivel de Afinidad con Personaje
    elif tipo == TipoCondicionEnum.AFINIDAD_PERSONAJE:
        personaje_id = condicion.personaje_id
        if not personaje_id:
            return False
        afinidades = run_data.get("afinidad", {})
        afinidad_actual = float(afinidades.get(personaje_id, 50))
        valor_objetivo = float(condicion.valor or 0)
        return _comparar_valores(afinidad_actual, condicion.operador, valor_objetivo)

    # 4. Posesión de un Tag Activo (de cartas o perks)
    elif tipo == TipoCondicionEnum.TIENE_TAG:
        tags = run_data.get("tags_activos", [])
        return condicion.tag in tags

    # 5. Posesión de Carta en Mano / Inventario
    elif tipo == TipoCondicionEnum.TIENE_CARTA:
        cartas = run_data.get("cartas_en_mano", [])
        return condicion.carta_id in cartas

    return False


def evaluar_condiciones(condiciones: List[Any], run_data: Dict[str, Any]) -> bool:
    """
    Evalúa una lista de condiciones bajo operador lógico AND.
    Si la lista está vacía, se considera True.
    """
    if not condiciones:
        return True
    return all(evaluar_condicion(c, run_data) for c in condiciones)


def _comparar_valores(actual: float, operador: Optional[OperadorEnum], objetivo: float) -> bool:
    """
    Compara dos valores flotantes utilizando el operador relacional provisto.
    """
    if operador == OperadorEnum.MAYOR_IGUAL:
        return actual >= objetivo
    elif operador == OperadorEnum.MENOR_IGUAL:
        return actual <= objetivo
    elif operador == OperadorEnum.MAYOR:
        return actual > objetivo
    elif operador == OperadorEnum.MENOR:
        return actual < objetivo
    elif operador == OperadorEnum.IGUAL:
        return actual == objetivo
    elif operador == OperadorEnum.DISTINTO:
        return actual != objetivo
    return False



def _aplicar_operacion_matematica(
    actual: float,
    operacion: Optional[Union[OperacionMatematicaEnum, str]],
    valor: float,
) -> float:
    """
    Aplica una operación matemática configurada sobre un valor numérico:
    - sumar: actual + valor
    - restar: actual - valor
    - multiplicar: actual * valor
    - dividir: actual / valor (con salvaguarda por división entre 0)
    - porcentual: actual + (actual * (valor / 100))
    - fijar: valor
    """
    op = operacion.value if hasattr(operacion, "value") else str(operacion or "sumar").lower()
    if op == "sumar":
        return actual + valor
    elif op == "restar":
        return actual - valor
    elif op == "multiplicar":
        return actual * valor
    elif op == "dividir":
        if valor == 0:
            logger.warning("División por cero detectada en mutar_estado; se mantiene el valor actual.")
            return actual
        return actual / valor
    elif op == "porcentual":
        return actual + (actual * (valor / 100.0))
    elif op == "fijar":
        return valor
    return actual + valor

def _extraer_primitiva_y_params(
    accion: Any,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
) -> tuple[str, Dict[str, Any]]:
    """
    Extrae la primitiva ejecutable y los parámetros normalizados tanto de
    AccionSchema (legacy) como de AccionReferenciadaSchema (nuevo desacoplado).
    """
    if isinstance(accion, AccionReferenciadaSchema):
        accion_id = accion.accion_id
        params = accion.parametros.model_dump()
    elif isinstance(accion, dict) and "accion_id" in accion:
        accion_id = accion["accion_id"]
        params = accion.get("parametros", {})
    elif isinstance(accion, AccionSchema):
        accion_id = accion.tipo.value
        params = {
            "clave": accion.clave,
            "valor": accion.valor,
            "tipo_calculo": accion.tipo_calculo.value if accion.tipo_calculo else "fijo",
            "personaje_id": accion.personaje_id,
            "tag": accion.tag,
            "destino": "portador" if not accion.personaje_id else "personaje",
        }
    elif isinstance(accion, dict) and "tipo" in accion:
        accion_id = accion["tipo"]
        params = {
            "clave": accion.get("clave"),
            "valor": accion.get("valor", 0),
            "tipo_calculo": accion.get("tipo_calculo", "fijo"),
            "personaje_id": accion.get("personaje_id"),
            "tag": accion.get("tag"),
            "destino": "portador" if not accion.get("personaje_id") else "personaje",
        }
    elif isinstance(accion, dict) and "primitiva" in accion:
        accion_id = accion["primitiva"]
        params = accion.get("parametros") if isinstance(accion.get("parametros"), dict) else {k: v for k, v in accion.items() if k != "primitiva"}
    else:
        return "", {}

    # Resolver la primitiva a través del catálogo si existe la referencia
    primitiva = accion_id
    if catalogo_acciones and accion_id in catalogo_acciones:
        cat_item = catalogo_acciones[accion_id]
        primitiva = cat_item.get("primitiva") or cat_item.get("tipo_accion") or accion_id

    return str(primitiva), params


def _resolver_limites(
    run_data: Dict[str, Any],
    clave: str,
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[tuple[float, float]]:
    """
    Devuelve (min, max) aplicables a un recurso. Prioriza los límites dinámicos de la
    partida, luego la definición del universo. Si ninguna fuente conoce el recurso,
    retorna None y el valor queda sin clampeo.
    """
    limite_run = (run_data.get("limites") or {}).get(clave)
    base = (recursos_definicion or {}).get(clave, {})
    if isinstance(limite_run, dict) and ("min" in limite_run or "max" in limite_run):
        return (
            float(limite_run.get("min", base.get("min", 0))),
            float(limite_run.get("max", base.get("max", 100))),
        )
    if base:
        return (float(base.get("min", 0)), float(base.get("max", 100)))
    return None


def aplicar_delta_recurso(
    run_data: Dict[str, Any],
    clave: str,
    delta: float,
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[int]:
    """
    Único punto de mutación de un recurso vivo de la partida.

    Amortigua las pérdidas con los modificadores pasivos, reclama contra los límites
    dinámicos y descarta la operación si la clave no es un recurso de la partida, para
    que una acción mal configurada no cree recursos fantasma en cero (que el colapso
    interpretaría como derrota).
    """
    recursos = run_data.setdefault("recursos", {})
    if clave not in recursos:
        logger.warning(
            "Acción narrativa descartada: '%s' no es un recurso de la partida.", clave
        )
        return None

    actual = float(recursos[clave])
    delta_efectivo = float(delta)
    if delta_efectivo < 0:
        for mod in run_data.get("modificadores_pasivos", []):
            if mod.get("tipo") == "amortiguar_danio" and (
                not mod.get("clave") or mod.get("clave") == clave
            ):
                reduccion = float(mod.get("reduccion_porcentual", 0))
                if 0 < reduccion <= 100:
                    delta_efectivo *= 1.0 - (reduccion / 100.0)

    nuevo_valor = actual + delta_efectivo
    limites = _resolver_limites(run_data, clave, recursos_definicion)
    if limites is not None:
        limite_min, limite_max = limites
        nuevo_valor = max(limite_min, min(limite_max, nuevo_valor))

    recursos[clave] = int(round(nuevo_valor))
    return recursos[clave]


def ejecutar_accion(
    accion: Any,
    run_data: Dict[str, Any],
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
    duenio_id: Optional[str] = None,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Modifica el estado en memoria de run_data según el tipo de acción.
    Soporta formato legacy AccionSchema y nuevo AccionReferenciadaSchema desacoplado.
    """
    primitiva, params = _extraer_primitiva_y_params(accion, catalogo_acciones)
    if not primitiva:
        return

    # 1. Modificar Recurso
    if primitiva in (TipoAccionEnum.MODIFICAR_RECURSO.value, PrimitivaOperacionEnum.MODIFICAR_RECURSO.value):
        clave = params.get("clave")
        if not clave:
            return
        recursos = run_data.setdefault("recursos", {})
        valor_actual = float(recursos.get(clave, 0))
        tipo_calc = params.get("tipo_calculo")
        valor_num = float(params.get("valor") or 0)

        if tipo_calc in (TipoCalculoEnum.PORCENTUAL.value, "porcentual"):
            delta = valor_actual * (valor_num / 100.0)
        else:
            delta = valor_num

        aplicar_delta_recurso(run_data, clave, delta, recursos_definicion)

    # 2. Modificar Afinidad con Personaje
    elif primitiva in (TipoAccionEnum.MODIFICAR_AFINIDAD.value, PrimitivaOperacionEnum.MODIFICAR_AFINIDAD.value):
        destino = params.get("destino", "personaje")
        afinidades = run_data.setdefault("afinidad", {})
        if destino == "portador":
            # "Portador" solo tiene sentido si el dueño es un personaje de la corte;
            # si es una carta, escribir en afinidad corromperia el estado con un id fantasma.
            personaje_target = duenio_id if duenio_id in afinidades else None
            if personaje_target is None:
                logger.warning(
                    "modificar_afinidad descartada: el portador '%s' no es un personaje de la corte.",
                    duenio_id,
                )
                return
        else:
            personaje_target = params.get("personaje_id")
        if not personaje_target:
            return
        actual = int(afinidades.get(personaje_target, 50))
        delta = int(float(params.get("valor") or 0))
        afinidades[personaje_target] = max(0, min(100, actual + delta))

    # 3. Otorgar Tag Pasivo
    elif primitiva in (TipoAccionEnum.OTORGAR_TAG.value, PrimitivaOperacionEnum.OTORGAR_TAG.value):
        tag = params.get("tag")
        if tag:
            if duenio_id:
                registrar_tags(run_data, duenio_id, [tag])
            else:
                tags = run_data.setdefault("tags_activos", [])
                if tag not in tags:
                    tags.append(tag)

    # 4. Remover Tag Pasivo
    elif primitiva == PrimitivaOperacionEnum.REMOVER_TAG.value:
        quitar_tag(run_data, params.get("tag"))

    # 5. Amortiguar Daño Pasivo
    elif primitiva in (TipoAccionEnum.AMORTIGUAR_DANIO.value, PrimitivaOperacionEnum.AMORTIGUAR_DANIO.value):
        clave = params.get("clave")
        reduccion = float(params.get("valor") or params.get("porcentaje") or 0)
        mods = run_data.setdefault("modificadores_pasivos", [])
        # Un mismo origen no puede acumular amortiguadores por disparar el efecto varias veces.
        existente = next(
            (m for m in mods
             if m.get("tipo") == "amortiguar_danio"
             and m.get("clave") == clave
             and m.get("fuente") == duenio_id),
            None,
        )
        if existente:
            existente["reduccion_porcentual"] = max(
                float(existente.get("reduccion_porcentual", 0)), reduccion
            )
        else:
            mods.append({
                "tipo": "amortiguar_danio",
                "clave": clave,
                "reduccion_porcentual": reduccion,
                "fuente": duenio_id,
            })

    # 6. Mutar Estado Genérico y Dinámico
    elif primitiva == PrimitivaOperacionEnum.MUTAR_ESTADO.value:
        ruta = params.get("ruta") or params.get("clave")
        if not ruta:
            return

        op_mat = params.get("operacion_matematica", OperacionMatematicaEnum.SUMAR.value)
        valor_num = float(params.get("valor") or 0.0)

        # A) Recursos: ruta 'recursos.<clave>' o clave directa de recurso
        if ruta.startswith("recursos.") or (recursos_definicion and ruta in recursos_definicion):
            clave_rec = ruta.split(".", 1)[1] if ruta.startswith("recursos.") else ruta
            recursos = run_data.get("recursos", {})
            if clave_rec not in recursos:
                logger.warning(
                    "mutar_estado descartado: la ruta '%s' no apunta a un recurso del universo.", ruta
                )
                return
            actual = float(recursos[clave_rec])
            nuevo_num = _aplicar_operacion_matematica(actual, op_mat, valor_num)
            aplicar_delta_recurso(run_data, clave_rec, nuevo_num - actual, recursos_definicion)

        # B) Límites dinámicos: 'limites.<clave>.min' o 'limites.<clave>.max'
        elif ruta.startswith("limites."):
            partes = ruta.split(".")
            if len(partes) >= 3:
                clave_rec = partes[1]
                sub_lim = partes[2]  # 'min' | 'max'
                lim_dict = run_data.setdefault("limites", {}).setdefault(clave_rec, {})

                default_lim = 0 if sub_lim == "min" else 100
                if recursos_definicion and clave_rec in recursos_definicion:
                    default_lim = recursos_definicion[clave_rec].get(sub_lim, default_lim)

                actual_lim = float(lim_dict.get(sub_lim, default_lim))
                nuevo_lim = int(round(_aplicar_operacion_matematica(actual_lim, op_mat, valor_num)))

                # Un limite invertido haria que el reclamp empuje el recurso hacia arriba.
                otro = "max" if sub_lim == "min" else "min"
                valor_otro = lim_dict.get(otro)
                if valor_otro is None:
                    valor_otro = (recursos_definicion or {}).get(clave_rec, {}).get(otro)
                if valor_otro is not None:
                    nuevo_lim = min(nuevo_lim, int(valor_otro)) if sub_lim == "min" else max(nuevo_lim, int(valor_otro))

                lim_dict[sub_lim] = nuevo_lim

                # Reclamping inmediato del recurso si quedó fuera del rango
                recursos = run_data.setdefault("recursos", {})
                if clave_rec in recursos:
                    res_val = float(recursos[clave_rec])
                    cur_min = float(lim_dict.get("min", (recursos_definicion or {}).get(clave_rec, {}).get("min", 0)))
                    cur_max = float(lim_dict.get("max", (recursos_definicion or {}).get(clave_rec, {}).get("max", 100)))
                    recursos[clave_rec] = int(max(cur_min, min(cur_max, res_val)))

        # C) Afinidad: 'afinidad.<target>'
        elif ruta.startswith("afinidad."):
            target = ruta.split(".", 1)[1]
            afinidades = run_data.setdefault("afinidad", {})
            if target in ("portador", "self", "me"):
                if duenio_id in afinidades:
                    target = duenio_id
                else:
                    logger.warning(
                        "mutar_estado descartado: '%s' no es personaje de la corte y no hay portador valido.",
                        ruta,
                    )
                    return
            if target and target in afinidades:
                actual_af = float(afinidades[target])
                nueva_af = _aplicar_operacion_matematica(actual_af, op_mat, valor_num)
                afinidades[target] = max(0, min(100, int(round(nueva_af))))

        # D) Variables arbitrarias del universo: 'variables.<clave>'
        elif ruta.startswith("variables."):
            var_clave = ruta.split(".", 1)[1]
            variables = run_data.setdefault("variables", {})
            actual_var = float(variables.get(var_clave, 0.0))
            nueva_var = _aplicar_operacion_matematica(actual_var, op_mat, valor_num)
            variables[var_clave] = round(nueva_var, 4)

    # 7. Mutar Estado de Entidad (Tag o Personaje)
    elif primitiva == PrimitivaOperacionEnum.MUTAR_ESTADO_ENTIDAD.value:
        entidad = (params.get("entidad") or "").lower()
        operacion = (params.get("operacion") or "").lower()
        id_entidad = params.get("id_entidad") or params.get("tag") or params.get("personaje_id")
        if not id_entidad:
            return

        # A) Entidad = Tag
        if entidad == "tag":
            if operacion in ("alta", "agregar"):
                if duenio_id:
                    registrar_tags(run_data, duenio_id, [id_entidad])
                else:
                    tags = run_data.setdefault("tags_activos", [])
                    if id_entidad not in tags:
                        tags.append(id_entidad)
            elif operacion in ("baja", "eliminar", "remover"):
                quitar_tag(run_data, id_entidad)

        # B) Entidad = Personaje
        elif entidad == "personaje":
            corte = run_data.setdefault("corte_activa", [])
            afinidades = run_data.setdefault("afinidad", {})

            if operacion in ("alta", "agregar"):
                if id_entidad not in corte:
                    corte.append(id_entidad)
                if id_entidad not in afinidades:
                    afinidades[id_entidad] = 50
                adq = run_data.setdefault("adquisiciones", {})
                if id_entidad not in adq:
                    adq[id_entidad] = {"mes": run_data.get("mes_actual", 1), "tipo": "personaje"}

            elif operacion in ("baja", "eliminar", "remover"):
                # Limpieza Total: Corte y afinidad
                if id_entidad in corte:
                    corte.remove(id_entidad)
                if id_entidad in afinidades:
                    del afinidades[id_entidad]

                # Purgar amortiguadores y modificadores pasivos del personaje
                mods = run_data.get("modificadores_pasivos", [])
                run_data["modificadores_pasivos"] = [
                    m for m in mods if m.get("fuente") != id_entidad
                ]

                # Retirar los tags que solo aportaba este personaje
                quitar_origen(run_data, id_entidad)



# Unico alias histórico del motor: el ciclo mensual se disparaba como 'cada_mes'
# y el catálogo de frecuencias lo nombra 'inicio_mes'.
_ALIAS_EVENTOS_MOTOR: Dict[str, str] = {
    "al_obtener": "al_obtener",
    "cada_mes": "inicio_mes",
    "mensual": "inicio_mes",
    "inicio_mes": "inicio_mes",
}


def _normalizar_evento_motor(valor: Any) -> str:
    crudo = valor.value if hasattr(valor, "value") else str(valor)
    return _ALIAS_EVENTOS_MOTOR.get(crudo, crudo)


def _resolver_evento_motor(
    frec_id: str,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Devuelve el evento del motor al que pertenece una frecuencia. El catálogo del
    universo manda: una frecuencia ausente o inactiva no dispara nada. Sin catálogo
    (motor V1 y pruebas puras) sólo se reconocen las claves históricas.
    """
    if catalogo_frecuencias is not None:
        item = catalogo_frecuencias.get(frec_id)
        if not item:
            return None
        return item.get("evento_motor")
    return _ALIAS_EVENTOS_MOTOR.get(frec_id)


def _frecuencia_coincide(
    efecto: EfectoSchema,
    disparador: Any,
    run_data: Dict[str, Any],
    duenio_id: Optional[str] = None,
    mes_actual: Optional[int] = None,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Determina si un efecto debe ejecutarse según el disparador del motor,
    evaluando si es 'al_obtener' o una periodicidad relativa calculada
    desde el mes de adquisición de la carta/personaje.
    """
    disp_valor = _normalizar_evento_motor(disparador)

    # Coincidencia directa por disparador legacy
    if efecto.disparador:
        if _normalizar_evento_motor(efecto.disparador) == disp_valor:
            return True

    frec_id = efecto.frecuencia_id
    if not frec_id:
        return False

    evento = _resolver_evento_motor(frec_id, catalogo_frecuencias)
    if evento is None or _normalizar_evento_motor(evento) != disp_valor:
        return False

    if disp_valor != "inicio_mes":
        return True

    # 2. Periodicidad relativa sobre el evento inicio_mes
    frec_item = (catalogo_frecuencias or {}).get(frec_id) or {}
    cada = max(1, int(frec_item.get("cada", 1) or 1))
    desfase = int(frec_item.get("desfase", 0) or 0)
    conteo_desde = frec_item.get("conteo_desde", "adquisicion")

    cur_mes = int(mes_actual or run_data.get("mes_actual", 1))

    if conteo_desde == "adquisicion" and duenio_id:
        adqs = run_data.get("adquisiciones", {})
        mes_adq = int(adqs.get(duenio_id, {}).get("mes", 1))
        delta = cur_mes - mes_adq
        # Dispara si pasó al menos 1 mes desde la adquisición y cumple el intervalo
        return delta > 0 and (delta - desfase) >= 0 and ((delta - desfase) % cada == 0)

    return (cur_mes - desfase) > 0 and ((cur_mes - desfase) % cada == 0)


def despachar_efectos(
    disparador: Any,
    run_data: Dict[str, Any],
    efectos: List[Any],
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
    duenio_id: Optional[str] = None,
    mes_actual: Optional[int] = None,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Filtra los efectos por el disparador solicitado, evalúa sus condiciones
    y ejecuta las acciones correspondientes mutando run_data.
    Soporta lista de acciones ordenadas y cálculo de periodicidad relativa.
    """
    for efecto_raw in efectos:
        if isinstance(efecto_raw, dict):
            efecto = EfectoSchema(**efecto_raw)
        else:
            efecto = efecto_raw

        if _frecuencia_coincide(
            efecto, disparador, run_data, duenio_id, mes_actual, catalogo_frecuencias
        ):
            if evaluar_condiciones(efecto.condiciones, run_data):
                # Ejecutar lista ordenada de acciones desacopladas
                if efecto.acciones:
                    for accion in efecto.acciones:
                        ejecutar_accion(
                            accion,
                            run_data,
                            recursos_definicion,
                            duenio_id=duenio_id,
                            catalogo_acciones=catalogo_acciones,
                        )
                # Fallback legacy si viniera únicamente `accion`
                elif efecto.accion:
                    ejecutar_accion(
                        efecto.accion,
                        run_data,
                        recursos_definicion,
                        duenio_id=duenio_id,
                        catalogo_acciones=catalogo_acciones,
                    )
