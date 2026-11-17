"""
lambda-consultarCategorias
DFR 2.2 Consultar categorías: lista las categorías indicando su categoría
padre cuando la tienen.
Ruta: GET /categorias (abierta, sin token).
Tabla: categoria (autorrelación id_categoria_padre). No usa stored procedure.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    manejar_errores,
    obtener_conexion,
    ok,
)

SQL_CATEGORIAS = """
    SELECT c.id_categoria,
           c.nombre,
           c.descripcion,
           c.id_categoria_padre,
           p.nombre AS categoria_padre
    FROM categoria c
    LEFT JOIN categoria p ON p.id_categoria = c.id_categoria_padre
    ORDER BY c.nombre
"""


@manejar_errores
def lambda_handler(event, context):
    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CATEGORIAS)
        categorias = cursor.fetchall()

    if not categorias:
        # DFR 2.2: "Si no existen categorías, el sistema mostrará:
        # 'No se encontraron registros'". Se responde 200 con lista vacía.
        return ok(MSG_SIN_REGISTROS, categorias=[])

    return ok("Consulta realizada", categorias=categorias)
