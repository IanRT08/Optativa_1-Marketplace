"""
lambda-consultarMisProductos
DFR 3.2 Consultar mis productos (Vendedor): solo los productos del vendedor
de la sesión, con filtros opcionales combinables (categoría, estado, palabra
clave en el nombre).
Fuente: RDS (stock exacto = suma de variante_producto; incluye Inactivos).
Paginación: 20 por página con cursor por id_producto.
Reglas de Ian: categoría exacta (sin subcategorías); sin productos ->
"No tienes productos registrados"; con productos pero sin coincidencias ->
"No se encontraron registros".
Ruta: GET /vendedor/productos (token con rol Vendedor).
Tablas: producto, marca, categoria, variante_producto. No usa stored procedure.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    ROL_VENDEDOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_PRODUCTOS = "No tienes productos registrados"  # DFR 3.2
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian
MSG_CATEGORIA_NO_EXISTE = "La categoría no existe"  # aprobado por Ian

TAM_PAGINA = 20
ESTADOS = {"activo": "Activo", "inactivo": "Inactivo"}

SQL_EXISTE_CATEGORIA = "SELECT 1 FROM categoria WHERE id_categoria = %s"
SQL_TIENE_PRODUCTOS = "SELECT 1 FROM producto WHERE id_vendedor = %s LIMIT 1"

# Los filtros se agregan como fragmentos fijos con parámetros (%s); nunca se
# concatena texto del usuario en el SQL.
SQL_BASE = """
    SELECT p.id_producto, p.nombre, p.precio, p.estado,
           m.nombre AS marca, c.id_categoria, c.nombre AS categoria,
           COALESCE(SUM(v.stock), 0) AS stock,
           COUNT(v.id_variante) AS variantes
    FROM producto p
    JOIN marca m ON m.id_marca = p.id_marca
    JOIN categoria c ON c.id_categoria = p.id_categoria
    LEFT JOIN variante_producto v ON v.id_producto = p.id_producto
    WHERE {condiciones}
    GROUP BY p.id_producto, p.nombre, p.precio, p.estado, m.nombre, c.id_categoria, c.nombre
    ORDER BY p.id_producto
    LIMIT %s
"""


def _patron_like(texto):
    """'%texto%' con % y _ escapados (se buscan como texto, no como comodines)."""
    escapado = texto.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escapado}%"


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])
    id_vendedor = sesion["id_usuario"]
    filtros = query_params(event)

    condiciones = ["p.id_vendedor = %s"]
    parametros = [id_vendedor]

    cursor_pagina = entero_positivo(filtros.get("cursor"))  # no válido -> primera página
    if cursor_pagina:
        condiciones.append("p.id_producto > %s")
        parametros.append(cursor_pagina)

    estado_texto = (filtros.get("estado") or "").strip()
    if estado_texto:
        estado = ESTADOS.get(estado_texto.lower())
        if estado is None:
            raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
        condiciones.append("p.estado = %s")
        parametros.append(estado)

    palabra = (filtros.get("q") or "").strip()
    if palabra:
        condiciones.append("p.nombre LIKE %s ESCAPE '!'")
        parametros.append(_patron_like(palabra))

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        categoria_texto = (filtros.get("id_categoria") or "").strip()
        if categoria_texto:
            id_categoria = entero_positivo(categoria_texto)
            if id_categoria is None:
                raise ErrorNegocio(400, MSG_CATEGORIA_NO_EXISTE)
            cursor.execute(SQL_EXISTE_CATEGORIA, (id_categoria,))
            if cursor.fetchone() is None:
                raise ErrorNegocio(400, MSG_CATEGORIA_NO_EXISTE)
            condiciones.append("p.id_categoria = %s")
            parametros.append(id_categoria)

        # Se pide uno de más para saber si hay otra página.
        sql = SQL_BASE.format(condiciones=" AND ".join(condiciones))
        cursor.execute(sql, (*parametros, TAM_PAGINA + 1))
        productos = list(cursor.fetchall())

        if not productos:
            cursor.execute(SQL_TIENE_PRODUCTOS, (id_vendedor,))
            mensaje = MSG_SIN_REGISTROS if cursor.fetchone() else MSG_SIN_PRODUCTOS
            return ok(mensaje, productos=[], siguiente_cursor=None)

    siguiente_cursor = None
    if len(productos) > TAM_PAGINA:
        productos = productos[:TAM_PAGINA]
        siguiente_cursor = productos[-1]["id_producto"]

    return ok(MSG_CONSULTA, productos=productos, siguiente_cursor=siguiente_cursor)
