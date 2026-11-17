"""
lambda-actualizarEstadoPedido
DFR 7.3 Actualizar estado de pedido (Administrador).
Transiciones del DFR: Pendiente->Enviado, Pendiente->Cancelado,
Enviado->Entregado, Enviado->Cancelado, Entregado->Devuelto. Un pedido
Cancelado o Devuelto ya no cambia.
- Cancelado / Devuelto: sp_CancelarPedido(p_id_pedido, p_nuevo_estado), que
  valida, repone stock y reembolsa el pago en una transacción. Sus errores
  (errno 1644) los devuelve manejar_errores con 400; "El pedido no existe"
  se traduce a 404 (aprobado por Ian, igual que 7.2).
- Enviado / Entregado: UPDATE simple desde la Lambda (lo indica el propio SP),
  con el pedido bloqueado (FOR UPDATE OF p).
Reglas de Ian: un valor que no es estado -> "El estado seleccionado no es
válido"; "Pendiente" como destino -> "El pedido no puede cambiar a ese estado".
Ruta: PATCH /admin/pedidos/{id}/estado (token con rol Administrador).
Tablas: pedido, estado_pedido. SP: sp_CancelarPedido.
"""
import pymysql

from smavib_common import (
    ERRNO_SIGNAL,
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_ADMINISTRADOR,
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

MSG_ESTADO_ACTUALIZADO = "Estado del pedido actualizado correctamente"  # DFR 7.3
MSG_TRANSICION_INVALIDA = "El pedido no puede cambiar a ese estado"  # DFR 7.3 (también lo da el SP)
MSG_PEDIDO_NO_EXISTE = "El pedido no existe"  # aprobado por Ian (también lo da el SP)
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian

ID_MAX = 4294967295  # INT UNSIGNED de p_id_pedido
ESTADOS = {e.lower(): e for e in ("Pendiente", "Enviado", "Entregado", "Cancelado", "Devuelto")}
CON_SP = ("Cancelado", "Devuelto")
# Destino -> estado actual requerido (cambios que no tocan stock)
ORIGEN_REQUERIDO = {"Enviado": "Pendiente", "Entregado": "Enviado"}

SQL_SP = "CALL sp_CancelarPedido(%s, %s)"
SQL_ESTADO_ACTUAL = """
    SELECT e.nombre AS estado
    FROM pedido p
    JOIN estado_pedido e ON e.id_estado = p.id_estado
    WHERE p.id_pedido = %s
    FOR UPDATE OF p
"""
SQL_ACTUALIZAR = """
    UPDATE pedido
    SET id_estado = (SELECT id_estado FROM estado_pedido WHERE nombre = %s)
    WHERE id_pedido = %s
"""


def _cancelar_o_devolver(conexion, id_pedido, destino):
    """Ejecuta sp_CancelarPedido y devuelve cuántas variantes repuso."""
    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_SP, (id_pedido, destino))
            fila = cursor.fetchone()  # id_pedido, nuevo_estado, variantes_repuestas
            while cursor.nextset():  # deja libre la conexión que se reutiliza
                pass
    except pymysql.err.MySQLError as e:
        if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL and e.args[1] == MSG_PEDIDO_NO_EXISTE:
            raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)
        raise  # los demás mensajes del SP salen con 400 (manejar_errores)
    return fila["variantes_repuestas"] if fila else 0


def _enviar_o_entregar(conexion, id_pedido, destino):
    """Pendiente -> Enviado o Enviado -> Entregado, con el pedido bloqueado."""
    conexion.begin()  # si algo falla, manejar_errores hace rollback
    with conexion.cursor() as cursor:
        cursor.execute(SQL_ESTADO_ACTUAL, (id_pedido,))
        actual = cursor.fetchone()
        if actual is None:
            raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)
        if actual["estado"] != ORIGEN_REQUERIDO[destino]:
            raise ErrorNegocio(400, MSG_TRANSICION_INVALIDA)
        cursor.execute(SQL_ACTUALIZAR, (destino, id_pedido))
    conexion.commit()


@manejar_errores
def lambda_handler(event, context):
    validar_token(event, roles=[ROL_ADMINISTRADOR])  # DFR 7.3: "Acceso restringido"

    id_pedido = entero_positivo(path_param(event, "id"))
    if id_pedido is None or id_pedido > ID_MAX:
        raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)

    datos = leer_body(event)
    estado_texto = campo_texto(datos, "estado")
    if not estado_texto:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    destino = ESTADOS.get(estado_texto.lower())
    if destino is None:
        raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
    if destino == "Pendiente":  # ningún pedido vuelve a Pendiente
        raise ErrorNegocio(400, MSG_TRANSICION_INVALIDA)

    conexion = obtener_conexion()
    if destino in CON_SP:
        repuestas = _cancelar_o_devolver(conexion, id_pedido, destino)
        return ok(MSG_ESTADO_ACTUALIZADO, id_pedido=id_pedido, estado=destino,
                  variantes_repuestas=repuestas)

    _enviar_o_entregar(conexion, id_pedido, destino)
    return ok(MSG_ESTADO_ACTUALIZADO, id_pedido=id_pedido, estado=destino)
