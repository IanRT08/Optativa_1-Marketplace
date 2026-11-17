"""
lambda-consultarMisPedidos
DFR 7.1 Consultar mis pedidos (Comprador): ID de orden, fecha, total y estado
de los pedidos del comprador de la sesión, con filtros opcionales por estado y
fecha.
Paginación: 20 por página, del más reciente al más antiguo, con cursor por
id_pedido (WHERE id_pedido < cursor ORDER BY id_pedido DESC).
Fechas (opción A de Ian): se guardan en hora de México (la conexión usa
time_zone = '-06:00'); el día se filtra tal cual y se devuelve con -06:00.
Ruta: GET /pedidos (token con rol Comprador).
Tablas: pedido, estado_pedido. No usa SP.
"""
import datetime
import re

from smavib_common import (
    MSG_SIN_REGISTROS,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_PEDIDOS = "No tienes pedidos registrados"  # DFR 7.1
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian

TAM_PAGINA = 20
ESTADOS = {e.lower(): e for e in ("Pendiente", "Enviado", "Entregado", "Cancelado", "Devuelto")}
# Hora de México (Ciudad de México): UTC-6 fijo, sin horario de verano desde 2022
ZONA_MEXICO = datetime.timezone(datetime.timedelta(hours=-6))  # para la etiqueta -06:00

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_TIENE_PEDIDOS = "SELECT 1 FROM pedido WHERE id_usuario = %s LIMIT 1"
SQL_BASE = """
    SELECT p.id_pedido, p.fecha, p.total, e.nombre AS estado
    FROM pedido p
    JOIN estado_pedido e ON e.id_estado = p.id_estado
    WHERE {condiciones}
    ORDER BY p.id_pedido DESC
    LIMIT %s
"""


def _rango_dia(texto):
    """'2026-11-14' -> (inicio, fin) del día; las fechas ya están en hora de México."""
    if not _RE_FECHA.fullmatch(texto):
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    try:
        dia = datetime.date.fromisoformat(texto)
    except ValueError:  # p. ej. 2026-02-30
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    inicio = datetime.datetime.combine(dia, datetime.time.min)
    return inicio, inicio + datetime.timedelta(days=1)


def _fecha_mexico(fecha):
    """datetime de RDS (ya en hora de México, sin zona) -> texto ISO con -06:00."""
    return fecha.replace(tzinfo=ZONA_MEXICO).isoformat()


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    id_usuario = sesion["id_usuario"]
    filtros = query_params(event)

    condiciones = ["p.id_usuario = %s"]
    parametros = [id_usuario]

    cursor_pagina = entero_positivo(filtros.get("cursor"))  # no válido -> primera página
    if cursor_pagina:
        condiciones.append("p.id_pedido < %s")
        parametros.append(cursor_pagina)

    estado_texto = (filtros.get("estado") or "").strip()
    if estado_texto:
        estado = ESTADOS.get(estado_texto.lower())
        if estado is None:
            raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
        condiciones.append("e.nombre = %s")
        parametros.append(estado)

    fecha_texto = (filtros.get("fecha") or "").strip()
    if fecha_texto:
        inicio, fin = _rango_dia(fecha_texto)
        condiciones.append("p.fecha >= %s AND p.fecha < %s")
        parametros.extend([inicio, fin])

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        sql = SQL_BASE.format(condiciones=" AND ".join(condiciones))
        cursor.execute(sql, (*parametros, TAM_PAGINA + 1))
        pedidos = list(cursor.fetchall())

        if not pedidos:
            cursor.execute(SQL_TIENE_PEDIDOS, (id_usuario,))
            mensaje = MSG_SIN_REGISTROS if cursor.fetchone() else MSG_SIN_PEDIDOS
            return ok(mensaje, pedidos=[], siguiente_cursor=None)

    siguiente_cursor = None
    if len(pedidos) > TAM_PAGINA:
        pedidos = pedidos[:TAM_PAGINA]
        siguiente_cursor = pedidos[-1]["id_pedido"]

    for pedido in pedidos:
        pedido["fecha"] = _fecha_mexico(pedido["fecha"])
    return ok(MSG_CONSULTA, pedidos=pedidos, siguiente_cursor=siguiente_cursor)
