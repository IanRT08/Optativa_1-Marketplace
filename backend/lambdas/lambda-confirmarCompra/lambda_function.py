"""
lambda-confirmarCompra
DFR 6.1 Confirmar compra (Comprador): convierte el carrito en un pedido con
pago simulado. La transacción completa vive en sp_RegistrarCompra; sus
errores (SQLSTATE 45000) llegan como errno 1644 y manejar_errores los
devuelve con 400 y el mensaje exacto.
Pago tokenizado (CLAUDE.md, regla 4): se valida la tarjeta (16 dígitos) y el
CVV (3 dígitos); al SP solo llegan un token aleatorio y los últimos 4
dígitos. El número completo y el CVV nunca se guardan ni se imprimen.
Regla de Ian: la tarjeta admite solo dígitos, espacios y guiones.
Ruta: POST /compras (token con rol Comprador).
SP: sp_RegistrarCompra(p_id_usuario, p_id_direccion, p_token, p_ultimos4, OUT p_id_pedido).
"""
import re
import secrets

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

MSG_COMPRA_REALIZADA = "Compra realizada correctamente"  # DFR 6.1
MSG_PAGO_INVALIDO = "Datos de pago no válidos"  # DFR 6.1 (también lo da el SP)
MSG_DIRECCION_INVALIDA = "La dirección de envío no es válida"  # DFR 6.1 (también lo da el SP)

ID_MAX = 4294967295  # INT UNSIGNED de p_id_direccion

# Solo dígitos ASCII, espacios y guiones (regla de Ian)
_RE_TARJETA_PERMITIDA = re.compile(r"[0-9 \-]+")
_RE_16_DIGITOS = re.compile(r"[0-9]{16}")
_RE_CVV = re.compile(r"[0-9]{3}")

SQL_LIMPIAR_OUT = "SET @p_id_pedido = NULL"
SQL_SP = "CALL sp_RegistrarCompra(%s, %s, %s, %s, @p_id_pedido)"
SQL_LEER_OUT = "SELECT @p_id_pedido AS id_pedido"
SQL_TOTAL = "SELECT total FROM pedido WHERE id_pedido = %s AND id_usuario = %s"


def _texto(valor):
    """Texto del campo; un número entero del JSON se toma como texto."""
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, int):
        return str(valor)
    return valor.strip() if isinstance(valor, str) else ""


def _ultimos4(numero_tarjeta, cvv):
    """Valida tarjeta y CVV y devuelve solo los últimos 4 dígitos."""
    if not _RE_TARJETA_PERMITIDA.fullmatch(numero_tarjeta):
        raise ErrorNegocio(400, MSG_PAGO_INVALIDO)
    digitos = numero_tarjeta.replace(" ", "").replace("-", "")
    if not _RE_16_DIGITOS.fullmatch(digitos) or not _RE_CVV.fullmatch(cvv):
        raise ErrorNegocio(400, MSG_PAGO_INVALIDO)
    return digitos[-4:]


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    datos = leer_body(event)

    direccion_texto = _texto(datos.get("id_direccion"))
    numero_tarjeta = _texto(datos.get("numero_tarjeta"))
    cvv = _texto(datos.get("cvv"))
    if not direccion_texto or not numero_tarjeta or not cvv:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    ultimos4 = _ultimos4(numero_tarjeta, cvv)
    del numero_tarjeta, cvv, datos  # el número completo y el CVV no se usan más

    id_direccion = entero_positivo(direccion_texto)
    if id_direccion is None or id_direccion > ID_MAX:
        raise ErrorNegocio(400, MSG_DIRECCION_INVALIDA)

    token_pago = "tok_" + secrets.token_hex(16)  # aleatorio: no se deriva de la tarjeta

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_LIMPIAR_OUT)
        cursor.execute(SQL_SP, (sesion["id_usuario"], id_direccion, token_pago, ultimos4))
        while cursor.nextset():  # deja libre la conexión que se reutiliza
            pass
        cursor.execute(SQL_LEER_OUT)
        id_pedido = cursor.fetchone()["id_pedido"]
        if id_pedido is None:
            raise RuntimeError("sp_RegistrarCompra terminó sin número de pedido")
        cursor.execute(SQL_TOTAL, (id_pedido, sesion["id_usuario"]))
        pedido = cursor.fetchone()

    return ok(
        MSG_COMPRA_REALIZADA,
        status=201,
        id_pedido=id_pedido,
        total=pedido["total"] if pedido else None,
    )
