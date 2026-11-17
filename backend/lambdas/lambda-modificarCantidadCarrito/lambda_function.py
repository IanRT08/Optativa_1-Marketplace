"""
lambda-modificarCantidadCarrito
DFR 5.3 Modificar cantidad en el carrito (Comprador): reemplaza la cantidad de
una variante del carrito del comprador, sin superar su stock.
Reglas aprobadas por Ian:
- Variante que no está en su carrito -> 404 "El producto no está en tu carrito".
- Producto Inactivo -> 409 "El producto [nombre] ya no está disponible"
  (se quita con 5.4).
- Cantidad 0: la Lambda la rechaza (DFR: "mayor a cero"); la pantalla de
  Flask llama a 5.4 para quitar el producto.
El carrito se bloquea (FOR UPDATE) durante la operación, igual que en 5.1.
Ruta: PUT /carrito/items/{id} ({id} = id_variante) (token con rol Comprador).
Tablas: carrito, carrito_detalle, variante_producto, producto. No usa SP.
"""
import re
from decimal import Decimal

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_ACTUALIZADO = "Carrito actualizado correctamente"  # DFR 5.3
MSG_SUPERA_STOCK = "La cantidad solicitada supera el stock disponible"  # DFR 5.3
MSG_CANTIDAD_CERO = "La cantidad debe ser mayor a cero"  # texto de 3.5 (aprobado por Ian)
MSG_CANTIDAD_ENTERA = "La cantidad debe ser un número entero"  # aprobado por Ian
MSG_NO_EN_CARRITO = "El producto no está en tu carrito"  # aprobado por Ian
MSG_NO_DISPONIBLE = "El producto {nombre} ya no está disponible"  # aprobado por Ian

_RE_ENTERO = re.compile(r"-?[0-9]+")

SQL_CARRITO = "SELECT id_carrito FROM carrito WHERE id_usuario = %s FOR UPDATE"
SQL_RENGLON = """
    SELECT cd.cantidad, v.stock, p.nombre, p.estado, p.precio
    FROM carrito_detalle cd
    JOIN variante_producto v ON v.id_variante = cd.id_variante
    JOIN producto p ON p.id_producto = v.id_producto
    WHERE cd.id_carrito = %s AND cd.id_variante = %s
"""
SQL_ACTUALIZAR = "UPDATE carrito_detalle SET cantidad = %s WHERE id_carrito = %s AND id_variante = %s"


def _cantidad(valor):
    """Entero mayor a cero (número o texto con solo dígitos), igual que 5.1."""
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

    id_variante = entero_positivo(path_param(event, "id"))
    if id_variante is None:
        raise ErrorNegocio(404, MSG_NO_EN_CARRITO)

    datos = leer_body(event)
    valor = datos.get("cantidad")
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    cantidad = _cantidad(valor)

    conexion = obtener_conexion()
    conexion.begin()  # si algo falla, manejar_errores hace rollback
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CARRITO, (sesion["id_usuario"],))
        carrito = cursor.fetchone()
        if carrito is None:
            raise ErrorNegocio(404, MSG_NO_EN_CARRITO)

        # Solo renglones del carrito del comprador: uno ajeno simplemente no aparece
        cursor.execute(SQL_RENGLON, (carrito["id_carrito"], id_variante))
        renglon = cursor.fetchone()
        if renglon is None:
            raise ErrorNegocio(404, MSG_NO_EN_CARRITO)
        if renglon["estado"] != "Activo":
            raise ErrorNegocio(409, MSG_NO_DISPONIBLE.format(nombre=renglon["nombre"]))
        if cantidad > renglon["stock"]:  # DFR 5.3
            raise ErrorNegocio(400, MSG_SUPERA_STOCK)

        cursor.execute(SQL_ACTUALIZAR, (cantidad, carrito["id_carrito"], id_variante))
    conexion.commit()

    subtotal = Decimal(renglon["precio"]) * cantidad
    return ok(MSG_ACTUALIZADO, id_variante=id_variante, cantidad=cantidad, subtotal=subtotal)
