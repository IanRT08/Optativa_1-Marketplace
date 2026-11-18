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
