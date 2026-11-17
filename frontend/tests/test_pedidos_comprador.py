"""Etapa 6: Mis pedidos (7.1), detalle del pedido (7.2) e historial de compras (7.4)."""
import api

PEDIDO = {"mensaje": "Consulta realizada", "pedido": {
    "id_pedido": 4, "fecha": "2026-11-16T10:05:00-06:00", "estado": "Pendiente", "total": 100000.0,
    "direccion": {"calle": "Av. Juárez", "numero": "120-B", "colonia": "Centro", "ciudad": "Monterrey",
                  "estado": "Nuevo León", "codigo_postal": "64000"},
    "pago": {"ultimos4": "4242", "estado": "Aprobado"},
    "productos": [{"id_producto": 120, "nombre": "iPhone 18", "id_variante": 11, "sku": "P120-M-ROJO",
                   "atributos": {"Color": "Rojo", "Talla": "M"}, "cantidad": 2, "precio_unitario": 50000.0,
                   "subtotal": 100000.0, "url_imagen": "https://ejemplo.com/a.png"}]}}


# --- 7.1 ----------------------------------------------------------------------
def test_71_lista_filtros_y_paginacion(R, cliente):
    R["/pedidos"] = {"mensaje": "Consulta realizada", "siguiente_cursor": 4, "pedidos": [
        {"id_pedido": 4, "fecha": "2026-11-16T10:05:00-06:00", "total": 1234.5, "estado": "Pendiente"}]}
    c = cliente("Comprador")
    h = c.get("/pedidos").get_data(as_text=True)
    assert "#4" in h and "Pendiente" in h and 'href="/pedidos/4"' in h
    assert R.llamadas[-1] == ("GET", "/pedidos", {})
    assert "cursor=4" in h and "Primera página" not in h
    h = c.get("/pedidos?estado=Enviado&fecha=2026-11-16&cursor=4").get_data(as_text=True)
    assert R.llamadas[-1][2] == {"estado": "Enviado", "fecha": "2026-11-16", "cursor": "4"}
    assert "Primera página" in h and "Quitar filtros" in h


def test_71_sin_pedidos_y_errores(R, cliente):
    c = cliente("Comprador")
    R["/pedidos"] = {"mensaje": "No tienes pedidos registrados", "pedidos": [], "siguiente_cursor": None}
    assert "No tienes pedidos registrados" in c.get("/pedidos").get_data(as_text=True)
    R["/pedidos"] = {"pedidos": "x"}
    assert "Ocurrió un error interno" in c.get("/pedidos").get_data(as_text=True)


def test_71_acceso_por_rol(R, cliente):
    assert cliente("Vendedor").get("/pedidos").status_code == 403
    assert not R.llamadas
    r = cliente().get("/pedidos")
    assert r.status_code == 302 and "login" in r.headers["Location"]


# --- 7.2 ----------------------------------------------------------------------
def test_72_detalle_completo_para_el_comprador(R, cliente):
    R["/pedidos/4"] = PEDIDO
    h = cliente("Comprador").get("/pedidos/4").get_data(as_text=True)
    assert "iPhone 18" in h and "Color: Rojo" in h
    assert "50,000.00" in h and "100,000.00" in h          # precio unitario histórico y total
    assert "Av. Juárez 120-B" in h and "terminada en 4242" in h
    assert "Actualizar estado" not in h and 'href="/pedidos"' in h


def test_72_errores(R, cliente):
    c = cliente("Comprador")
    R["/pedidos/5"] = api.AccesoRestringido(403, "Acceso restringido")
    r = c.get("/pedidos/5")
    assert r.status_code == 403 and "Acceso restringido" in r.get_data(as_text=True)
    with c.session_transaction() as s:
        assert s.get("token")                              # el 403 no cierra la sesión
    R["/pedidos/999"] = api.ApiError(404, "El pedido no existe")
    r = c.get("/pedidos/999")
    assert r.status_code == 404 and "El pedido no existe" in r.get_data(as_text=True)
    R["/pedidos/4"] = api.SesionExpirada(401, "Tu sesión no es válida o ya venció. Inicia sesión nuevamente")
    r = c.get("/pedidos/4")
    assert r.status_code == 302 and "login" in r.headers["Location"]


def test_72_administrador_no_usa_la_ruta_del_comprador(R, cliente):
    assert cliente("Administrador").get("/pedidos/4").status_code == 403
    assert not R.llamadas


# --- 7.4 ----------------------------------------------------------------------
def test_74_historial_y_total_comprado(R, cliente):
    c = cliente("Comprador")
    h = c.get("/historial").get_data(as_text=True)
    assert not R.llamadas and "Fecha inicial" in h          # primera visita: solo el formulario
    R["/historial/compras"] = {"mensaje": "Consulta realizada", "total_comprado": 1200.0, "pedidos": [
        {"id_pedido": 4, "fecha": "2026-11-16T10:05:00-06:00", "estado": "Cancelado", "total": 500.0, "suma_al_total": False},
        {"id_pedido": 5, "fecha": "2026-11-16T11:00:00-06:00", "estado": "Entregado", "total": 1200.0, "suma_al_total": True}]}
    h = c.get("/historial?fecha_inicio=2026-11-01&fecha_fin=2026-11-30").get_data(as_text=True)
    assert R.llamadas[-1] == ("GET", "/historial/compras", {"fecha_inicio": "2026-11-01", "fecha_fin": "2026-11-30"})
    assert h.count("No suma al total") == 1 and "Total comprado" in h and "1,200.00" in h


def test_74_sin_pedidos_y_fecha_faltante(R, cliente):
    c = cliente("Comprador")
    R["/historial/compras"] = {"mensaje": "No tienes pedidos registrados", "pedidos": [], "total_comprado": 0}
    h = c.get("/historial?fecha_inicio=2026-01-01&fecha_fin=2026-01-31").get_data(as_text=True)
    assert "No tienes pedidos registrados" in h and "Total comprado" not in h
    n = len(R.llamadas)
    h = c.get("/historial?fecha_inicio=2026-11-01").get_data(as_text=True)
    assert "Debe completar los campos obligatorios" in h and len(R.llamadas) == n


def test_reportes_de_ventas_comparten_plantilla(R, cliente):
    R["/vendedor/ventas"] = {"mensaje": "Consulta realizada", "total_ventas": 300.0, "productos": [
        {"id_producto": 1, "producto": "Gorra", "unidades_vendidas": 3, "total_vendido": 300.0}]}
    h = cliente("Vendedor").get("/vendedor/ventas?fecha_inicio=2026-11-01&fecha_fin=2026-11-30").get_data(as_text=True)
    assert "Gorra" in h and "Total de ventas" in h
