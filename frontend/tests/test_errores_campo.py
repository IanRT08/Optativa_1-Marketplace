"""Errores debajo de cada campo (errores_campo.py) con los textos exactos del DFR."""
from api import ApiError as E
from conftest import arriba, bajo, grupo

OB = "Debe completar los campos obligatorios"
REGISTRO = {"nombre": "Ana", "apellido": "López", "email": "ana@x.test", "password": "Buena123!", "confirmar_password": "Buena123!"}
CARRITO = {"mensaje": "Consulta realizada", "total": 10.0, "puede_comprar": True, "items": [
    {"id_producto": 1, "id_variante": 7, "nombre": "Gorra", "sku": "P1-STD", "atributos": {}, "precio": 10.0, "cantidad": 1,
     "subtotal": 10.0, "stock": 5, "disponible": True, "stock_suficiente": True, "url_imagen": None}]}
PRODUCTO = {"producto": {"id_producto": 1, "nombre": "Gorra", "marca": "M", "categoria": "C", "id_categoria": 1, "precio": 10.0,
                         "vendedor": "V", "stock": 5, "disponible": True, "descripcion": "", "url_imagen": None,
                         "variantes": [{"id_variante": 7, "sku": "P1-STD", "atributos": {}, "stock": 5, "disponible": True}]}}
CATALOGOS = {
    "/categorias": {"categorias": [{"id_categoria": 1, "nombre": "Audio", "descripcion": None, "id_categoria_padre": None, "categoria_padre": None}]},
    "/marcas": {"marcas": [{"id_marca": 1, "nombre": "Sonora"}]},
    "/atributos": {"atributos": [{"id_atributo": 1, "nombre": "Color", "valores": [{"id_valor": 1, "valor": "Negro"}]},
                                 {"id_atributo": 2, "nombre": "Talla", "valores": [{"id_valor": 3, "valor": "M"}]}]},
}


def _catalogos(R):
    for ruta, datos in CATALOGOS.items():
        R[ruta] = datos


def test_login(R, cliente):
    h = cliente().post("/login", data={"email": "", "password": ""}).get_data(as_text=True)
    assert bajo(h, "c-email", OB) and bajo(h, "c-password", OB) and not arriba(h, OB)
    R[("POST", "/auth/login")] = E(401, "Contraseña incorrecta")
    h = cliente().post("/login", data={"email": "ana@x.test", "password": "Mala1234!"}).get_data(as_text=True)
    assert bajo(h, "c-password", "Contraseña incorrecta") and 'value="ana@x.test"' in h
    R[("POST", "/auth/login")] = E(403, "La cuenta se encuentra inactiva")
    h = cliente().post("/login", data={"email": "ana@x.test", "password": "Mala1234!"}).get_data(as_text=True)
    assert arriba(h, "La cuenta se encuentra inactiva") and "aria-invalid" not in h


def test_registro(R, cliente):
    R[("POST", "/usuarios/registro")] = E(409, "El correo electrónico ya está registrado")
    h = cliente().post("/registro", data=REGISTRO).get_data(as_text=True)
    assert bajo(h, "c-email", "El correo electrónico ya está registrado")
    assert 'value="López"' in h and "Buena123!" not in h       # la contraseña nunca regresa
    R[("POST", "/usuarios/registro")] = E(400, "El apellido no puede tener espacios en blanco seguidos")
    h = cliente().post("/registro", data=dict(REGISTRO, apellido="Ló  pez")).get_data(as_text=True)
    assert bajo(h, "c-apellido", "El apellido no puede tener espacios en blanco seguidos")
    R[("POST", "/usuarios/registro")] = E(400, "El nombre y el apellido no pueden superar 80 caracteres")
    h = cliente().post("/registro", data=dict(REGISTRO, nombre="A" * 81)).get_data(as_text=True)
    assert bajo(h, "c-nombre", "El nombre y el apellido no pueden superar 80 caracteres") and 'id="c-apellido-error"' not in h


def test_direccion_y_compra(R, cliente):
    R["/direcciones"] = {"mensaje": "Consulta realizada", "direcciones": [
        {"id_direccion": 1, "calle": "A", "numero": "1", "colonia": "B", "ciudad": "C", "estado": "D", "codigo_postal": "64000"}]}
    R[("POST", "/direcciones")] = E(400, "El código postal debe tener 5 dígitos")
    datos = {"calle": "Av. Juárez", "numero": "12", "colonia": "Centro", "ciudad": "Monterrey", "estado": "NL", "codigo_postal": "640"}
    h = cliente("Comprador").post("/direcciones", data=datos).get_data(as_text=True)
    assert bajo(h, "c-codigo_postal", "El código postal debe tener 5 dígitos") and 'value="Av. Juárez"' in h
    R["/carrito"] = CARRITO
    R[("POST", "/compras")] = E(400, "Datos de pago no válidos")
    h = cliente("Comprador").post("/compra", data={"id_direccion": "1", "numero_tarjeta": "1234", "cvv": "123"}).get_data(as_text=True)
    assert bajo(h, "c-numero_tarjeta", "Datos de pago no válidos") and 'id="c-cvv-error"' not in h and 'value="1234"' not in h
    R[("POST", "/compras")] = E(400, OB)
    h = cliente("Comprador").post("/compra", data={"numero_tarjeta": "4242424242424242", "cvv": "123"}).get_data(as_text=True)
    assert grupo(h, "id_direccion", OB)
    R[("POST", "/compras")] = E(400, "Stock insuficiente para el producto Gorra")
    h = cliente("Comprador").post("/compra", data={"id_direccion": "1", "numero_tarjeta": "4242424242424242", "cvv": "123"}).get_data(as_text=True)
    assert arriba(h, "Stock insuficiente para el producto Gorra")


def test_carrito_tras_redirigir(R, cliente):
    R["/productos/1"] = PRODUCTO
    R["/carrito"] = CARRITO
    R[("POST", "/carrito/items")] = E(400, "La cantidad solicitada supera el stock disponible")
    c = cliente("Comprador")
    r = c.post("/carrito/agregar", data={"id_producto": "1", "cantidad": "9"})
    h = c.get(r.headers["Location"]).get_data(as_text=True)
    assert bajo(h, "c-cantidad", "La cantidad solicitada supera el stock disponible") and 'value="9"' in h
    assert 'id="c-cantidad-error"' not in c.get("/productos/1").get_data(as_text=True)   # una sola vez
    R[("PUT", "/carrito/items/7")] = E(400, "La cantidad solicitada supera el stock disponible")
    c.post("/carrito/7/cantidad", data={"cantidad": "8"})
    h = c.get("/carrito").get_data(as_text=True)
    assert grupo(h, "cantidad-7", "La cantidad solicitada supera el stock disponible")
    assert 'value="8"' in h and 'aria-describedby="error-cantidad-7"' in h


def test_vendedor(R, cliente):
    _catalogos(R)
    pf = {"nombre": "Gorra", "descripcion": "Gorra azul", "precio": "10.999", "stock": "3", "id_marca": "1",
          "id_categoria": "1", "url_imagen": "https://x.test/a.png"}
    R[("POST", "/vendedor/productos")] = E(400, "El precio no es válido")
    h = cliente("Vendedor").post("/vendedor/productos/nuevo", data=pf).get_data(as_text=True)
    assert bajo(h, "c-precio", "El precio no es válido") and 'value="Gorra"' in h
    esp = ("Se admiten hasta 20 especificaciones, con nombre de hasta 50 caracteres y valor de texto de hasta 200, "
           "sin nombres repetidos")
    R[("POST", "/vendedor/productos")] = E(400, esp)
    h = cliente("Vendedor").post("/vendedor/productos/nuevo", data=dict(pf, precio="10")).get_data(as_text=True)
    assert grupo(h, "especificaciones", esp)
    largo = "El nombre no puede superar 200 caracteres, la descripción 1000 y la URL de imagen 500"
    R[("POST", "/vendedor/productos")] = E(400, largo)
    h = cliente("Vendedor").post("/vendedor/productos/nuevo", data=dict(pf, precio="10", descripcion="x" * 1001)).get_data(as_text=True)
    assert bajo(h, "c-descripcion", largo) and 'id="c-nombre-error"' not in h
    R["/productos/5"] = {"producto": dict(PRODUCTO["producto"], id_producto=5)}
    R[("GET", "/vendedor/productos")] = {"productos": [{"id_producto": 5}], "siguiente_cursor": None}  # es suyo
    R[("POST", "/vendedor/productos/5/variantes")] = E(400, "No puedes elegir dos valores del mismo atributo")
    h = cliente("Vendedor").post("/vendedor/productos/5/variantes", data={"valores": ["1", "3"], "stock": "2"}).get_data(as_text=True)
    assert grupo(h, "valores", "No puedes elegir dos valores del mismo atributo")
    assert h.count("No puedes elegir dos valores del mismo atributo") == 1
    R[("POST", "/vendedor/stock-masivo")] = E(400, "No se encontraron productos para actualizar")
    h = cliente("Vendedor").post("/vendedor/stock-masivo", data={"id_categoria": "1", "cantidad": "5"}).get_data(as_text=True)
    assert bajo(h, "c-id_categoria", "No se encontraron productos para actualizar")


def test_filtros_y_reportes(R, cliente):
    R["/vendedor/ventas"] = E(400, "La fecha inicial no puede ser mayor a la fecha final")
    h = cliente("Vendedor").get("/vendedor/ventas?fecha_inicio=2026-12-01&fecha_fin=2026-11-01").get_data(as_text=True)
    assert bajo(h, "c-fecha_inicio", "La fecha inicial no puede ser mayor a la fecha final")
    R["/historial/compras"] = E(400, "La fecha no es válida")
    h = cliente("Comprador").get("/historial?fecha_inicio=2026-02-30&fecha_fin=2026-03-01").get_data(as_text=True)
    assert bajo(h, "c-fecha_inicio", "La fecha no es válida") and 'id="c-fecha_fin-error"' not in h
    R["/pedidos"] = E(400, "El estado seleccionado no es válido")
    h = cliente("Comprador").get("/pedidos?estado=Raro").get_data(as_text=True)
    assert bajo(h, "c-estado", "El estado seleccionado no es válido")
    R["/productos"] = E(400, "El precio no es válido")
    h = cliente().get("/?precio_min=abc&precio_max=10").get_data(as_text=True)
    assert bajo(h, "c-precio_min", "El precio no es válido") and 'id="c-precio_max-error"' not in h
    assert 'class="filtros-extra abierto"' in h


def test_administrador(R, cliente):
    _catalogos(R)
    R[("POST", "/admin/usuarios")] = E(400, "El rol seleccionado no es válido")
    h = cliente("Administrador").post("/admin/usuarios/nuevo", data={
        "nombre": "Luis", "apellido": "P", "email": "l@x.test", "password": "Buena123!", "rol": "Jefe"}).get_data(as_text=True)
    assert bajo(h, "c-rol", "El rol seleccionado no es válido")
    R[("POST", "/categorias")] = E(409, "La categoría ya existe")
    h = cliente("Administrador").post("/admin/categorias", data={"nombre": "Audio", "descripcion": "", "id_categoria_padre": ""}).get_data(as_text=True)
    assert bajo(h, "c-nombre", "La categoría ya existe")
    R["/pedidos/120"] = {"pedido": {"id_pedido": 120, "fecha": "", "estado": "Pendiente", "total": 1.0, "productos": [],
                                    "direccion": None, "comprador": "Ana"}}
    c = cliente("Administrador")
    R[("PATCH", "/admin/pedidos/120/estado")] = E(400, "El pedido no puede cambiar a ese estado")
    c.post("/admin/pedidos/120/estado", data={"estado": "Entregado"})
    assert arriba(c.get("/admin/pedidos/120").get_data(as_text=True), "El pedido no puede cambiar a ese estado")
    R[("PATCH", "/admin/pedidos/120/estado")] = E(400, "El estado seleccionado no es válido")
    c.post("/admin/pedidos/120/estado", data={"estado": "Enviado"})
    assert bajo(c.get("/admin/pedidos/120").get_data(as_text=True), "c-estado", "El estado seleccionado no es válido")
