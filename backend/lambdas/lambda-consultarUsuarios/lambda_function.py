"""
lambda-consultarUsuarios
DFR 1.4 Consultar usuarios (Administrador): lista los usuarios registrados
con filtros opcionales y combinables por rol y estado. Paginado de 20 en 20
con cursor por id_usuario (rápido con muchos registros: usa la llave primaria).
Nunca devuelve password_hash.
Ruta: GET /admin/usuarios?rol=&estado=&cursor= (token con rol Administrador).
Tablas: usuario, rol. No usa stored procedure.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    ROL_ADMINISTRADOR,
    ROL_COMPRADOR,
    ROL_VENDEDOR,
    ErrorNegocio,
    campo_texto,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_ROL_INVALIDO = "El rol seleccionado no es válido"
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"
MSG_CONSULTA = "Consulta realizada"

TAMANO_PAGINA = 20

# Valores permitidos en los filtros (se aceptan sin distinguir mayúsculas)
ROLES_SISTEMA = {r.lower(): r for r in (ROL_ADMINISTRADOR, ROL_VENDEDOR, ROL_COMPRADOR)}
ESTADOS_USUARIO = {"activo": "Activo", "inactivo": "Inactivo"}  # usuario.estado ENUM

SQL_BASE = """
    SELECT u.id_usuario,
           u.nombre,
           u.apellido,
           u.email,
           r.nombre AS rol,
           u.estado,
           u.fecha_registro
    FROM usuario u
    JOIN rol r ON r.id_rol = u.id_rol
"""


@manejar_errores
def lambda_handler(event, context):
    # DFR 1.4: solo un administrador puede consultar la lista de usuarios
    validar_token(event, roles=[ROL_ADMINISTRADOR])

    params = query_params(event)
    rol_recibido = campo_texto(params, "rol")
    estado_recibido = campo_texto(params, "estado")
    cursor_recibido = entero_positivo(params.get("cursor"))  # inválido -> primera página

    # Los filtros se combinan con AND. Solo se concatenan fragmentos fijos;
    # los valores siempre van como parámetros (sin inyección SQL).
    condiciones = []
    valores = []

    if rol_recibido:
        rol = ROLES_SISTEMA.get(rol_recibido.lower())
        if rol is None:
            raise ErrorNegocio(400, MSG_ROL_INVALIDO)
        condiciones.append("r.nombre = %s")
        valores.append(rol)

    if estado_recibido:
        estado = ESTADOS_USUARIO.get(estado_recibido.lower())
        if estado is None:
            raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
        condiciones.append("u.estado = %s")
        valores.append(estado)

    if cursor_recibido is not None:
        condiciones.append("u.id_usuario > %s")
        valores.append(cursor_recibido)

    sql = SQL_BASE
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY u.id_usuario LIMIT %s"
    valores.append(TAMANO_PAGINA + 1)  # uno extra para saber si hay otra página

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(sql, valores)
        usuarios = cursor.fetchall()

    if not usuarios:
        # DFR 1.4: "Si no existen resultados, el sistema mostrará:
        # 'No se encontraron registros'". Se responde 200 con lista vacía.
        return ok(MSG_SIN_REGISTROS, usuarios=[], siguiente_cursor=None)

    siguiente_cursor = None
    if len(usuarios) > TAMANO_PAGINA:
        usuarios = usuarios[:TAMANO_PAGINA]
        siguiente_cursor = usuarios[-1]["id_usuario"]

    return ok(MSG_CONSULTA, usuarios=usuarios, siguiente_cursor=siguiente_cursor)
