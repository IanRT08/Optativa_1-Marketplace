"""
lambda-consultarDirecciones
DFR 9.2 Consultar mis direcciones (Comprador): solo las direcciones activas
del comprador de la sesión.
Reglas de Ian: sin paginación; primero la dirección activa más antigua y
después las demás de la más reciente a la menos reciente.
Ruta: GET /direcciones (token con rol Comprador).
Tabla: direccion. No usa stored procedure.
"""
from smavib_common import (
    ROL_COMPRADOR,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_DIRECCIONES = "No tienes direcciones registradas"  # DFR 9.2

# estado_region se devuelve como "estado", igual que el body de 9.1.
SQL_DIRECCIONES = """
    SELECT id_direccion, calle, numero, colonia, ciudad,
           estado_region AS estado, codigo_postal
    FROM direccion
    WHERE id_usuario = %s AND activa = 1
    ORDER BY id_direccion DESC
"""


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_DIRECCIONES, (sesion["id_usuario"],))
        direcciones = list(cursor.fetchall())

    if not direcciones:
        return ok(MSG_SIN_DIRECCIONES, direcciones=[])

    # Vienen de la más reciente a la más antigua; la más antigua (la última)
    # pasa al principio.
    direcciones.insert(0, direcciones.pop())
    return ok(MSG_CONSULTA, direcciones=direcciones)
