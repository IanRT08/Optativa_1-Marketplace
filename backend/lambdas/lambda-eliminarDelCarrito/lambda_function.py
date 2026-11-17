"""
lambda-eliminarDelCarrito
DFR 5.4 Eliminar producto del carrito (Comprador): quita uno o varios
renglones del carrito del comprador de la sesión.
Reglas aprobadas por Ian: se quitan los que sí están; 404 solo si ninguno
estaba (una lista con ids ya borrados no da error, y una lista de ids ajenos
no revela nada). Flask desactiva el botón durante la petición para evitar el
404 de un doble clic sobre un solo producto. Borrado físico: la regla de bajas lógicas no aplica a
renglones del carrito.
Los ids se procesan en bloques de 100 dentro de una sola transacción.
Ruta: DELETE /carrito/items (token con rol Comprador).
Tablas: carrito, carrito_detalle. No usa SP.
"""
from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_ELIMINADOS = "Producto/s eliminado/s del carrito"  # DFR 5.4 (texto exacto)
MSG_VARIANTE_NO_EXISTE = "La variante seleccionada no existe"  # aprobado por Ian
MSG_NO_EN_CARRITO = "El producto no está en tu carrito"  # aprobado por Ian

BLOQUE = 100

SQL_CARRITO = "SELECT id_carrito FROM carrito WHERE id_usuario = %s"
SQL_ELIMINAR = "DELETE FROM carrito_detalle WHERE id_carrito = %s AND id_variante IN ({marcas})"


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    datos = leer_body(event)

    lista = datos.get("variantes")
    if not isinstance(lista, list) or not lista:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    ids = [entero_positivo(v) for v in lista]
    if None in ids:
        raise ErrorNegocio(400, MSG_VARIANTE_NO_EXISTE)
    ids = list(dict.fromkeys(ids))  # sin repetidos, conservando el orden

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CARRITO, (sesion["id_usuario"],))
        carrito = cursor.fetchone()
    if carrito is None:
        raise ErrorNegocio(404, MSG_NO_EN_CARRITO)

    eliminados = 0
    conexion.begin()  # si algo falla, manejar_errores hace rollback
    with conexion.cursor() as cursor:
        for inicio in range(0, len(ids), BLOQUE):
            bloque = ids[inicio:inicio + BLOQUE]
            sql = SQL_ELIMINAR.format(marcas=", ".join(["%s"] * len(bloque)))
            # Solo filas del carrito del comprador: los ids ajenos no borran nada
            cursor.execute(sql, (carrito["id_carrito"], *bloque))
            eliminados += cursor.rowcount
    conexion.commit()

    if eliminados == 0:
        raise ErrorNegocio(404, MSG_NO_EN_CARRITO)
    return ok(MSG_ELIMINADOS, eliminados=eliminados)
