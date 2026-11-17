"""
lambda-consultarHistorialCompras
DFR 7.4 Consultar historial de compras (Comprador): pedidos del periodo con
fecha, estado y total, y el total comprado (Cancelados y Devueltos no suman).
La consulta vive en sp_HistorialVentas (tipo 'Comprador'); la Lambda solo
valida el formato de las fechas y da forma a la respuesta. Restricción por
rol (el SP la deja a la aplicación): el id_usuario sale del token.
Reglas de Ian: "No tienes pedidos registrados" del SP -> 200 con lista vacía.
Las fechas se guardan en hora de México (opción A), así que el SP compara
los días correctos.
Ruta: GET /historial/compras (token con rol Comprador).
SP: sp_HistorialVentas(p_id_usuario, p_tipo, p_fecha_inicio, p_fecha_fin).
"""
import datetime
import re

import pymysql

from smavib_common import (
    ERRNO_SIGNAL,
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_PEDIDOS = "No tienes pedidos registrados"  # DFR 7.4 (lo da el SP)
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian

ZONA_MEXICO = datetime.timezone(datetime.timedelta(hours=-6))  # etiqueta -06:00
NO_SUMAN = ("Cancelado", "Devuelto")

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_SP = "CALL sp_HistorialVentas(%s, 'Comprador', %s, %s)"


def _fecha(texto):
    texto = (texto or "").strip()
    if not texto:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if not _RE_FECHA.fullmatch(texto):
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    try:
        return datetime.date.fromisoformat(texto)
    except ValueError:  # p. ej. 2026-02-30
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)


def _fecha_mexico(fecha):
    return fecha.replace(tzinfo=ZONA_MEXICO).isoformat()


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    filtros = query_params(event)

    if not (filtros.get("fecha_inicio") or "").strip() or not (filtros.get("fecha_fin") or "").strip():
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    fecha_inicio = _fecha(filtros.get("fecha_inicio"))
    fecha_fin = _fecha(filtros.get("fecha_fin"))
    # "La fecha inicial no puede ser mayor a la fecha final" lo valida el SP.

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_SP, (sesion["id_usuario"], fecha_inicio, fecha_fin))
            filas = list(cursor.fetchall())
            while cursor.nextset():  # deja libre la conexión que se reutiliza
                pass
    except pymysql.err.MySQLError as e:
        if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL and e.args[1] == MSG_SIN_PEDIDOS:
            return ok(MSG_SIN_PEDIDOS, pedidos=[], total_comprado=0)
        raise  # los demás mensajes del SP salen con 400 (manejar_errores)

    pedidos = []
    total_comprado = 0
    for fila in filas:
        if fila["pedido"] == "TOTAL":  # fila de WITH ROLLUP
            total_comprado = fila["total_comprado"]
            continue
        pedidos.append({
            "id_pedido": int(fila["pedido"]),
            "fecha": _fecha_mexico(fila["fecha"]),
            "estado": fila["estado"],
            "total": fila["total_pedido"],
            "suma_al_total": fila["estado"] not in NO_SUMAN,
        })

    return ok(MSG_CONSULTA, pedidos=pedidos, total_comprado=total_comprado)
