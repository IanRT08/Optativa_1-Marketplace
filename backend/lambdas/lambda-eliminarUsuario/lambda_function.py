"""
lambda-eliminarUsuario
DFR 1.6 Eliminar usuario (Administrador): baja lógica. No borra el registro;
cambia usuario.estado a 'Inactivo' para conservar los pedidos y productos
asociados.
Reglas aprobadas por Ian:
- Un administrador no puede desactivarse a sí mismo (mismo mensaje que 1.5).
- Si el usuario ya estaba Inactivo, responde 200 con el mismo mensaje.
- Los productos de un Vendedor no se desactivan aquí: el DFR 1.6 solo cambia
  al usuario, y como 3.4 no permite reactivar productos, reactivar al
  vendedor en 1.5 no podría devolverlos.
Ruta: PATCH /admin/usuarios/{id}/desactivar (token con rol Administrador).
Tabla: usuario. No usa stored procedure.
"""
from smavib_common import (
    ROL_ADMINISTRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_USUARIO_ELIMINADO = "Usuario eliminado correctamente"  # DFR 1.6
MSG_USUARIO_NO_EXISTE = "El usuario no existe"  # aprobado por Ian
MSG_PROPIO_ROL_ESTADO = "No puedes cambiar tu propio rol o estado"  # aprobado por Ian

ESTADO_INACTIVO = "Inactivo"

SQL_ESTADO = "SELECT estado FROM usuario WHERE id_usuario = %s"
SQL_DESACTIVAR = "UPDATE usuario SET estado = 'Inactivo' WHERE id_usuario = %s"


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_ADMINISTRADOR])

    id_usuario = entero_positivo(path_param(event, "id"))
    if id_usuario is None:
        raise ErrorNegocio(404, MSG_USUARIO_NO_EXISTE)

    if id_usuario == sesion["id_usuario"]:
        raise ErrorNegocio(403, MSG_PROPIO_ROL_ESTADO)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_ESTADO, (id_usuario,))
        fila = cursor.fetchone()
        if fila is None:
            raise ErrorNegocio(404, MSG_USUARIO_NO_EXISTE)

        # Baja lógica (nunca DELETE). Si ya estaba Inactivo no se vuelve a escribir.
        if fila["estado"] != ESTADO_INACTIVO:
            cursor.execute(SQL_DESACTIVAR, (id_usuario,))

    return ok(MSG_USUARIO_ELIMINADO, id_usuario=id_usuario, estado=ESTADO_INACTIVO)
