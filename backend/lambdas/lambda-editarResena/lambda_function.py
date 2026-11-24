from smavib_common import (
    ErrorNegocio,
    ROL_COMPRADOR,
    MSG_CAMPOS_OBLIGATORIOS,
    campo_texto,
    entero_positivo,
    leer_body,
    manejar_errores,
    ok,
    obtener_conexion_resenas,
    path_param,
    validar_texto,
    validar_token,
)

COMENTARIO_MAX = 1000


def _validar_id_resena(raw):
    id_resena = entero_positivo(raw)
    if not id_resena:
        raise ErrorNegocio(404, "La reseña no existe")
    return id_resena


@manejar_errores
def lambda_handler(event, context):
    usuario = validar_token(event, roles=[ROL_COMPRADOR])
    id_usuario = usuario["id_usuario"]

    id_resena = _validar_id_resena(path_param(event, "id"))

    datos = leer_body(event)

    calificacion = datos.get("calificacion")
    if calificacion is None:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if not isinstance(calificacion, int) or isinstance(calificacion, bool):
        raise ErrorNegocio(400, "La calificación debe ser un número entero del 1 al 5")
    if not (1 <= calificacion <= 5):
        raise ErrorNegocio(400, "La calificación debe ser un número entero del 1 al 5")

    comentario = campo_texto(datos, "comentario")
    if not comentario:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if len(comentario) > COMENTARIO_MAX:
        raise ErrorNegocio(400, f"El comentario no puede superar {COMENTARIO_MAX} caracteres")
    validar_texto(comentario, "El comentario")

    con_r = obtener_conexion_resenas()
    with con_r.cursor() as cur:
        # Verifica que la reseña exista y sea del comprador
        cur.execute(
            "SELECT id_usuario, activa FROM resena WHERE id_resena = %s",
            (id_resena,),
        )
        fila = cur.fetchone()

    if not fila:
        raise ErrorNegocio(404, "La reseña no existe")
    if not fila["activa"]:
        raise ErrorNegocio(404, "La reseña no existe")
    if fila["id_usuario"] != id_usuario:
        raise ErrorNegocio(403, "Acceso restringido")

    with con_r.cursor() as cur:
        cur.execute(
            """
            UPDATE resena
            SET calificacion = %s, comentario = %s
            WHERE id_resena = %s
            """,
            (calificacion, comentario, id_resena),
        )

    return ok("Reseña actualizada correctamente", id_resena=id_resena)
