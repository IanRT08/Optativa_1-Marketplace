"""
lambda-actualizarStockMasivo
DFR 3.5 Actualizar stock de forma masiva (Vendedor): suma la cantidad indicada
a todas las variantes de los productos del vendedor en una categoría.
La lógica transaccional vive en sp_ActualizarStockMasivo (una sola
transacción; si falla, no cambia ningún stock). Sus errores (SQLSTATE 45000)
llegan como errno 1644 y manejar_errores los devuelve con 400 y el mensaje
exacto del SP.
Reglas aprobadas por Ian: cantidad entera, máximo 1,000,000 por operación;
categoría no válida -> mensaje del DFR "No se encontraron productos para
actualizar".
No toca DynamoDB (el Stock del catálogo es solo referencia).
Ruta: POST /vendedor/stock-masivo (token con rol Vendedor).
SP: sp_ActualizarStockMasivo(p_id_vendedor, p_id_categoria, p_cantidad).
"""
import re

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_VENDEDOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_STOCK_ACTUALIZADO = "Stock actualizado correctamente"  # DFR 3.5
MSG_SIN_PRODUCTOS = "No se encontraron productos para actualizar"  # DFR 3.5 (también lo da el SP)
MSG_CANTIDAD_ENTERA = "La cantidad debe ser un número entero"  # aprobado por Ian
MSG_CANTIDAD_INVALIDA = "La cantidad no es válida"  # aprobado por Ian

CANTIDAD_MAX = 1000000
ID_MAX = 4294967295  # INT UNSIGNED del parámetro p_id_categoria

_RE_ENTERO = re.compile(r"-?[0-9]+")

SQL_SP = "CALL sp_ActualizarStockMasivo(%s, %s, %s)"


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _cantidad(valor):
    """Entero (número o texto con solo dígitos). Si es <= 0, el SP da el mensaje del DFR."""
    if isinstance(valor, bool):
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and _RE_ENTERO.fullmatch(valor.strip()):
        numero = int(valor.strip())
    else:
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if numero > CANTIDAD_MAX:
        raise ErrorNegocio(400, MSG_CANTIDAD_INVALIDA)
    return max(numero, -1)  # cualquier valor <= 0 lo rechaza el SP


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])
    datos = leer_body(event)

    if _vacio(datos.get("id_categoria")) or _vacio(datos.get("cantidad")):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    cantidad = _cantidad(datos["cantidad"])
    id_categoria = entero_positivo(datos["id_categoria"])
    if id_categoria is None or id_categoria > ID_MAX:
        raise ErrorNegocio(400, MSG_SIN_PRODUCTOS)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_SP, (sesion["id_usuario"], id_categoria, cantidad))
        fila = cursor.fetchone()  # SELECT v_actualizadas AS variantes_actualizadas
        # Consumir todos los resultados del CALL para dejar libre la conexión
        # que se reutiliza en la siguiente invocación.
        while cursor.nextset():
            pass

    actualizadas = fila["variantes_actualizadas"] if fila else 0
    return ok(MSG_STOCK_ACTUALIZADO, variantes_actualizadas=actualizadas)
