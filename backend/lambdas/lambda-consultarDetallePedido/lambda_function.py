"""
lambda-consultarDetallePedido
DFR 7.2 Consultar detalle de pedido: cada producto con cantidad, precio
unitario histórico (detalle_pedido.precio_unitario) y subtotal, y el total.
Reglas de Ian:
- Comprador: solo sus pedidos (otro -> 403 "Acceso restringido"); ve la
  dirección completa y el pago (últimos 4 dígitos y estado).
- Administrador: cualquier pedido, con datos reducidos: nombre del comprador,
  dirección solo con ciudad, estado y código postal, y sin datos de pago.
- Inexistente o id no válido -> 404 "El pedido no existe".
El token de pago nunca se devuelve. Fecha guardada en hora de México (se devuelve con -06:00).
Imágenes: un solo BatchGetItem de bajo costo; si DynamoDB falla, sin imágenes.
Ruta: GET /pedidos/{id} (token Comprador o Administrador).
Tablas: pedido, estado_pedido, usuario, direccion, pago, detalle_pedido,
variante_producto, producto, variante_valor, valor_atributo, atributo (+ DynamoDB).
"""
import datetime
import os
from decimal import Decimal

import boto3

from smavib_common import (
    MSG_ACCESO_RESTRINGIDO,
    ROL_ADMINISTRADOR,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_PEDIDO_NO_EXISTE = "El pedido no existe"  # aprobado por Ian

ZONA_MEXICO = datetime.timezone(datetime.timedelta(hours=-6))  # UTC-6 fijo
LOTE_DYNAMO = 100

SQL_PEDIDO = """
    SELECT p.id_pedido, p.id_usuario, p.fecha, p.total, e.nombre AS estado,
           u.nombre AS comprador_nombre, u.apellido AS comprador_apellido,
           d.calle, d.numero, d.colonia, d.ciudad, d.estado_region, d.codigo_postal,
           pg.ultimos4, pg.estado AS estado_pago
    FROM pedido p
    JOIN estado_pedido e ON e.id_estado = p.id_estado
    JOIN usuario u ON u.id_usuario = p.id_usuario
    LEFT JOIN direccion d ON d.id_direccion = p.id_direccion
    LEFT JOIN pago pg ON pg.id_pedido = p.id_pedido
    WHERE p.id_pedido = %s
"""
SQL_PRODUCTOS = """
    SELECT dp.id_detalle, dp.id_variante, dp.cantidad, dp.precio_unitario, v.sku,
           pr.id_producto, pr.nombre, a.nombre AS atributo, va.valor
    FROM detalle_pedido dp
    JOIN variante_producto v ON v.id_variante = dp.id_variante
    JOIN producto pr ON pr.id_producto = v.id_producto
    LEFT JOIN variante_valor vv ON vv.id_variante = v.id_variante
    LEFT JOIN valor_atributo va ON va.id_valor = vv.id_valor
    LEFT JOIN atributo a ON a.id_atributo = va.id_atributo
    WHERE dp.id_pedido = %s
    ORDER BY dp.id_detalle, a.nombre
"""

TABLA_PRODUCTOS = os.environ["TABLA_PRODUCTOS"]
dynamodb = boto3.resource("dynamodb")


def _fecha_mexico(fecha):
    """datetime de RDS (ya en hora de México, sin zona) -> texto ISO con -06:00."""
    return fecha.replace(tzinfo=ZONA_MEXICO).isoformat()


def _imagenes(ids_producto):
    """{id_producto: URLImagen} con BatchGetItem (igual que 5.2); ante falla, {}."""
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
        print(f"No se pudieron leer las imágenes del pedido: {e!r}")
        return {}
    return imagenes


def _productos(filas):
    productos = {}
    for fila in filas:
        producto = productos.get(fila["id_detalle"])
        if producto is None:
            precio = Decimal(fila["precio_unitario"])
            producto = {
                "id_producto": fila["id_producto"],
                "nombre": fila["nombre"],
                "id_variante": fila["id_variante"],
                "sku": fila["sku"],
                "atributos": {},
                "cantidad": fila["cantidad"],
                "precio_unitario": precio,  # DFR 7.2: precio histórico
                "subtotal": precio * fila["cantidad"],
                "url_imagen": None,
            }
            productos[fila["id_detalle"]] = producto
        if fila["atributo"] is not None:
            producto["atributos"][fila["atributo"]] = fila["valor"]
    return list(productos.values())


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR, ROL_ADMINISTRADOR])
    es_admin = sesion["rol"] == ROL_ADMINISTRADOR

    id_pedido = entero_positivo(path_param(event, "id"))
    if id_pedido is None:
        raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_PEDIDO, (id_pedido,))
        cabecera = cursor.fetchone()
        if cabecera is None:
            raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)
        if not es_admin and cabecera["id_usuario"] != sesion["id_usuario"]:
            raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)  # DFR 7.2: solo sus pedidos
        cursor.execute(SQL_PRODUCTOS, (id_pedido,))
        productos = _productos(cursor.fetchall())

    imagenes = _imagenes({p["id_producto"] for p in productos})
    for producto in productos:
        producto["url_imagen"] = imagenes.get(str(producto["id_producto"]))

    detalle = {
        "id_pedido": cabecera["id_pedido"],
        "fecha": _fecha_mexico(cabecera["fecha"]),
        "estado": cabecera["estado"],
        "total": cabecera["total"],
        "productos": productos,
    }

    tiene_direccion = cabecera["ciudad"] is not None
    if es_admin:
        # Datos reducidos (regla de Ian): sin pago y sin calle, número ni colonia
        detalle["comprador"] = f"{cabecera['comprador_nombre']} {cabecera['comprador_apellido']}"
        detalle["direccion"] = {
            "ciudad": cabecera["ciudad"],
            "estado": cabecera["estado_region"],
            "codigo_postal": cabecera["codigo_postal"],
        } if tiene_direccion else None
    else:
        detalle["direccion"] = {
            "calle": cabecera["calle"],
            "numero": cabecera["numero"],
            "colonia": cabecera["colonia"],
            "ciudad": cabecera["ciudad"],
            "estado": cabecera["estado_region"],
            "codigo_postal": cabecera["codigo_postal"],
        } if tiene_direccion else None
        detalle["pago"] = {
            "ultimos4": cabecera["ultimos4"],
            "estado": cabecera["estado_pago"],
        } if cabecera["ultimos4"] else None

    return ok(MSG_CONSULTA, pedido=detalle)
