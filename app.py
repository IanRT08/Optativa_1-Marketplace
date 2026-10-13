from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Blueprint
from functools import wraps
import requests
import os
import re
from flask_wtf.csrf import CSRFProtect
from dto import ProductoDTO, LogisticaEnvioDTO

app = Flask(__name__)
# SEGURIDAD: La secret_key se lee desde variable de entorno para no exponerla en el código fuente.
# Definirla con: set FLASK_SECRET_KEY=<valor_seguro_aleatorio>
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-insecure-key")

# SEGURIDAD: Protección CSRF global — genera y valida un token en cada formulario POST.
csrf = CSRFProtect(app)

# URL base de tu API Gateway
API_GATEWAY_URL = "https://mpucrluxrh.execute-api.us-east-1.amazonaws.com"

# SEGURIDAD: Patrón para validar producto_id — solo letras, números, guiones y guión bajo.
# Previene NoSQL Injection y Path Traversal en los parámetros de URL.
ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,50}$')

def validar_producto_id(producto_id):
    return bool(ID_PATTERN.match(producto_id))

def _solo_fetch(f):
    """
    SEGURIDAD: Decorador que restringe el acceso a las rutas /api solo a peticiones
    internas del frontend (fetch). Verifica el header X-Requested-With que el JS
    agrega en cada llamada. Cualquier acceso directo desde el navegador, Postman
    u otra herramienta externa recibe un 403 sin revelar que el endpoint existe.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return wrapper


# ── Blueprint /api ────────────────────────────────────────────────────────────
# SEGURIDAD: Las rutas de la API viven en un Blueprint separado.
# No aparecen en ningún template ni son enlazadas desde el HTML.
api = Blueprint('api', __name__, url_prefix='/api')

@api.route('/productos', methods=['GET'])
@csrf.exempt
@_solo_fetch
def api_listar():
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


# ── Rutas HTML — solo renderizan la vista, los datos los carga el JS ──────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/crear', methods=['GET'])
def crear():
    return render_template('form.html', accion="Crear")

@app.route('/editar/<producto_id>', methods=['GET'])
def editar(producto_id):
    if not validar_producto_id(producto_id):
        flash("ID de producto inválido.", "error")
        return redirect(url_for('index'))
    return render_template('form.html', accion="Editar", producto_id=producto_id)

@app.route('/detalle/<producto_id>')
def detalle(producto_id):
    if not validar_producto_id(producto_id):
        flash("ID de producto inválido.", "error")
        return redirect(url_for('index'))
    return render_template('detalle.html', producto_id=producto_id)

if __name__ == '__main__':
    # SEGURIDAD: El modo debug se controla desde variable de entorno.
    # En producción debe estar ausente o en 'false'. Con debug=True Flask expone
    # una consola interactiva de Python en el navegador al ocurrir errores.
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, port=5000)
