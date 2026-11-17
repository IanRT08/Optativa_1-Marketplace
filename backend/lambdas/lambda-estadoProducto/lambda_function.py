"""
lambda-estadoProducto
DFR 3.4 Activar / desactivar producto (Vendedor): cambia el estado de un
producto propio en RDS y en el catálogo de DynamoDB. Nunca lo borra.
Un producto Inactivo no se muestra en 4.1 ni se puede agregar al carrito
(se aplica en 4.1 y 5.1).
Reglas aprobadas por Ian:
- Sigue el DFR: activa y desactiva (se anuló "sin reactivación").
- Orden: RDS sin confirmar -> UpdateItem en DynamoDB -> commit; si DynamoDB
  falla, rollback.
- Si ya tenía ese estado: 200 con el mismo mensaje, sin escribir.
- Activar un producto sin ítem en DynamoDB (la 3.1 falló al publicarlo) ->
  409: no se puede reconstruir porque la descripción y la URL solo vivían en
  DynamoDB.
Ruta: PATCH /vendedor/productos/{id}/estado (token con rol Vendedor). Función
nueva; la Lambda vieja "eliminar" no se toca.
Tabla: producto (+ DynamoDB). No usa stored procedure.
"""
import os

import boto3

from smavib_common import (
    MSG_ACCESO_RESTRINGIDO,
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_ERROR_INTERNO,
    ROL_VENDEDOR,
    ErrorNegocio,
    campo_texto,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_ESTADO_ACTUALIZADO = "Estado del producto actualizado correctamente"  # DFR 3.4
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"  # aprobado por Ian
MSG_SIN_CATALOGO = (  # aprobado por Ian
    "El producto no se registró completo en el catálogo; regístralo de nuevo"
)

ESTADOS = {"activo": "Activo", "inactivo": "Inactivo"}
CONDICION_FALLIDA = "ConditionalCheckFailedException"  # el ítem no existe

SQL_PRODUCTO = "SELECT id_vendedor, estado FROM producto WHERE id_producto = %s FOR UPDATE"
SQL_ESTADO = "UPDATE producto SET estado = %s WHERE id_producto = %s"

tabla_productos = boto3.resource("dynamodb").Table(os.environ["TABLA_PRODUCTOS"])


def _codigo_error(excepcion):
    """Código de error de boto3 (ClientError), o None si no es de DynamoDB."""
    return (getattr(excepcion, "response", None) or {}).get("Error", {}).get("Code")


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])

    id_producto = entero_positivo(path_param(event, "id"))
    if id_producto is None:
        raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)

    datos = leer_body(event)
    estado_texto = campo_texto(datos, "estado")
    if not estado_texto:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    estado = ESTADOS.get(estado_texto.lower())
    if estado is None:
        raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)

    # --- RDS sin confirmar (si algo falla, manejar_errores hace rollback) ---
    conexion = obtener_conexion()
    conexion.begin()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_PRODUCTO, (id_producto,))
        producto = cursor.fetchone()
        if producto is None:
            raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)
        if producto["id_vendedor"] != sesion["id_usuario"]:
            raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)  # DFR 3.4

        if producto["estado"] == estado:
            conexion.rollback()  # nada que cambiar
            return ok(MSG_ESTADO_ACTUALIZADO, id_producto=id_producto, estado=estado)

        cursor.execute(SQL_ESTADO, (estado, id_producto))

    # --- DynamoDB antes del commit ---
    try:
        tabla_productos.update_item(
            Key={"productoID": str(id_producto)},
            UpdateExpression="SET #Estado = :estado",
            ConditionExpression="attribute_exists(productoID)",
            ExpressionAttributeNames={"#Estado": "Estado"},
            ExpressionAttributeValues={":estado": estado},
        )
    except Exception as e:
        if _codigo_error(e) == CONDICION_FALLIDA and estado == "Inactivo":
            # Sin ítem en el catálogo no hay nada que ocultar: basta con RDS.
            print(f"Producto {id_producto} sin ítem en DynamoDB; se desactiva solo en RDS")
        elif _codigo_error(e) == CONDICION_FALLIDA:
            conexion.rollback()
            raise ErrorNegocio(409, MSG_SIN_CATALOGO)
        else:
            print(f"DynamoDB falló al cambiar el estado del producto {id_producto}; rollback: {e!r}")
            conexion.rollback()
            raise ErrorNegocio(500, MSG_ERROR_INTERNO)

    conexion.commit()
    return ok(MSG_ESTADO_ACTUALIZADO, id_producto=id_producto, estado=estado)
