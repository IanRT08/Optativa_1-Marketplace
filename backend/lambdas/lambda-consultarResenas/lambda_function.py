from smavib_common import (
    ErrorNegocio,
    manejar_errores,
    ok,
    obtener_conexion,
    obtener_conexion_resenas,
    path_param,
    query_params,
    entero_positivo,
)

PAGINA = 20


def _validar_id_producto(raw):
    id_producto = entero_positivo(raw)
    if not id_producto:
        raise ErrorNegocio(404, "El producto no existe")
    return id_producto


def _verificar_producto_existe(id_producto):
    con = obtener_conexion()
    with con.cursor() as cur:
        cur.execute(
            "SELECT id_producto FROM producto WHERE id_producto = %s AND estado = 'Activo'",
            (id_producto,),
        )
        if not cur.fetchone():
            raise ErrorNegocio(404, "El producto no existe")


@manejar_errores
def lambda_handler(event, context):
    id_producto = _validar_id_producto(path_param(event, "id"))
    _verificar_producto_existe(id_producto)

    params = query_params(event)
    cursor = entero_positivo(params.get("cursor")) or 0

    con_r = obtener_conexion_resenas()
    with con_r.cursor() as cur:
        cur.execute(
            """
            SELECT id_resena, id_usuario, calificacion, comentario, fecha
            FROM resena
            WHERE id_producto = %s
              AND activa      = 1
              AND id_resena   > %s
            ORDER BY id_resena
            LIMIT %s
            """,
            (id_producto, cursor, PAGINA + 1),
        )
        filas = cur.fetchall()

    hay_siguiente = len(filas) > PAGINA
    resenas = filas[:PAGINA]
    siguiente_cursor = resenas[-1]["id_resena"] if hay_siguiente else None

    if not resenas:
        return ok("No hay reseñas para este producto", resenas=[], siguiente_cursor=None)

    # Promedio de calificación
    promedio = round(sum(r["calificacion"] for r in resenas) / len(resenas), 1)

    return ok(
        "Consulta realizada",
        resenas=[
            {
                "id_resena":    r["id_resena"],
                "id_usuario":   r["id_usuario"],
                "calificacion": r["calificacion"],
                "comentario":   r["comentario"],
                "fecha":        r["fecha"],
            }
            for r in resenas
        ],
        promedio_calificacion=promedio,
        siguiente_cursor=siguiente_cursor,
    )
