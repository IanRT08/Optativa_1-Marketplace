from flask import Flask, render_template, request, redirect, url_for, flash
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
    """Retorna True si el ID tiene formato válido, False si es sospechoso."""
    return bool(ID_PATTERN.match(producto_id))

@app.route('/')
def index():
    try:
        # Consume el endpoint GET /consultar
        response = requests.get(f"{API_GATEWAY_URL}/consultar")
        productos = response.json() if response.status_code == 200 else []
    except Exception as e:
        productos = []
        # SEGURIDAD: No se expone el detalle de la excepción al usuario para no filtrar información interna.
        flash("Error al conectar con el servidor. Intente nuevamente.", "error")
    
    return render_template('index.html', productos=productos)

@app.route('/crear', methods=['GET', 'POST'])
def crear():
    if request.method == 'POST':
        try:
            # Mapeo usando DTO
            logistica = LogisticaEnvioDTO(
                alto=request.form.get('alto'),
                ancho=request.form.get('ancho'),
                profundidad=request.form.get('profundidad'),
                peso_kg=request.form.get('peso_kg'),
                requiere_fragil=True if request.form.get('requiere_fragil') == 'on' else False,
                tipo_empaque=request.form.get('tipo_empaque')
            )
            
            producto_dto = ProductoDTO(
                productoID=request.form.get('productoID'),
                categoria=request.form.get('categoria'),
                color=request.form.get('color'),
                logistica=logistica,
                material=request.form.get('material'),
                nombre=request.form.get('nombre'),
                precio=request.form.get('precio'),
                stock=request.form.get('stock'),
                talla=request.form.get('talla'),
                vendedorID=request.form.get('vendedorID')
            )

            # CORREGIDO: Apunta al endpoint POST /crear de tu API Gateway
            response = requests.post(f"{API_GATEWAY_URL}/crear", json=producto_dto.to_dict())

            if response.status_code in [200, 201]:
                flash("Producto creado exitosamente", "success")
                return redirect(url_for('index'))
            else:
                # SEGURIDAD: No se reenvía response.text al usuario para no exponer detalles de la API/AWS.
                flash("Error al crear el producto. Intente nuevamente.", "error")
        except Exception as e:
            # SEGURIDAD: Se registra el error internamente pero no se muestra al usuario.
            print(f"[ERROR crear]: {str(e)}")
            flash("Ocurrió un error interno. Intente nuevamente.", "error")

    return render_template('form.html', accion="Crear", producto=None)

@app.route('/editar/<producto_id>', methods=['GET', 'POST'])
def editar(producto_id):
    # SEGURIDAD: Se valida el formato del ID antes de usarlo en la URL de la API (previene NoSQL Injection y Path Traversal).
    if not validar_producto_id(producto_id):
        flash("ID de producto inválido.", "error")
        return redirect(url_for('index'))
    if request.method == 'GET':
        producto = None
        try:
            response = requests.get(f"{API_GATEWAY_URL}/consultar/{producto_id}")
            if response.status_code == 200:
                data = response.json()
                # Si por error la API devolvió una lista, filtramos exactamente el productoID que buscamos
                if isinstance(data, list):
                    for item in data:
                        if item.get('productoID') == producto_id:
                            producto = item
                            break
                elif isinstance(data, dict):
                    producto = data
        except Exception as e:
            print(f"[ERROR editar GET]: {str(e)}")
            # SEGURIDAD: No se expone el detalle de la excepción al usuario.
            flash("Error al obtener el producto. Intente nuevamente.", "error")
            
        return render_template('form.html', accion="Editar", producto=producto)
    
    if request.method == 'POST':
        try:
            logistica = LogisticaEnvioDTO(
                alto=request.form.get('alto'),
                ancho=request.form.get('ancho'),
                profundidad=request.form.get('profundidad'),
                peso_kg=request.form.get('peso_kg'),
                requiere_fragil=True if request.form.get('requiere_fragil') == 'on' else False,
                tipo_empaque=request.form.get('tipo_empaque')
            )
            
            producto_dto = ProductoDTO(
                productoID=producto_id,
                categoria=request.form.get('categoria'),
                color=request.form.get('color'),
                logistica=logistica,
                material=request.form.get('material'),
                nombre=request.form.get('nombre'),
                precio=request.form.get('precio'),
                stock=request.form.get('stock'),
                talla=request.form.get('talla'),
                vendedorID=request.form.get('vendedorID')
            )

            # Consume el endpoint PUT /modificar/{productoID}
            response = requests.put(f"{API_GATEWAY_URL}/modificar/{producto_id}", json=producto_dto.to_dict())

            if response.status_code == 200:
                flash("Producto actualizado exitosamente", "success")
                return redirect(url_for('index'))
            else:
                # SEGURIDAD: No se reenvía response.text al usuario para no exponer detalles de la API/AWS.
                flash("Error al actualizar el producto. Intente nuevamente.", "error")
        except Exception as e:
            print(f"[ERROR editar POST]: {str(e)}")
            # SEGURIDAD: Se registra el error internamente pero no se muestra al usuario.
            flash("Ocurrió un error interno. Intente nuevamente.", "error")

    return redirect(url_for('index'))

@app.route('/eliminar/<producto_id>', methods=['POST'])
def eliminar(producto_id):
    # SEGURIDAD: Se valida el formato del ID antes de usarlo en la URL de la API (previene NoSQL Injection y Path Traversal).
    if not validar_producto_id(producto_id):
        flash("ID de producto inválido.", "error")
        return redirect(url_for('index'))
    try:
        # Consume el endpoint DELETE /eliminar/{productoID} que creaste en API Gateway
        response = requests.delete(f"{API_GATEWAY_URL}/eliminar/{producto_id}")
        if response.status_code == 200:
            flash("Producto eliminado correctamente", "success")
        else:
            # SEGURIDAD: No se reenvía response.text al usuario para no exponer detalles de la API/AWS.
            flash("Error al eliminar el producto. Intente nuevamente.", "error")
    except Exception as e:
        print(f"[ERROR eliminar]: {str(e)}")
        # SEGURIDAD: Se registra el error internamente pero no se muestra al usuario.
        flash("Ocurrió un error interno. Intente nuevamente.", "error")
    return redirect(url_for('index'))

@app.route('/detalle/<producto_id>')
def detalle(producto_id):
    # SEGURIDAD: Se valida el formato del ID antes de usarlo en la URL de la API (previene NoSQL Injection y Path Traversal).
    if not validar_producto_id(producto_id):
        flash("ID de producto inválido.", "error")
        return redirect(url_for('index'))
    producto = None
    try:
        response = requests.get(f"{API_GATEWAY_URL}/consultar/{producto_id}")
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                # Buscamos si la lista contiene el producto específico
                for item in data:
                    if item.get('productoID') == producto_id:
                        producto = item
                        break
            elif isinstance(data, dict):
                producto = data
        else:
            # SEGURIDAD: No se reenvía el status code ni response.text de AWS al usuario.
            flash("Error al obtener el producto. Intente nuevamente.", "error")
            return redirect(url_for('index'))
            
    except Exception as e:
        print(f"[ERROR detalle]: {str(e)}")
        # SEGURIDAD: Se registra el error internamente pero no se muestra al usuario.
        flash("Ocurrió un error interno. Intente nuevamente.", "error")
        return redirect(url_for('index'))

    if not producto:
        flash("No se pudo cargar la información del producto.", "error")
        return redirect(url_for('index'))

    return render_template('detalle.html', producto=producto)

if __name__ == '__main__':
    # SEGURIDAD: El modo debug se controla desde variable de entorno.
    # En producción debe estar ausente o en 'false'. Con debug=True Flask expone
    # una consola interactiva de Python en el navegador al ocurrir errores.
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, port=5000)