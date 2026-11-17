"""
lambda-cargaDynamo
Herramienta de carga inicial (DFR, Requerimientos de Eficiencia: ingesta
masiva en DynamoDB con BatchWriteItem). Lee de RDS los productos que creó
01_carga_inicial.sql y los escribe en el catálogo con el estándar de Ian.
Se invoca UNA vez a mano desde la consola (sin API Gateway):
    {"desde_id": 1, "hasta_id": 17000}
Diseño (pedido de Ian: sin conexiones de más y optimizado):
- Una sola conexión a MySQL (smavib_common), lectura por bloques de 1,000 con
  keyset (id_producto > último leído), sin cargar todo en memoria.
- Por bloque: BatchGetItem (100 llaves por llamada, solo productoID) para no
  sobrescribir ítems que ya existan, y batch_writer (lotes de 25 con
  reintento automático) para los que faltan. Se puede reintentar sin duplicar.
- Si quedan menos de 60 s, se detiene y devuelve desde dónde continuar.
Tablas: producto, categoria, marca, variante_producto (+ DynamoDB).
"""
import os
import time
import unicodedata
from urllib.parse import quote

import boto3

from smavib_common import (
    entero_positivo,
    error,
    manejar_errores,
    obtener_conexion,
    ok,
)

MSG_EVENTO_INVALIDO = "Indica desde_id y hasta_id válidos (desde_id <= hasta_id)"

BLOQUE_RDS = 1000  # productos por lectura
LOTE_LECTURA = 100  # máximo de llaves por BatchGetItem
MARGEN_MS = 60000  # se detiene si quedan menos de 60 s
REINTENTOS = 5

# Variante estándar unida por SKU: un solo renglón por producto
SQL_BLOQUE = """
    SELECT p.id_producto, p.nombre, p.precio, p.estado, p.id_vendedor,
           c.id_categoria, c.nombre AS categoria, m.nombre AS marca,
           v.id_variante, v.sku, v.stock
    FROM producto p
    JOIN categoria c ON c.id_categoria = p.id_categoria
    JOIN marca m ON m.id_marca = p.id_marca
    LEFT JOIN variante_producto v
           ON v.id_producto = p.id_producto
          AND v.sku = CONCAT('P', p.id_producto, '-STD')
    WHERE p.id_producto > %s AND p.id_producto <= %s
    ORDER BY p.id_producto
    LIMIT %s
"""

TABLA_PRODUCTOS = os.environ["TABLA_PRODUCTOS"]
dynamodb = boto3.resource("dynamodb")
tabla_productos = dynamodb.Table(TABLA_PRODUCTOS)


def _texto_busqueda(texto):
    """Igual que en 3.1, 3.3 y 4.1: minúsculas, sin acentos, espacios normalizados."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _existentes(ids):
    """productoID que ya están en DynamoDB (BatchGetItem de 100 en 100)."""
    encontrados = set()
    for inicio in range(0, len(ids), LOTE_LECTURA):
        pedido = {
            TABLA_PRODUCTOS: {
                "Keys": [{"productoID": str(i)} for i in ids[inicio:inicio + LOTE_LECTURA]],
                "ProjectionExpression": "productoID",
            }
        }
        for intento in range(REINTENTOS):
            respuesta = dynamodb.batch_get_item(RequestItems=pedido)
            for item in respuesta.get("Responses", {}).get(TABLA_PRODUCTOS, []):
                encontrados.add(item["productoID"])
            pedido = respuesta.get("UnprocessedKeys") or {}
            if not pedido:
                break
            time.sleep(0.2 * (intento + 1))  # espera creciente antes de reintentar
        else:
            raise RuntimeError("DynamoDB dejó llaves sin procesar tras varios reintentos")
    return encontrados


def _item(fila):
    """Ítem con el estándar de Ian a partir de una fila de RDS."""
    return {
        "productoID": str(fila["id_producto"]),
        "Nombre": fila["nombre"],
        "NombreBusqueda": _texto_busqueda(fila["nombre"]),
        "Descripcion": {
            "Resumen": f"{fila['categoria']} de la marca {fila['marca']}. Producto de prueba del catálogo SMAVIB."
        },
        "Precio": fila["precio"],  # Decimal de MySQL
        "Marca": fila["marca"],
        "Categoria": fila["categoria"],
        "CategoriaID": fila["id_categoria"],
        "URLImagen": f"https://placehold.co/600x400?text={quote(fila['categoria'])}",
        "Stock": fila["stock"],  # referencia; el exacto vive en RDS
        "VendedorID": fila["id_vendedor"],
        "Estado": fila["estado"],
        "Variantes": [
            {"IdVariante": fila["id_variante"], "SKU": fila["sku"], "Stock": fila["stock"], "Atributos": {}}
        ],
    }


@manejar_errores
def lambda_handler(event, context):
    evento = event if isinstance(event, dict) else {}
    desde_id = entero_positivo(evento.get("desde_id"))
    hasta_id = entero_positivo(evento.get("hasta_id"))
    if desde_id is None or hasta_id is None or desde_id > hasta_id:
        return error(400, MSG_EVENTO_INVALIDO)

    conexion = obtener_conexion()
    ultimo = desde_id - 1  # keyset: id_producto > ultimo
    leidos = escritos = ya_existian = sin_variante = 0
    continuar_desde = None

    while True:
        if context is not None and context.get_remaining_time_in_millis() < MARGEN_MS:
            continuar_desde = ultimo + 1
            break

        with conexion.cursor() as cursor:
            cursor.execute(SQL_BLOQUE, (ultimo, hasta_id, BLOQUE_RDS))
            filas = cursor.fetchall()
        if not filas:
            break

        leidos += len(filas)
        ultimo = filas[-1]["id_producto"]
        completas = [f for f in filas if f["id_variante"] is not None]
        sin_variante += len(filas) - len(completas)

        existentes = _existentes([f["id_producto"] for f in completas])
        nuevos = [f for f in completas if str(f["id_producto"]) not in existentes]
        ya_existian += len(completas) - len(nuevos)

        with tabla_productos.batch_writer() as escritor:  # lotes de 25 + reintentos
            for fila in nuevos:
                escritor.put_item(Item=_item(fila))
        escritos += len(nuevos)
        print(f"Bloque hasta id {ultimo}: {len(nuevos)} escritos, {len(completas) - len(nuevos)} ya existían")

    mensaje = "Carga completa" if continuar_desde is None else (
        "Carga parcial: vuelve a invocar con desde_id = continuar_desde_id"
    )
    return ok(
        mensaje,
        leidos=leidos,
        escritos=escritos,
        ya_existian=ya_existian,
        sin_variante_estandar=sin_variante,
        ultimo_id_procesado=ultimo if leidos else None,
        continuar_desde_id=continuar_desde,
    )
