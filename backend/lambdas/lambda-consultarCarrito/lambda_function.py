"""
lambda-consultarCarrito
DFR 5.2 Consultar carrito (Comprador): renglones del carrito del comprador de
la sesión con precio, cantidad y subtotal, y el total.
Además (para 6.1): cada renglón avisa si el producto sigue Activo y si el
stock alcanza; puede_comprar indica si sp_RegistrarCompra lo aceptaría (el SP
compra todo el carrito o nada).
Imágenes: un solo BatchGetItem por llave, solo de los productos del carrito y
solo URLImagen (bajo costo, regla de Ian). Si DynamoDB falla, se responde sin
imágenes en vez de fallar.
Ruta: GET /carrito (token con rol Comprador).
Tablas: carrito, carrito_detalle, variante_producto, producto, variante_valor,
valor_atributo, atributo (+ DynamoDB). No usa SP.
"""
import os
from decimal import Decimal

import boto3

from smavib_common import (
    ROL_COMPRADOR,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_CARRITO_VACIO = "Tu carrito está vacío"  # DFR 5.2

LOTE_DYNAMO = 100  # máximo de llaves por BatchGetItem

SQL_CARRITO = """
    SELECT cd.id_variante, cd.cantidad, v.sku, v.stock,
           p.id_producto, p.nombre, p.precio, p.estado,
           a.nombre AS atributo, va.valor
    FROM carrito c
    JOIN carrito_detalle cd ON cd.id_carrito = c.id_carrito
    JOIN variante_producto v ON v.id_variante = cd.id_variante
    JOIN producto p ON p.id_producto = v.id_producto
    LEFT JOIN variante_valor vv ON vv.id_variante = v.id_variante
    LEFT JOIN valor_atributo va ON va.id_valor = vv.id_valor
    LEFT JOIN atributo a ON a.id_atributo = va.id_atributo
    WHERE c.id_usuario = %s
    ORDER BY p.nombre, cd.id_variante, a.nombre
"""

TABLA_PRODUCTOS = os.environ["TABLA_PRODUCTOS"]
dynamodb = boto3.resource("dynamodb")


def _imagenes(ids_producto):
    """{id_producto: URLImagen} con BatchGetItem; ante cualquier falla, {}."""
    imagenes = {}
    llaves = [{"productoID": str(i)} for i in ids_producto]
    try:
        for inicio in range(0, len(llaves), LOTE_DYNAMO):
            pedido = {
                TABLA_PRODUCTOS: {
                    "Keys": llaves[inicio:inicio + LOTE_DYNAMO],
                    "ProjectionExpression": "productoID, URLImagen",
                }
            }
            for _ in range(2):  # un reintento para llaves no procesadas
                respuesta = dynamodb.batch_get_item(RequestItems=pedido)
                for item in respuesta.get("Responses", {}).get(TABLA_PRODUCTOS, []):
                    imagenes[item["productoID"]] = item.get("URLImagen")
                pedido = respuesta.get("UnprocessedKeys") or {}
                if not pedido:
                    break
    except Exception as e:
        print(f"No se pudieron leer las imágenes del carrito: {e!r}")
        return {}
    return imagenes


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CARRITO, (sesion["id_usuario"],))
        filas = cursor.fetchall()

    if not filas:
        return ok(MSG_CARRITO_VACIO, items=[], total=0, puede_comprar=False)

    # Agrupa los atributos por renglón, conservando el orden de la consulta
    renglones = {}
    for fila in filas:
        renglon = renglones.get(fila["id_variante"])
        if renglon is None:
            precio = Decimal(fila["precio"])
            renglon = {
                "id_producto": fila["id_producto"],
                "nombre": fila["nombre"],
                "id_variante": fila["id_variante"],
                "sku": fila["sku"],
                "atributos": {},
                "precio": precio,
                "cantidad": fila["cantidad"],
                "subtotal": precio * fila["cantidad"],
                "url_imagen": None,
                "disponible": fila["estado"] == "Activo",
                "stock": fila["stock"],
                "stock_suficiente": fila["cantidad"] <= fila["stock"],
            }
            renglones[fila["id_variante"]] = renglon
        if fila["atributo"] is not None:
            renglon["atributos"][fila["atributo"]] = fila["valor"]
    items = list(renglones.values())

    imagenes = _imagenes({i["id_producto"] for i in items})
    for item in items:
        item["url_imagen"] = imagenes.get(str(item["id_producto"]))

    total = sum((i["subtotal"] for i in items), Decimal("0"))
    puede_comprar = all(i["disponible"] and i["stock_suficiente"] for i in items)
    return ok(MSG_CONSULTA, items=items, total=total, puede_comprar=puede_comprar)
