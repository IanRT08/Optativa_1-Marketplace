from smavib_common import (
    ErrorNegocio,
    ROL_ADMINISTRADOR,
    ROL_COMPRADOR,
    entero_positivo,
    manejar_errores,
    ok,
    obtener_conexion_resenas,
    path_param,
    validar_token,
)


def _validar_id_resena(raw):
    id_resena = entero_positivo(raw)
    if not id_resena:
        raise ErrorNegocio(404, "La reseña no existe")
    return id_resena


@manejar_errores
def lambda_handler(event, context):
    usuario = validar_token(event, roles=[ROL_COMPRADOR, ROL_ADMINISTRADOR])
    id_usuario = usuario["id_usuario"]
    rol = usuario["rol"]

    id_resena = _validar_id_resena(path_param(event, "id"))

    con_r = obtener_conexion_resenas()
    with con_r.cursor() as cur:
        cur.execute(
            "SELECT id_usuario, activa FROM resena WHERE id_resena = %s",
            (id_resena,),
        )
        fila = cur.fetchone()

    if not fila or not fila["activa"]:
        raise ErrorNegocio(404, "La reseña no existe")

    # El Comprador solo puede eliminar la suya; el Administrador puede cualquiera
    if rol == ROL_COMPRADOR and fila["id_usuario"] != id_usuario:
        raise ErrorNegocio(403, "Acceso restringido")

    with con_r.cursor() as cur:
        cur.execute(
            "UPDATE resena SET activa = 0 WHERE id_resena = %s",
            (id_resena,),
        )

    return ok("Reseña eliminada correctamente", id_resena=id_resena)
