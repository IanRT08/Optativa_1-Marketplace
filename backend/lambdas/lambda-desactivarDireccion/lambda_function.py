"""
lambda-desactivarDireccion
DFR 9.3 Desactivar dirección (Comprador): baja lógica (activa = 0). No se
borra para conservar la información de los pedidos ya generados.
Reglas aprobadas por Ian: si ya estaba inactiva responde 200 con el mismo
mensaje; dirección inexistente -> 404 "La dirección no existe".
Ruta: PATCH /direcciones/{id}/desactivar (token con rol Comprador).
Tabla: direccion. No usa stored procedure.
"""
from smavib_common import (
    MSG_ACCESO_RESTRINGIDO,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_DIRECCION_DESACTIVADA = "Dirección desactivada correctamente"  # DFR 9.3
MSG_DIRECCION_NO_EXISTE = "La dirección no existe"  # aprobado por Ian

SQL_DIRECCION = "SELECT id_usuario, activa FROM direccion WHERE id_direccion = %s"
SQL_DESACTIVAR = "UPDATE direccion SET activa = 0 WHERE id_direccion = %s AND id_usuario = %s"


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])

    id_direccion = entero_positivo(path_param(event, "id"))
    if id_direccion is None:
        raise ErrorNegocio(404, MSG_DIRECCION_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_DIRECCION, (id_direccion,))
        direccion = cursor.fetchone()
        if direccion is None:
            raise ErrorNegocio(404, MSG_DIRECCION_NO_EXISTE)

        # DFR 9.3: solo puede desactivar sus propias direcciones.
        if direccion["id_usuario"] != sesion["id_usuario"]:
            raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)

        # Baja lógica (nunca DELETE). Si ya estaba inactiva no se vuelve a escribir.
        if direccion["activa"]:
            cursor.execute(SQL_DESACTIVAR, (id_direccion, sesion["id_usuario"]))

    return ok(MSG_DIRECCION_DESACTIVADA, id_direccion=id_direccion)
