"""
lambda-iniciarSesion
DFR 1.2 Inicio de sesión (Comprador, Vendedor, Administrador): valida correo
y contraseña (bcrypt) y emite un JWT HS256 válido por 2 horas con el
id_usuario y el rol.
Ruta: POST /auth/login (abierta, sin token).
Tablas: usuario, rol. No usa stored procedure.
"""
from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    SESION_HORAS,
    ErrorNegocio,
    campo_password,
    campo_texto,
    emitir_token,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    verificar_password,
)

MSG_USUARIO_NO_ENCONTRADO = "Usuario no encontrado"
MSG_PASSWORD_INCORRECTA = "Contraseña incorrecta"
MSG_CUENTA_INACTIVA = "La cuenta se encuentra inactiva"
MSG_SESION_INICIADA = "Sesión iniciada"

SQL_USUARIO_POR_EMAIL = """
    SELECT u.id_usuario,
           u.nombre,
           u.apellido,
           u.password_hash,
           u.estado,
           r.nombre AS rol
    FROM usuario u
    JOIN rol r ON r.id_rol = u.id_rol
    WHERE u.email = %s
    LIMIT 1
"""


@manejar_errores
def lambda_handler(event, context):
    datos = leer_body(event)

    email = campo_texto(datos, "email").lower()  # 1.1 guarda el correo en minúsculas
    password = campo_password(datos, "password")

    if not email or not password:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_USUARIO_POR_EMAIL, (email,))
        usuario = cursor.fetchone()

    # Regla 1: el usuario debe existir en el sistema
    if not usuario:
        raise ErrorNegocio(404, MSG_USUARIO_NO_ENCONTRADO)

    # Regla 2: la contraseña debe coincidir con la registrada (hash bcrypt)
    if not verificar_password(password, usuario["password_hash"]):
        raise ErrorNegocio(401, MSG_PASSWORD_INCORRECTA)

    # Regla 3: la cuenta debe estar activa (se revisa después de la contraseña
    # para no revelar el estado de la cuenta a quien no conoce la contraseña)
    if usuario["estado"] != "Activo":
        raise ErrorNegocio(403, MSG_CUENTA_INACTIVA)

    token = emitir_token(usuario["id_usuario"], usuario["rol"])

    # Inicia sesión según el rol de la cuenta: Flask redirige con 'rol'
    return ok(
        MSG_SESION_INICIADA,
        token=token,
        expira_en=SESION_HORAS * 3600,
        id_usuario=usuario["id_usuario"],
        nombre=usuario["nombre"],
        apellido=usuario["apellido"],
        rol=usuario["rol"],
    )
