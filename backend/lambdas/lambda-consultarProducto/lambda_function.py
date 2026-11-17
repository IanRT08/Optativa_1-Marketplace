"""
lambda-consultarProducto
DFR 4.2 Consultar detalle de producto: nombre, descripción, precio, stock
disponible, marca, categoría, imagen y vendedor. Solo productos Activos.
Reglas de Ian:
- Abierta. Token opcional: con sesión válida (cualquier rol) se muestra el
  stock exacto; visitante (o token inválido/vencido) solo ve "disponible".
- Producto Inactivo -> 404 "Este producto ya no está disponible".
Fuentes: RDS para estado, nombre, precio, marca, categoría, vendedor y stock
exacto por variante (fuente de verdad); DynamoDB para descripción, imagen,
especificaciones y logística.
Ruta: GET /productos/{id}.
Tablas: producto, marca, categoria, usuario, variante_producto,
variante_valor, valor_atributo, atributo (+ DynamoDB). No usa SP.
"""
import os

import boto3

from smavib_common import (
    MSG_ERROR_INTERNO,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"  # aprobado por Ian
MSG_NO_DISPONIBLE = "Este producto ya no está disponible"  # aprobado por Ian

SQL_PRODUCTO = """
    SELECT p.id_producto, p.nombre, p.precio, p.estado,
           m.nombre AS marca, c.id_categoria, c.nombre AS categoria,
           u.nombre AS vendedor_nombre, u.apellido AS vendedor_apellido
    FROM producto p
    JOIN marca m ON m.id_marca = p.id_marca
    JOIN categoria c ON c.id_categoria = p.id_categoria
    JOIN usuario u ON u.id_usuario = p.id_vendedor
    WHERE p.id_producto = %s
"""
SQL_VARIANTES = """
    SELECT v.id_variante, v.sku, v.stock, a.nombre AS atributo, va.valor
    FROM variante_producto v
    LEFT JOIN variante_valor vv ON vv.id_variante = v.id_variante
    LEFT JOIN valor_atributo va ON va.id_valor = vv.id_valor
    LEFT JOIN atributo a ON a.id_atributo = va.id_atributo
    WHERE v.id_producto = %s
    ORDER BY v.id_variante, a.nombre
"""

tabla_productos = boto3.resource("dynamodb").Table(os.environ["TABLA_PRODUCTOS"])


def _usuario_opcional(event):
    """Usuario del token si es válido; None si no hay token o no es válido (visitante)."""
    try:
        return validar_token(event)
    except ErrorNegocio:
        return None


def _variantes(filas, con_stock):
    variantes = {}
    for fila in filas:
        variante = variantes.get(fila["id_variante"])
        if variante is None:
            variante = {
                "id_variante": fila["id_variante"],
                "sku": fila["sku"],
                "atributos": {},
                "disponible": fila["stock"] > 0,
            }
            if con_stock:
                variante["stock"] = fila["stock"]
            variantes[fila["id_variante"]] = variante
        if fila["atributo"] is not None:
            variante["atributos"][fila["atributo"]] = fila["valor"]
    return list(variantes.values())


@manejar_errores
def lambda_handler(event, context):
    id_producto = entero_positivo(path_param(event, "id"))
    if id_producto is None:
        raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)

    con_stock = _usuario_opcional(event) is not None

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_PRODUCTO, (id_producto,))
        producto = cursor.fetchone()
        if producto is None:
            raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)
        if producto["estado"] != "Activo":  # DFR 4.2: solo Activos
            raise ErrorNegocio(404, MSG_NO_DISPONIBLE)
        cursor.execute(SQL_VARIANTES, (id_producto,))
        variantes = _variantes(cursor.fetchall(), con_stock)

    respuesta = tabla_productos.get_item(
        Key={"productoID": str(id_producto)},
        ProjectionExpression="#Descripcion, #URLImagen, #Especificaciones, #LogisticaEnvio",
        ExpressionAttributeNames={
            "#Descripcion": "Descripcion",
            "#URLImagen": "URLImagen",
            "#Especificaciones": "Especificaciones",
            "#LogisticaEnvio": "LogisticaEnvio",
        },
    )
    item = respuesta.get("Item")
    if item is None:
        # Activo en RDS pero sin ítem en el catálogo: no debería pasar.
        print(f"Producto {id_producto} Activo en RDS sin ítem en DynamoDB")
        raise ErrorNegocio(500, MSG_ERROR_INTERNO)

    descripcion = dict(item.get("Descripcion") or {})
    detalle = {
        "id_producto": producto["id_producto"],
        "nombre": producto["nombre"],
        "descripcion": descripcion.pop("Resumen", None),
        "detalles": descripcion,  # claves extra de Descripcion (p. ej. Pantalla)
        "precio": producto["precio"],
        "marca": producto["marca"],
        "categoria": producto["categoria"],
        "id_categoria": producto["id_categoria"],
        "url_imagen": item.get("URLImagen"),
        "vendedor": f"{producto['vendedor_nombre']} {producto['vendedor_apellido']}",
        "especificaciones": item.get("Especificaciones") or {},
        "logistica_envio": item.get("LogisticaEnvio"),
        "disponible": any(v["disponible"] for v in variantes),
        "variantes": variantes,
    }
    if con_stock:
        detalle["stock"] = sum(v["stock"] for v in variantes)  # DFR 3.6: suma de variantes

    return ok(MSG_CONSULTA, producto=detalle)
