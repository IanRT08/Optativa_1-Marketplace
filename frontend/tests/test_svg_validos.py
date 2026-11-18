"""Los SVG se interpretan como XML estricto: si están mal formados, el navegador
no los dibuja (p. ej. "--" dentro de un comentario dejó el favicon sin mostrarse)."""
from pathlib import Path
from xml.dom import minidom

import pytest

SVGS = sorted((Path(__file__).resolve().parent.parent / "static").rglob("*.svg"))


def test_hay_svgs():
    assert SVGS


@pytest.mark.parametrize("ruta", SVGS, ids=lambda p: p.name)
def test_svg_es_xml_valido(ruta):
    minidom.parse(str(ruta))
