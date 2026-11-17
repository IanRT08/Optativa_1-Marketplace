"""
lambda-reporteVentasVendedor
DFR 8.1 Reporte de ventas del vendedor (Vendedor): total de ventas y detalle
por producto en un rango de fechas, con precio unitario histórico; los
pedidos Cancelados y Devueltos no cuentan.
La consulta vive en sp_HistorialVentas (tipo 'Vendedor'); la Lambda valida el
formato de las fechas y da forma a la respuesta. Restricción por rol (el SP la
deja a la aplicación): el id del vendedor sale del token.
Regla de Ian (igual que 7.4): "No hay ventas en el periodo seleccionado" del
SP -> 200 con lista vacía.
La fila TOTAL del ROLLUP se detecta por id_producto nulo (no por el texto,
porque un producto podría llamarse "TOTAL").
Ruta: GET /vendedor/ventas (token con rol Vendedor).
SP: sp_HistorialVentas(p_id_usuario, p_tipo, p_fecha_inicio, p_fecha_fin).
"""
import datetime
import re

import pymysql

from smavib_common import (
    ERRNO_SIGNAL,
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_VENDEDOR,
    ErrorNegocio,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_VENTAS = "No hay ventas en el periodo seleccionado"  # DFR 8.1 (lo da el SP)
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_SP = "CALL sp_HistorialVentas(%s, 'Vendedor', %s, %s)"


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


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])
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
        if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL and e.args[1] == MSG_SIN_VENTAS:
            return ok(MSG_SIN_VENTAS, productos=[], total_ventas=0)
        raise  # los demás mensajes del SP salen con 400 (manejar_errores)

    productos = []
    total_ventas = 0
    for fila in filas:
        if fila["id_producto"] is None:  # fila TOTAL de WITH ROLLUP
            total_ventas = fila["total_vendido"]
            continue
        productos.append({
            "id_producto": fila["id_producto"],
            "producto": fila["producto"],
            "unidades_vendidas": fila["unidades_vendidas"],
            "total_vendido": fila["total_vendido"],
        })

    return ok(MSG_CONSULTA, productos=productos, total_ventas=total_ventas)
