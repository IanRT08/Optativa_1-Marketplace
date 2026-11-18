"""Ajustes de interfaz del 2026-11-17 (pedidos por Ian)."""
import re
from pathlib import Path

PLANTILLAS = Path(__file__).resolve().parent.parent / "templates"


def test_todos_los_formularios_tienen_novalidate():
    # Sin novalidate el navegador muestra su burbuja en vez del error del DFR bajo el campo.
    faltan = []
    for ruta in PLANTILLAS.rglob("*.html"):
        for etiqueta in re.findall(r"<form\b[^>]*>", ruta.read_text(encoding="utf-8"), re.S):
            if "novalidate" not in etiqueta:
                faltan.append(f"{ruta.name}: {etiqueta[:60]}")
    assert not faltan, faltan


def test_contrasena_con_boton_mostrar(cliente):
    h = cliente().get("/login").get_data(as_text=True)
    assert 'class="campo-password"' in h
    assert re.search(r'<button type="button" class="btn-ver-password" aria-controls="c-password" '
                     r'aria-pressed="false" aria-label="Mostrar contraseña" hidden>', h)


def test_dialogo_de_confirmacion_en_base(cliente):
    h = cliente().get("/login").get_data(as_text=True)
    assert '<dialog id="dialogo-confirmar"' in h


def test_producto_ajeno_no_se_abre(R, cliente):
    # 3.9: la 3.2 (solo productos del vendedor) no trae el 9003 como primer renglón.
    R[("GET", "/vendedor/productos")] = {"productos": [{"id_producto": 9500}], "siguiente_cursor": None}
    R["/productos/9003"] = {"producto": {"id_producto": 9003}}
    c = cliente("Vendedor")
    for ruta in ("/vendedor/productos/9003/editar", "/vendedor/productos/9003/variantes"):
        r = c.get(ruta)
        assert r.status_code == 403 and "Acceso restringido" in r.get_data(as_text=True)
    assert not any(ruta == "/productos/9003" for _, ruta, _ in R.llamadas)   # ni siquiera se consulta


def test_rango_de_precio_invalido_muestra_productos(monkeypatch, cliente):
    # 4.3: el error va debajo del precio mínimo y la pantalla no queda vacía:
    # se muestran los productos sin el rango de precio, y los enlaces no lo llevan.
    import api
    llamadas = []

    def simulada(metodo, ruta, params=None, **kw):
        if ruta == "/productos":
            llamadas.append(params)
        if params and "precio_min" in params:
            raise api.ApiError(400, "El precio mínimo no puede ser mayor al máximo")
        return {"productos": [{"id_producto": 9003, "nombre": "Celular X", "precio": 250}],
                "siguiente_cursor": "abc"}

    monkeypatch.setattr(api, "llamar", simulada)
    h = cliente().get("/?q=cel&precio_min=500&precio_max=100").get_data(as_text=True)
    assert "El precio mínimo no puede ser mayor al máximo" in h
    assert "Celular X" in h
    assert llamadas[-1] == {"q": "cel"}
    assert "cursor=abc" in h and "precio_min=500" not in h.split('class="rejilla-productos"')[1]


def test_estado_vacio_centrado():
    css = (PLANTILLAS.parent / "static" / "css" / "app.css").read_text(encoding="utf-8")
    regla = re.search(r"\.vacio \{[^}]*\}", css).group(0)
    assert "align-items: center" in regla and "text-align: center" in regla


def test_recibo_centrado_y_alerta_se_cierra_sola(cliente):
    # 5.15: recibo en una caja centrada; el aviso de éxito se cierra solo como en las demás pantallas.
    c = cliente("Comprador")
    with c.session_transaction() as s:
        s["ultima_compra"] = {"id_pedido": 5, "total": 455.97}
    h = c.get("/compra/realizada").get_data(as_text=True)
    assert '<div class="recibo">' in h and 'class="panel recibo-caja"' in h
    assert re.search(r'class="alerta[^"]*"[^>]*data-autocerrar', h)


def test_volver_al_catalogo_conserva_filtros(R, cliente):
    # Del detalle se regresa a la misma búsqueda (categoría y página), no al catálogo general.
    from test_errores_campo import PRODUCTO
    R["/productos"] = {"productos": [], "siguiente_cursor": None}
    R["/productos/1"] = PRODUCTO
    c = cliente()
    c.get("/?q=&id_categoria=7&precio_min=&cursor=abc")
    h = c.get("/productos/1").get_data(as_text=True)
    volver = re.search(r'<p class="volver"><a href="([^"]+)"', h).group(1)
    assert "id_categoria=7" in volver and "cursor=abc" in volver and "precio_min" not in volver
    c.get("/")   # sin filtros: el regreso vuelve a ser el catálogo general
    h = c.get("/productos/1").get_data(as_text=True)
    assert re.search(r'<p class="volver"><a href="/"', h)


def test_filas_de_pedidos_abren_el_detalle(R, cliente):
    # La fila completa abre el pedido: el enlace principal va marcado para app.js.
    R[("GET", "/pedidos")] = {"pedidos": [{"id_pedido": 5, "fecha": "2026-11-18 11:13", "total": 455.97,
                                           "estado": "Pendiente"}], "siguiente_cursor": None}
    h = cliente("Comprador").get("/pedidos").get_data(as_text=True)
    assert re.search(r'<a data-fila-enlace href="/pedidos/5">', h)
    js = (PLANTILLAS.parent / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "a[data-fila-enlace]" in js


def test_fecha_invalida_muestra_mes_actual_y_calendario_limitado(R, cliente):
    # 8.1: con el rango invertido, el error va bajo el campo y la tabla muestra el mes actual.
    import api
    import reportes

    def simulada(metodo, ruta, params=None, **kw):
        if params and params["fecha_inicio"] > params["fecha_fin"]:
            raise api.ApiError(400, "La fecha inicial no puede ser mayor a la fecha final")
        return {"mensaje": "Consulta realizada", "total_ventas": 300.0, "productos": [
            {"id_producto": 1, "producto": "Gorra", "unidades_vendidas": 3, "total_vendido": 300.0}]}

    from unittest import mock
    with mock.patch.object(api, "llamar", simulada):
        h = cliente("Vendedor").get("/vendedor/ventas?fecha_inicio=2026-12-01&fecha_fin=2026-11-01").get_data(as_text=True)
    assert "La fecha inicial no puede ser mayor a la fecha final" in h and "Gorra" in h
    assert "Mostrando del 01/" in h and 'value="2026-12-01"' in h     # se conserva lo que escribió
    assert f'min="2026-01-01" max="{reportes.hoy().isoformat()}"' in h


def test_alerta_de_error_de_arriba_se_cierra_sola(cliente):
    from flask import render_template_string
    import app as modulo
    with modulo.app.test_request_context():
        h = render_template_string('{% import "macros.html" as ui %}{{ ui.mensaje("error", "x", autocerrar=True) }}'
                                   '{{ ui.mensaje("error", "y") }}')
    assert h.count("data-autocerrar") == 1     # solo la de arriba (flash); la de la página se queda
