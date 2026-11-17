"""
lambda-consultarProductos
DFR 4.1 Buscar y filtrar productos: solo productos Activos, con filtros
opcionales combinables (palabra clave, categoría, precio mínimo y máximo).
Se resuelve sobre DynamoDB (DFR, Requerimientos de Eficiencia) con dos GSI:
  - EstadoPrecio    (Estado, Precio):      búsqueda sin categoría
  - CategoriaPrecio (CategoriaID, Precio): búsqueda con categoría
El rango de precio va en la condición de llave (Query, sin recorrer la tabla);
la palabra clave filtra sobre NombreBusqueda (minúsculas, sin acentos).
Paginación: 20 por página, ordenadas por precio; cursor codificado en base64.
Reglas de Ian: abierta (sin token); categoría exacta; el listado no muestra
stock (el exacto se ve en 4.2, desde RDS).
Ruta: GET /productos. No usa RDS ni stored procedures.
"""
import base64
import json
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation

import boto3

from smavib_common import (
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    ok,
    query_params,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_PRODUCTOS = "No se encontraron productos"  # DFR 4.1
MSG_RANGO_PRECIO = "El precio mínimo no puede ser mayor al máximo"  # DFR 4.1
MSG_PRECIO_INVALIDO = "El precio no es válido"  # aprobado por Ian

TAM_PAGINA = 20
LOTE = 200  # ítems que evalúa cada Query
MAX_EVALUADOS = 2000  # tope por invocación (si se alcanza, se devuelve lo encontrado y un cursor)
Q_MAX = 100
PRECIO_MAX = Decimal("100000000")
INDICE_ESTADO = "EstadoPrecio"
INDICE_CATEGORIA = "CategoriaPrecio"

_RE_PRECIO = re.compile(r"[0-9]+(\.[0-9]{1,2})?")

NOMBRES = {
    "#Nombre": "Nombre",
    "#Precio": "Precio",
    "#Marca": "Marca",
    "#Categoria": "Categoria",
    "#CategoriaID": "CategoriaID",
    "#URLImagen": "URLImagen",
    "#Estado": "Estado",
}
PROYECCION = "productoID, " + ", ".join(NOMBRES)

tabla_productos = boto3.resource("dynamodb").Table(os.environ["TABLA_PRODUCTOS"])


def _texto_busqueda(texto):
    """'Niño Azúl' -> 'nino azul' (igual que NombreBusqueda en 3.1 y 3.3)."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _precio_filtro(texto):
    texto = (texto or "").strip()
    if not texto:
        return None
    if not _RE_PRECIO.fullmatch(texto):
        raise ErrorNegocio(400, MSG_PRECIO_INVALIDO)
    precio = Decimal(texto)
    if precio >= PRECIO_MAX:
        raise ErrorNegocio(400, MSG_PRECIO_INVALIDO)
    return precio


# --- Cursor -----------------------------------------------------------------
def _llave(item, indice):
    """ExclusiveStartKey de un GSI: llave de la tabla + llaves del índice."""
    llave = {"productoID": item["productoID"], "Precio": item["Precio"]}
    if indice == INDICE_CATEGORIA:
        llave["CategoriaID"] = item["CategoriaID"]
    else:
        llave["Estado"] = item["Estado"]
    return llave


def _codificar_cursor(llave, indice):
    datos = {
        "i": indice,
        "p": llave["productoID"],
        "precio": str(llave["Precio"]),
        "k": str(llave.get("CategoriaID", llave.get("Estado"))),
    }
    return base64.urlsafe_b64encode(json.dumps(datos).encode("utf-8")).decode("ascii")


def _decodificar_cursor(texto, indice, id_categoria):
    """Devuelve la llave de inicio o None (primera página) si el cursor no es válido."""
    if not texto:
        return None
    try:
        datos = json.loads(base64.urlsafe_b64decode(texto.encode("ascii")))
        producto_id, precio, valor = datos["p"], Decimal(datos["precio"]), datos["k"]
        if datos["i"] != indice or not isinstance(producto_id, str) or not precio.is_finite():
            return None
        llave = {"productoID": producto_id, "Precio": precio}
        if indice == INDICE_CATEGORIA:
            if valor != str(id_categoria):
                return None
            llave["CategoriaID"] = id_categoria
        else:
            if valor != "Activo":
                return None
            llave["Estado"] = "Activo"
        return llave
    except (ValueError, TypeError, KeyError, InvalidOperation, UnicodeError):
        return None


# --- Búsqueda ---------------------------------------------------------------
def _buscar(parametros, inicio, indice):
    """Junta hasta 20 productos aunque el filtro descarte ítems en cada lote."""
    encontrados = []
    evaluados = 0
    while True:
        consulta = dict(parametros, Limit=LOTE)
        if inicio:
            consulta["ExclusiveStartKey"] = inicio
        respuesta = tabla_productos.query(**consulta)
        evaluados += respuesta.get("ScannedCount", 0)
        lote = respuesta.get("Items", [])
        ultima = respuesta.get("LastEvaluatedKey")

        faltan = TAM_PAGINA - len(encontrados)
        if len(lote) >= faltan:
            encontrados.extend(lote[:faltan])
            hay_mas = len(lote) > faltan or ultima is not None
            return encontrados, (_llave(encontrados[-1], indice) if hay_mas else None)

        encontrados.extend(lote)
        if ultima is None:
            return encontrados, None
        if evaluados >= MAX_EVALUADOS:
            return encontrados, ultima
        inicio = ultima


def _producto(item):
    producto_id = item["productoID"]
    return {
        "id_producto": int(producto_id) if producto_id.isdigit() else producto_id,
        "nombre": item.get("Nombre"),
        "precio": item.get("Precio"),
        "marca": item.get("Marca"),
        "categoria": item.get("Categoria"),
        "id_categoria": item.get("CategoriaID"),
        "url_imagen": item.get("URLImagen"),
    }


@manejar_errores
def lambda_handler(event, context):
    filtros = query_params(event)

    precio_min = _precio_filtro(filtros.get("precio_min"))
    precio_max = _precio_filtro(filtros.get("precio_max"))
    if precio_min is not None and precio_max is not None and precio_min > precio_max:
        raise ErrorNegocio(400, MSG_RANGO_PRECIO)

    palabra = _texto_busqueda((filtros.get("q") or "")[:Q_MAX])

    categoria_texto = (filtros.get("id_categoria") or "").strip()
    id_categoria = entero_positivo(categoria_texto) if categoria_texto else None
    if categoria_texto and id_categoria is None:
        return ok(MSG_SIN_PRODUCTOS, productos=[], siguiente_cursor=None)

    nombres = dict(NOMBRES)
    valores = {":activo": "Activo"}
    filtro = []
    if id_categoria:
        indice = INDICE_CATEGORIA
        llave = "#CategoriaID = :categoria"
        valores[":categoria"] = id_categoria
        filtro.append("#Estado = :activo")  # DFR 4.1: solo Activos
    else:
        indice = INDICE_ESTADO
        llave = "#Estado = :activo"  # DFR 4.1: solo Activos

    if precio_min is not None and precio_max is not None:
        llave += " AND #Precio BETWEEN :min AND :max"
        valores.update({":min": precio_min, ":max": precio_max})
    elif precio_min is not None:
        llave += " AND #Precio >= :min"
        valores[":min"] = precio_min
    elif precio_max is not None:
        llave += " AND #Precio <= :max"
        valores[":max"] = precio_max

    if palabra:
        filtro.append("contains(#NombreBusqueda, :q)")
        nombres["#NombreBusqueda"] = "NombreBusqueda"
        valores[":q"] = palabra

    parametros = {
        "IndexName": indice,
        "KeyConditionExpression": llave,
        "ProjectionExpression": PROYECCION,
        "ExpressionAttributeNames": nombres,
        "ExpressionAttributeValues": valores,
    }
    if filtro:
        parametros["FilterExpression"] = " AND ".join(filtro)

    inicio = _decodificar_cursor(filtros.get("cursor"), indice, id_categoria)
    items, siguiente = _buscar(parametros, inicio, indice)
    cursor = _codificar_cursor(siguiente, indice) if siguiente else None

    if not items and cursor is None:
        return ok(MSG_SIN_PRODUCTOS, productos=[], siguiente_cursor=None)
    return ok(MSG_CONSULTA, productos=[_producto(i) for i in items], siguiente_cursor=cursor)
