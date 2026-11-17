"""
lambda-eliminarCategoria
DFR 2.4 Eliminar categoría (Administrador): elimina una categoría que no se
utiliza. No se puede eliminar si tiene productos asociados (activos o
inactivos) ni si tiene subcategorías.
Borrado físico: el DFR indica "eliminada en BD" y la regla de bajas lógicas
no aplica a categorías (solo a usuarios, productos, pedidos y direcciones).
Ruta: DELETE /categorias/{id} (token con rol Administrador).
Tablas: categoria, producto. No usa stored procedure.
"""
import pymysql

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

MSG_CATEGORIA_ELIMINADA = "Categoría eliminada correctamente"
MSG_CON_PRODUCTOS = "No se puede eliminar una categoría con productos asociados"
MSG_CON_SUBCATEGORIAS = "No se puede eliminar una categoría con subcategorías"
MSG_CATEGORIA_NO_EXISTE = "La categoría no existe"

ERRNO_FK_HIJOS = 1451  # fila referenciada por fk_producto_categoria o fk_categoria_padre

SQL_EXISTE_CATEGORIA = "SELECT 1 FROM categoria WHERE id_categoria = %s LIMIT 1"
SQL_TIENE_PRODUCTOS = "SELECT 1 FROM producto WHERE id_categoria = %s LIMIT 1"
SQL_TIENE_SUBCATEGORIAS = "SELECT 1 FROM categoria WHERE id_categoria_padre = %s LIMIT 1"
SQL_ELIMINAR = "DELETE FROM categoria WHERE id_categoria = %s"


def _validar_sin_dependencias(cursor, id_categoria):
    """Reglas del DFR 2.4, en el orden en que las lista el documento."""
    cursor.execute(SQL_TIENE_PRODUCTOS, (id_categoria,))
    if cursor.fetchone():
        raise ErrorNegocio(409, MSG_CON_PRODUCTOS)

    cursor.execute(SQL_TIENE_SUBCATEGORIAS, (id_categoria,))
    if cursor.fetchone():
        raise ErrorNegocio(409, MSG_CON_SUBCATEGORIAS)


@manejar_errores
def lambda_handler(event, context):
    # Solo un administrador puede eliminar categorías
    validar_token(event, roles=[ROL_ADMINISTRADOR])

    id_categoria = entero_positivo(path_param(event, "id"))
    if id_categoria is None:
        raise ErrorNegocio(404, MSG_CATEGORIA_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_EXISTE_CATEGORIA, (id_categoria,))
        if not cursor.fetchone():
            raise ErrorNegocio(404, MSG_CATEGORIA_NO_EXISTE)

        _validar_sin_dependencias(cursor, id_categoria)

    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_ELIMINAR, (id_categoria,))
    except pymysql.err.IntegrityError as e:
        if e.args and e.args[0] == ERRNO_FK_HIJOS:
            # Entró un producto o una subcategoría entre la validación y el DELETE:
            # se vuelve a revisar para responder con el mensaje del DFR correcto.
            with conexion.cursor() as cursor:
                _validar_sin_dependencias(cursor, id_categoria)
        raise

    return ok(MSG_CATEGORIA_ELIMINADA, id_categoria=id_categoria)
