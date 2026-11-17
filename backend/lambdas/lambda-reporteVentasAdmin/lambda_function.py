"""
lambda-reporteVentasAdmin
DFR 8.2 Reporte de ventas por vendedor (Administrador): mismas reglas de
cálculo y fechas que 8.1, para el vendedor que elija el administrador.
La consulta vive en sp_HistorialVentas (tipo 'Vendedor'); el SP deja la
restricción por rol a la aplicación: aquí solo entra el Administrador.
Reglas de Ian:
- id_vendedor inexistente, no válido o que no es Vendedor -> 404
  "El vendedor no existe" (evita un "No hay ventas" engañoso). Un vendedor
  Inactivo sí se consulta (su historial sigue siendo válido).
- "No hay ventas en el periodo seleccionado" del SP -> 200 con lista vacía.
La fila TOTAL del ROLLUP se detecta por id_producto nulo.
Ruta: GET /admin/ventas (token con rol Administrador).
Tablas: usuario, rol. SP: sp_HistorialVentas(p_id_usuario, p_tipo, p_fecha_inicio, p_fecha_fin).
"""
import datetime
import re

import pymysql

from smavib_common import (
    ERRNO_SIGNAL,
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_ADMINISTRADOR,
    ROL_VENDEDOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_VENTAS = "No hay ventas en el periodo seleccionado"  # DFR 8.1 (lo da el SP)
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian
MSG_VENDEDOR_NO_EXISTE = "El vendedor no existe"  # aprobado por Ian

ID_MAX = 4294967295  # INT UNSIGNED de p_id_usuario

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_VENDEDOR = """
    SELECT u.nombre, u.apellido
    FROM usuario u
    JOIN rol r ON r.id_rol = u.id_rol
    WHERE u.id_usuario = %s AND r.nombre = %s
"""
SQL_SP = "CALL sp_HistorialVentas(%s, 'Vendedor', %s, %s)"


def _vacio(valor):
    return not (valor or "").strip()


def _fecha(texto):
    texto = (texto or "").strip()
    if not _RE_FECHA.fullmatch(texto):
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    try:
        return datetime.date.fromisoformat(texto)
    except ValueError:  # p. ej. 2026-02-30
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)


@manejar_errores
def lambda_handler(event, context):
    validar_token(event, roles=[ROL_ADMINISTRADOR])  # DFR 8.2: solo el administrador
    filtros = query_params(event)

    if any(_vacio(filtros.get(c)) for c in ("id_vendedor", "fecha_inicio", "fecha_fin")):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    fecha_inicio = _fecha(filtros.get("fecha_inicio"))
    fecha_fin = _fecha(filtros.get("fecha_fin"))
    # "La fecha inicial no puede ser mayor a la fecha final" lo valida el SP.

    id_vendedor = entero_positivo(filtros.get("id_vendedor"))
    if id_vendedor is None or id_vendedor > ID_MAX:
        raise ErrorNegocio(404, MSG_VENDEDOR_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_VENDEDOR, (id_vendedor, ROL_VENDEDOR))
        vendedor = cursor.fetchone()
    if vendedor is None:
        raise ErrorNegocio(404, MSG_VENDEDOR_NO_EXISTE)
    nombre_vendedor = f"{vendedor['nombre']} {vendedor['apellido']}"

    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_SP, (id_vendedor, fecha_inicio, fecha_fin))
            filas = list(cursor.fetchall())
            while cursor.nextset():  # deja libre la conexión que se reutiliza
                pass
    except pymysql.err.MySQLError as e:
        if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL and e.args[1] == MSG_SIN_VENTAS:
            return ok(MSG_SIN_VENTAS, vendedor=nombre_vendedor, productos=[], total_ventas=0)
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

    return ok(MSG_CONSULTA, vendedor=nombre_vendedor, productos=productos, total_ventas=total_ventas)
