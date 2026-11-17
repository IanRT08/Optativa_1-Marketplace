"""
lambda-consultarPedidosAdmin
A3 (endpoint de apoyo aprobado por Ian, no está en el DFR): lista todos los
pedidos para que el administrador elija cuál actualizar con 7.3.
Filtros opcionales: estado y fecha (día en hora de México; las fechas se
guardan así), igual que 7.1. Flask abre la pantalla con estado=Pendiente (regla de Ian).
Muestra ID de orden, fecha (hora de México), total, estado y nombre del
comprador; sin dirección ni pago (eso está en 7.2 con datos reducidos).
Paginación: 20 por página, del más reciente al más antiguo (cursor id_pedido).
Ruta: GET /admin/pedidos (token con rol Administrador).
Tablas: pedido, estado_pedido, usuario. No usa SP.
"""
import datetime
import re

from smavib_common import (
    MSG_SIN_REGISTROS,
    ROL_ADMINISTRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian

TAM_PAGINA = 20
ESTADOS = {e.lower(): e for e in ("Pendiente", "Enviado", "Entregado", "Cancelado", "Devuelto")}
ZONA_MEXICO = datetime.timezone(datetime.timedelta(hours=-6))  # UTC-6 fijo

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_BASE = """
    SELECT p.id_pedido, p.fecha, p.total, e.nombre AS estado,
           u.nombre AS comprador_nombre, u.apellido AS comprador_apellido
    FROM pedido p
    JOIN estado_pedido e ON e.id_estado = p.id_estado
    JOIN usuario u ON u.id_usuario = p.id_usuario
    {donde}
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
    validar_token(event, roles=[ROL_ADMINISTRADOR])
    filtros = query_params(event)

    condiciones = []
    parametros = []

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

    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_BASE.format(donde=donde), (*parametros, TAM_PAGINA + 1))
        filas = list(cursor.fetchall())

    if not filas:
        return ok(MSG_SIN_REGISTROS, pedidos=[], siguiente_cursor=None)

    siguiente_cursor = None
    if len(filas) > TAM_PAGINA:
        filas = filas[:TAM_PAGINA]
        siguiente_cursor = filas[-1]["id_pedido"]

    pedidos = [
        {
            "id_pedido": f["id_pedido"],
            "fecha": _fecha_mexico(f["fecha"]),
            "total": f["total"],
            "estado": f["estado"],
            "comprador": f"{f['comprador_nombre']} {f['comprador_apellido']}",
        }
        for f in filas
    ]
    return ok(MSG_CONSULTA, pedidos=pedidos, siguiente_cursor=siguiente_cursor)
