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
BUSQUEDA_MAX = 100     # 4.1: la Lambda recorta la palabra clave a 100
URL_IMAGEN_MAX = 500   # 3.1: URL de imagen hasta 500
# 9.1 (tabla direccion)
CALLE_MAX = 150
NUMERO_MAX = 20
COLONIA_MAX = CIUDAD_MAX = ESTADO_MAX = 100

# --- Mensajes (texto exacto del DFR o aprobados por Ian) ---------------------
MSG_CAMPOS_OBLIGATORIOS = "Debe completar los campos obligatorios"
MSG_NOMBRE_LARGO = "El nombre y el apellido no pueden superar 80 caracteres"
MSG_CORREO_FORMATO = "El formato del correo electrónico no es válido"
MSG_SESION_INVALIDA = "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"
MSG_ACCESO_RESTRINGIDO = "Acceso restringido"
MSG_ERROR_INTERNO = "Ocurrió un error interno. Intenta más tarde"
MSG_REGISTRO_EXITOSO = "Registro exitoso"
MSG_SIN_PRODUCTOS = "No se encontraron productos"   # DFR 4.1
MSG_CANTIDAD_ENTERA = "La cantidad debe ser un número entero"        # 5.1 (texto de 3.5)
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"
MSG_VARIANTE_NO_EXISTE = "La variante seleccionada no existe"
MSG_CARRITO_VACIO = "Tu carrito está vacío"                          # DFR 5.2 / 6.1
MSG_DIRECCION_LARGA = ("La calle no puede superar 150 caracteres, el número 20 "
                       "y la colonia, la ciudad y el estado 100")    # 9.1
MSG_DIRECCION_NO_VALIDA = "La dirección de envío no es válida"       # DFR 6.1
MSG_DIRECCION_NO_EXISTE = "La dirección no existe"                    # 9.3
MSG_COMPRA_REALIZADA = "Compra realizada correctamente"               # DFR 6.1
# Avisos por renglón del carrito antes de comprar (textos del DFR 6.1)
MSG_STOCK_INSUFICIENTE = "Stock insuficiente para el producto {nombre}"
MSG_PRODUCTO_NO_DISPONIBLE = "El producto {nombre} ya no está disponible"

# --- Llamadas a API Gateway --------------------------------------------------
# Las Lambdas tienen 10 s de timeout; se deja margen para el arranque en frío.
API_TIMEOUT_S = 15
SESION_HORAS = 2   # igual que la vigencia del JWT de la 1.2
CATEGORIAS_CACHE_S = 300   # el filtro de categorías se refresca cada 5 min
# 4.1 revisa hasta 2,000 ítems por llamada: 9 llamadas cubren los 17,000.
BUSQUEDA_MAX_LLAMADAS = 9
