from smavib_common import (
    ErrorNegocio,
    ROL_COMPRADOR,
    MSG_CAMPOS_OBLIGATORIOS,
    campo_texto,
    entero_positivo,
    leer_body,
    manejar_errores,
    ok,
    error,
    obtener_conexion,
    obtener_conexion_resenas,
    path_param,
    validar_texto,
    validar_token,
)

COMENTARIO_MAX = 1000


def _validar_id_producto(raw):
    id_producto = entero_positivo(raw)
    if not id_producto:
        raise ErrorNegocio(404, "El producto no existe")
    return id_producto


def _verificar_producto_comprado(id_usuario, id_producto):
    """El comprador debe tener al menos un pedido Entregado con ese producto."""
    con = obtener_conexion()
    with con.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM pedido ped
            JOIN estado_pedido e   ON e.id_estado   = ped.id_estado
            JOIN detalle_pedido d  ON d.id_pedido   = ped.id_pedido
            JOIN variante_producto v ON v.id_variante = d.id_variante
            WHERE ped.id_usuario = %s
              AND v.id_producto  = %s
              AND e.nombre       = 'Entregado'
            LIMIT 1
            """,
            (id_usuario, id_producto),
        )
        if not cur.fetchone():
            raise ErrorNegocio(403, "Solo puedes reseñar productos que hayas recibido")


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
    usuario = validar_token(event, roles=[ROL_COMPRADOR])
    id_usuario = usuario["id_usuario"]

    id_producto = _validar_id_producto(path_param(event, "id"))

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

    _verificar_producto_existe(id_producto)
    _verificar_producto_comprado(id_usuario, id_producto)

    con_r = obtener_conexion_resenas()
    with con_r.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO resena (id_usuario, id_producto, calificacion, comentario)
                VALUES (%s, %s, %s, %s)
                """,
                (id_usuario, id_producto, calificacion, comentario),
            )
        except Exception as e:
            # errno 1062 = Duplicate entry (uq_resena_usuario_producto)
            if hasattr(e, "args") and len(e.args) >= 1 and e.args[0] == 1062:
                raise ErrorNegocio(409, "Ya escribiste una reseña para este producto")
            raise

        id_resena = cur.lastrowid

    return ok("Reseña registrada correctamente", status=201, id_resena=id_resena)
