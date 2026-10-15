from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Blueprint, session
from functools import wraps
import requests
import os
import re
from flask_wtf.csrf import CSRFProtect
from dto import ProductoDTO, LogisticaEnvioDTO

app = Flask(__name__)
# SEGURIDAD: La secret_key se lee desde variable de entorno para no exponerla en el código fuente.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-insecure-key")

csrf = CSRFProtect(app)

API_GATEWAY_URL = "https://mpucrluxrh.execute-api.us-east-1.amazonaws.com"

ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,50}$')

# SEGURIDAD: Credenciales hardcodeadas temporales por rol hasta que exista la Lambda de autenticación.
# Reemplazar por llamada a Lambda cuando esté disponible.
USUARIOS = {
    "admin":    {"password": "admin123",    "rol": "administrador"},
    "vendedor": {"password": "vendedor123", "rol": "vendedor"},
    "cliente":  {"password": "cliente123",  "rol": "comprador"},
}

# Destino de redirección por rol al hacer login
RUTA_POR_ROL = {
    "administrador": "index",
    "vendedor":      "index",
    "comprador":     "catalogo",
}

def validar_producto_id(producto_id):
    return bool(ID_PATTERN.match(producto_id))

def _solo_fetch(f):
    """
    SEGURIDAD: Restringe las rutas /api solo a peticiones internas del frontend.
    Verifica el header X-Requested-With. Accesos externos reciben 403.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return wrapper

def _requiere_login(f):
    """
    SEGURIDAD: Protege rutas que requieren sesión activa.
    Redirige al login si el usuario no está autenticado.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("autenticado"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def _requiere_rol(*roles):
    """
    SEGURIDAD: Restringe una ruta a uno o más roles específicos.
    Redirige al catálogo o index según el rol activo si no tiene permiso.
    """
    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get("autenticado"):
                return redirect(url_for("login"))
            if session.get("rol") not in roles:
                destino = RUTA_POR_ROL.get(session.get("rol"), "login")
                flash("No tienes permiso para acceder a esa sección.", "error")
                return redirect(url_for(destino))
            return f(*args, **kwargs)
        return wrapper
    return decorador


# ── Rutas de autenticación ────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get("autenticado"):
        # SEGURIDAD: Si el rol en sesión no es reconocido (sesión corrupta o antigua), se limpia.
        destino = RUTA_POR_ROL.get(session.get("rol"))
        if not destino:
            session.clear()
        else:
            return redirect(url_for(destino))
    if request.method == 'POST':
        usuario = request.form.get("usuario", "")
        password = request.form.get("password", "")
        # SEGURIDAD: Comparación directa temporal — reemplazar por Lambda cuando esté disponible.
        datos = USUARIOS.get(usuario)
        if datos and datos["password"] == password:
            session["autenticado"] = True
            session["usuario"] = usuario
            session["rol"] = datos["rol"]
            return redirect(url_for(RUTA_POR_ROL[datos["rol"]]))
        flash("Credenciales incorrectas.", "error")
    return render_template("login.html")

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Rutas HTML ────────────────────────────────────────────────────────────────

@app.route('/')
@_requiere_rol("administrador", "vendedor")
def index():
    return render_template('index.html', usuario=session.get("usuario"), rol=session.get("rol"))

@app.route('/catalogo')
@_requiere_login
def catalogo():
    return render_template('catalogo.html', usuario=session.get("usuario"), rol=session.get("rol"))


# ── Blueprint /api ────────────────────────────────────────────────────────────

api = Blueprint('api', __name__, url_prefix='/api')

@api.route('/productos', methods=['GET'])
@csrf.exempt
@_solo_fetch
def api_listar():
    if not session.get("autenticado"):
        return jsonify({"error": "Forbidden"}), 403
    try:
        response = requests.get(f"{API_GATEWAY_URL}/consultar")
        if response.status_code == 200:
            return jsonify(response.json()), 200
        return jsonify({"error": "Error al obtener productos"}), 502
    except Exception as e:
        print(f"[ERROR api_listar]: {str(e)}")
        return jsonify({"error": "Error interno"}), 500

@api.route('/productos/<producto_id>', methods=['GET'])
@csrf.exempt
@_solo_fetch
def api_obtener(producto_id):
    if not session.get("autenticado"):
        return jsonify({"error": "Forbidden"}), 403
    if not validar_producto_id(producto_id):
        return jsonify({"error": "ID inválido"}), 400
    try:
        response = requests.get(f"{API_GATEWAY_URL}/consultar/{producto_id}")
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                producto = next((i for i in data if i.get('productoID') == producto_id), None)
            else:
                producto = data
            if not producto:
                return jsonify({"error": "Producto no encontrado"}), 404
            return jsonify(producto), 200
        return jsonify({"error": "Error al obtener producto"}), 502
    except Exception as e:
        print(f"[ERROR api_obtener]: {str(e)}")
        return jsonify({"error": "Error interno"}), 500

@api.route('/productos', methods=['POST'])
@csrf.exempt
@_solo_fetch
def api_crear():
    # SEGURIDAD: Solo administrador y vendedor pueden crear productos.
    if session.get("rol") not in ("administrador", "vendedor"):
        return jsonify({"error": "Forbidden"}), 403
    try:
        data = request.get_json(silent=True) or {}
        logistica = LogisticaEnvioDTO(
            alto=data.get('alto'), ancho=data.get('ancho'),
            profundidad=data.get('profundidad'), peso_kg=data.get('peso_kg'),
            requiere_fragil=data.get('requiere_fragil', False),
            tipo_empaque=data.get('tipo_empaque')
        )
        producto_dto = ProductoDTO(
            productoID=data.get('productoID'), categoria=data.get('categoria'),
            color=data.get('color'), logistica=logistica,
            material=data.get('material'), nombre=data.get('nombre'),
            precio=data.get('precio'), stock=data.get('stock'),
            talla=data.get('talla'), vendedorID=data.get('vendedorID')
        )
        response = requests.post(f"{API_GATEWAY_URL}/crear", json=producto_dto.to_dict())
        if response.status_code in [200, 201]:
            return jsonify({"mensaje": "Producto creado exitosamente"}), 201
        return jsonify({"error": "Error al crear el producto"}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[ERROR api_crear]: {str(e)}")
        return jsonify({"error": "Error interno"}), 500

@api.route('/productos/<producto_id>', methods=['PUT'])
@csrf.exempt
@_solo_fetch
def api_editar(producto_id):
    # SEGURIDAD: Solo administrador y vendedor pueden editar productos.
    if session.get("rol") not in ("administrador", "vendedor"):
        return jsonify({"error": "Forbidden"}), 403
    if not validar_producto_id(producto_id):
        return jsonify({"error": "ID inválido"}), 400
    try:
        data = request.get_json(silent=True) or {}
        logistica = LogisticaEnvioDTO(
            alto=data.get('alto'), ancho=data.get('ancho'),
            profundidad=data.get('profundidad'), peso_kg=data.get('peso_kg'),
            requiere_fragil=data.get('requiere_fragil', False),
            tipo_empaque=data.get('tipo_empaque')
        )
        producto_dto = ProductoDTO(
            productoID=producto_id, categoria=data.get('categoria'),
            color=data.get('color'), logistica=logistica,
            material=data.get('material'), nombre=data.get('nombre'),
            precio=data.get('precio'), stock=data.get('stock'),
            talla=data.get('talla'), vendedorID=data.get('vendedorID')
        )
        response = requests.put(f"{API_GATEWAY_URL}/modificar/{producto_id}", json=producto_dto.to_dict())
        if response.status_code == 200:
            return jsonify({"mensaje": "Producto actualizado exitosamente"}), 200
        return jsonify({"error": "Error al actualizar el producto"}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[ERROR api_editar]: {str(e)}")
        return jsonify({"error": "Error interno"}), 500

@api.route('/productos/<producto_id>', methods=['DELETE'])
@csrf.exempt
@_solo_fetch
def api_eliminar(producto_id):
    # SEGURIDAD: Solo el administrador puede eliminar productos.
    if session.get("rol") != "administrador":
        return jsonify({"error": "Forbidden"}), 403
    if not validar_producto_id(producto_id):
        return jsonify({"error": "ID inválido"}), 400
    try:
        response = requests.delete(f"{API_GATEWAY_URL}/eliminar/{producto_id}")
        if response.status_code == 200:
            return jsonify({"mensaje": "Producto eliminado correctamente"}), 200
        return jsonify({"error": "Error al eliminar el producto"}), 502
    except Exception as e:
        print(f"[ERROR api_eliminar]: {str(e)}")
        return jsonify({"error": "Error interno"}), 500

app.register_blueprint(api)

if __name__ == '__main__':
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, port=5000)
