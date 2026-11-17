"""
lambda-agregarAlCarrito
DFR 5.1 Agregar producto al carrito (Comprador): agrega una variante con su
cantidad al carrito del comprador (en RDS, se conserva entre sesiones). Si ya
estaba, suma la cantidad sin superar el stock de esa variante.
Reglas aprobadas por Ian:
- id_variante opcional: si se omite, la variante estándar P{id}-STD.
- Producto Inactivo -> "El producto [nombre] ya no está disponible".
- Cantidad: textos de 3.5 ("mayor a cero", "número entero").
- Variante inexistente o de otro producto -> "La variante seleccionada no existe".
El carrito se bloquea (FOR UPDATE) durante la operación: un doble clic no
suma dos veces sin revisar el stock. El stock se vuelve a validar al comprar
(sp_RegistrarCompra).
Ruta: POST /carrito/items (token con rol Comprador).
Tablas: carrito, carrito_detalle, variante_producto, producto. No usa SP.
"""
import re

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

MSG_AGREGADO = "Producto agregado al carrito"  # DFR 5.1
MSG_SUPERA_STOCK = "La cantidad solicitada supera el stock disponible"  # DFR 5.1
MSG_CANTIDAD_CERO = "La cantidad debe ser mayor a cero"  # texto de 3.5 (aprobado por Ian)
MSG_CANTIDAD_ENTERA = "La cantidad debe ser un número entero"  # aprobado por Ian
MSG_VARIANTE_NO_EXISTE = "La variante seleccionada no existe"  # aprobado por Ian
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"  # aprobado por Ian
MSG_NO_DISPONIBLE = "El producto {nombre} ya no está disponible"  # aprobado por Ian

_RE_ENTERO = re.compile(r"-?[0-9]+")

SQL_CREAR_CARRITO = """
    INSERT INTO carrito (id_usuario) VALUES (%s)
    ON DUPLICATE KEY UPDATE id_usuario = id_usuario
"""
SQL_CARRITO = "SELECT id_carrito FROM carrito WHERE id_usuario = %s FOR UPDATE"
SQL_PRODUCTO = "SELECT nombre, estado FROM producto WHERE id_producto = %s"
SQL_VARIANTE = "SELECT id_variante, stock FROM variante_producto WHERE id_variante = %s AND id_producto = %s"
SQL_VARIANTE_STD = "SELECT id_variante, stock FROM variante_producto WHERE sku = %s"
SQL_EN_CARRITO = "SELECT cantidad FROM carrito_detalle WHERE id_carrito = %s AND id_variante = %s"
SQL_GUARDAR = """
    INSERT INTO carrito_detalle (id_carrito, id_variante, cantidad) VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE cantidad = %s
"""


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _cantidad(valor):
    """Entero mayor a cero (número o texto con solo dígitos)."""
    if isinstance(valor, bool):
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and _RE_ENTERO.fullmatch(valor.strip()):
        numero = int(valor.strip())
    else:
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if numero <= 0:
        raise ErrorNegocio(400, MSG_CANTIDAD_CERO)
    return numero


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    datos = leer_body(event)

    if _vacio(datos.get("id_producto")) or _vacio(datos.get("cantidad")):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    cantidad = _cantidad(datos["cantidad"])

    id_producto = entero_positivo(datos["id_producto"])
    if id_producto is None:
        raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)

    variante_pedida = datos.get("id_variante")
    id_variante = None
    if not _vacio(variante_pedida):
        id_variante = entero_positivo(variante_pedida)
        if id_variante is None:
            raise ErrorNegocio(400, MSG_VARIANTE_NO_EXISTE)

    id_usuario = sesion["id_usuario"]
    conexion = obtener_conexion()
    conexion.begin()  # si algo falla, manejar_errores hace rollback
    with conexion.cursor() as cursor:
        # Carrito del comprador (se crea la primera vez) y bloqueado hasta el commit
        cursor.execute(SQL_CREAR_CARRITO, (id_usuario,))
        cursor.execute(SQL_CARRITO, (id_usuario,))
        id_carrito = cursor.fetchone()["id_carrito"]

        cursor.execute(SQL_PRODUCTO, (id_producto,))
        producto = cursor.fetchone()
        if producto is None:
            raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)
        if producto["estado"] != "Activo":  # DFR 5.1: el producto debe estar activo
            raise ErrorNegocio(409, MSG_NO_DISPONIBLE.format(nombre=producto["nombre"]))

        if id_variante is None:
            cursor.execute(SQL_VARIANTE_STD, (f"P{id_producto}-STD",))
        else:
            cursor.execute(SQL_VARIANTE, (id_variante, id_producto))
        variante = cursor.fetchone()
        if variante is None:
            raise ErrorNegocio(400, MSG_VARIANTE_NO_EXISTE)

        cursor.execute(SQL_EN_CARRITO, (id_carrito, variante["id_variante"]))
        en_carrito = cursor.fetchone()
        total = (en_carrito["cantidad"] if en_carrito else 0) + cantidad

        # DFR 5.1: la suma no puede superar el stock de la variante seleccionada
        if total > variante["stock"]:
            raise ErrorNegocio(400, MSG_SUPERA_STOCK)

        cursor.execute(SQL_GUARDAR, (id_carrito, variante["id_variante"], total, total))
    conexion.commit()

    return ok(MSG_AGREGADO, id_variante=variante["id_variante"], cantidad_en_carrito=total)
