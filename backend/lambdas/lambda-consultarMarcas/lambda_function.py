"""
lambda-consultarMarcas
A1 (endpoint de apoyo aprobado por Ian, no está en el DFR): lista las marcas
para el selector "Marca *" de 3.1 y 3.3 (DFR: "La categoría y la marca deben
existir en el sistema").
Ruta: GET /marcas, abierta (sin token): solo lee nombres públicos de marcas.
Tabla: marca. No usa stored procedure. Sin paginación: catálogo corto que se
llena con el seed de marcas.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    manejar_errores,
    obtener_conexion,
    ok,
)

MSG_CONSULTA = "Consulta realizada"

SQL_MARCAS = "SELECT id_marca, nombre FROM marca ORDER BY nombre"


@manejar_errores
def lambda_handler(event, context):
    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_MARCAS)
        marcas = cursor.fetchall()

    if not marcas:
        return ok(MSG_SIN_REGISTROS, marcas=[])
    return ok(MSG_CONSULTA, marcas=marcas)
