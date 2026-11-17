"""
lambda-registrarDireccion
DFR 9.1 Registrar dirección de envío (Comprador): la dirección queda ligada al
comprador de la sesión y activa (activa = 1).
Reglas de Ian: textos libres con validar_texto (el número exterior admite solo
números); sin límite de direcciones por comprador.
Ruta: POST /direcciones (token con rol Comprador).
Tabla: direccion. No usa stored procedure.
"""
import re

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    campo_texto,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_texto,
    validar_token,
)

MSG_DIRECCION_REGISTRADA = "Dirección registrada correctamente"  # DFR 9.1
MSG_CP_INVALIDO = "El código postal debe tener 5 dígitos"  # DFR 9.1
MSG_LONGITUD = (  # aprobado por Ian
    "La calle no puede superar 150 caracteres, el número 20 y la colonia, "
    "la ciudad y el estado 100"
)

# Longitudes de la tabla direccion
CALLE_MAX = 150
NUMERO_MAX = 20
LUGAR_MAX = 100  # colonia, ciudad, estado_region

# Solo dígitos ASCII, igual que el CHECK ck_direccion_cp de la tabla
_RE_CP = re.compile(r"[0-9]{5}")

SQL_INSERTAR = """
    INSERT INTO direccion
        (id_usuario, calle, numero, colonia, ciudad, estado_region, codigo_postal, activa)
    VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
"""


def _codigo_postal(datos):
    """Texto del código postal; si llega como número entero se convierte a texto."""
    valor = datos.get("codigo_postal")
    if isinstance(valor, int) and not isinstance(valor, bool):
        return str(valor)
    return campo_texto(datos, "codigo_postal")


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    datos = leer_body(event)

    calle = campo_texto(datos, "calle")
    numero = campo_texto(datos, "numero")
    colonia = campo_texto(datos, "colonia")
    ciudad = campo_texto(datos, "ciudad")
    estado = campo_texto(datos, "estado")
    codigo_postal = _codigo_postal(datos)

    if not all((calle, numero, colonia, ciudad, estado, codigo_postal)):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    if not _RE_CP.fullmatch(codigo_postal):
        raise ErrorNegocio(400, MSG_CP_INVALIDO)

    if (
        len(calle) > CALLE_MAX
        or len(numero) > NUMERO_MAX
        or max(len(colonia), len(ciudad), len(estado)) > LUGAR_MAX
    ):
        raise ErrorNegocio(400, MSG_LONGITUD)

    validar_texto(calle, "La calle")
    validar_texto(numero, "El número", permitir_solo_numeros=True)
    validar_texto(colonia, "La colonia")
    validar_texto(ciudad, "La ciudad")
    validar_texto(estado, "El estado")

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(
            SQL_INSERTAR,
            (sesion["id_usuario"], calle, numero, colonia, ciudad, estado, codigo_postal),
        )
        id_direccion = cursor.lastrowid

    return ok(MSG_DIRECCION_REGISTRADA, status=201, id_direccion=id_direccion)
