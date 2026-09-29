from flask import Flask, render_template, request, redirect, url_for, flash
import requests
from dto import ProductoDTO, LogisticaEnvioDTO

app = Flask(__name__)
app.secret_key = "clave_secreta_flask_segura"

# URL base de tu API Gateway
API_GATEWAY_URL = ""

@app.route('/')
def index():
    try:
        # Consume el endpoint GET /consultar
        response = requests.get(f"{API_GATEWAY_URL}/consultar")
        productos = response.json() if response.status_code == 200 else []
    except Exception as e:
        productos = []
        flash(f"Error al conectar con la API: {str(e)}", "error")
    
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
                flash(f"Error en la API: {response.text}", "error")
        except Exception as e:
            flash(f"Excepción: {str(e)}", "error")

    return render_template('form.html', accion="Crear", producto=None)

@app.route('/editar/<producto_id>', methods=['GET', 'POST'])
def editar(producto_id):
    if request.method == 'GET':
        producto = None
        try:
            # Consume el endpoint GET /consultar/{productoID}
            response = requests.get(f"{API_GATEWAY_URL}/consultar/{producto_id}")
            if response.status_code == 200:
                data = response.json()
                # Si la API devolvió una lista por error, tomamos el primer elemento
                if isinstance(data, list) and len(data) > 0:
                    producto = data[0]
                elif isinstance(data, dict):
                    producto = data
        except Exception as e:
            flash(f"Error al obtener producto: {str(e)}", "error")
            
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
                flash(f"Error al actualizar en la API: {response.text}", "error")
        except Exception as e:
            flash(f"Excepción: {str(e)}", "error")

    return redirect(url_for('index'))

@app.route('/eliminar/<producto_id>', methods=['POST'])
def eliminar(producto_id):
    try:
        # Consume el endpoint DELETE /eliminar/{productoID} que creaste en API Gateway
        response = requests.delete(f"{API_GATEWAY_URL}/eliminar/{producto_id}")
        if response.status_code == 200:
            flash("Producto eliminado correctamente", "success")
        else:
            flash(f"Error al eliminar: {response.text}", "error")
    except Exception as e:
        flash(f"Excepción: {str(e)}", "error")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)