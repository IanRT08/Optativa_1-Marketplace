"""
lambda-consultarAtributos
A2 (endpoint de apoyo aprobado por Ian, no está en el DFR): lista los
atributos con sus valores para 3.6 (DFR: "Los atributos y valores se
seleccionan del catálogo registrado en el sistema").
Ruta: GET /atributos, abierta (sin token): solo lee el catálogo público.
Tablas: atributo, valor_atributo. No usa stored procedure.
Orden: atributos por nombre; valores por id_valor (orden de carga), para que
las tallas no salgan en orden alfabético.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    manejar_errores,
    obtener_conexion,
    ok,
)

MSG_CONSULTA = "Consulta realizada"

# LEFT JOIN: un atributo sin valores también aparece (con lista vacía).
SQL_ATRIBUTOS = """
    SELECT a.id_atributo, a.nombre, v.id_valor, v.valor
    FROM atributo a
    LEFT JOIN valor_atributo v ON v.id_atributo = a.id_atributo
    ORDER BY a.nombre, a.id_atributo, v.id_valor
"""


@manejar_errores
def lambda_handler(event, context):
    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_ATRIBUTOS)
        filas = cursor.fetchall()

    # Agrupa las filas por atributo conservando el orden de la consulta.
    atributos = {}
    for fila in filas:
        atributo = atributos.setdefault(
            fila["id_atributo"],
            {"id_atributo": fila["id_atributo"], "nombre": fila["nombre"], "valores": []},
        )
        if fila["id_valor"] is not None:
            atributo["valores"].append({"id_valor": fila["id_valor"], "valor": fila["valor"]})

    if not atributos:
        return ok(MSG_SIN_REGISTROS, atributos=[])
    return ok(MSG_CONSULTA, atributos=list(atributos.values()))
