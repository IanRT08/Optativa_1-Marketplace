"""Constantes de la interfaz web.

Las longitudes y los mensajes son los mismos de las Lambdas
(lambdas/layer/python/smavib_common.py). Si cambian allá, se cambian aquí.
"""

# --- Roles (tabla rol; los devuelve la 1.2 con esta escritura) ---------------
ROL_ADMINISTRADOR = "Administrador"
ROL_VENDEDOR = "Vendedor"
ROL_COMPRADOR = "Comprador"
ROLES = (ROL_ADMINISTRADOR, ROL_VENDEDOR, ROL_COMPRADOR)

# --- Longitudes máximas (iguales a las de las Lambdas) -----------------------
NOMBRE_MAX = 80    # usuario.nombre y usuario.apellido VARCHAR(80)
EMAIL_MAX = 150    # usuario.email VARCHAR(150)

# --- Mensajes (texto exacto del DFR o aprobados por Ian) ---------------------
MSG_CAMPOS_OBLIGATORIOS = "Debe completar los campos obligatorios"
MSG_NOMBRE_LARGO = "El nombre y el apellido no pueden superar 80 caracteres"
MSG_CORREO_FORMATO = "El formato del correo electrónico no es válido"
MSG_SESION_INVALIDA = "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"
MSG_ACCESO_RESTRINGIDO = "Acceso restringido"
MSG_ERROR_INTERNO = "Ocurrió un error interno. Intenta más tarde"
MSG_REGISTRO_EXITOSO = "Registro exitoso"

# --- Llamadas a API Gateway --------------------------------------------------
# Las Lambdas tienen 10 s de timeout; se deja margen para el arranque en frío.
API_TIMEOUT_S = 15
SESION_HORAS = 2   # igual que la vigencia del JWT de la 1.2
