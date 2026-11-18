"""Reportes por rango de fechas: 7.4 (historial de compras), 8.1 y 8.2 (ventas).

Ajustes de Ian (2026-11-18):
- La pantalla abre con el mes actual (del día 1 a hoy) y su reporte.
- Si las fechas tienen error, el error queda debajo del campo y la tabla
  muestra el mes actual, con la nota del periodo mostrado.
- El calendario solo deja elegir del 01/01/2026 a hoy (atributos min y max).
  El DFR no tiene mensaje para fechas fuera de ese rango, así que una fecha
  escrita a mano se consulta igual.
"""
from datetime import date, datetime, timedelta, timezone

from flask import g

import api
from constantes import MSG_ERROR_INTERNO
from dtos import ErrorRespuesta, ErrorValidacion
from errores_campo import asignar

ZONA_MEXICO = timezone(timedelta(hours=-6))   # igual que time_zone de la Layer 2
FECHA_MINIMA = "2026-01-01"


def hoy():
    return datetime.now(ZONA_MEXICO).date()


def mes_actual():
    dia = hoy()
    return {"fecha_inicio": dia.replace(day=1).isoformat(), "fecha_fin": dia.isoformat()}


def _dma(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def consultar(args, pedir, extra=()):
    """Arma lo que necesita reporte_ventas.html.

    pedir(datos) llama a la API con un diccionario de filtros y regresa el DTO.
    extra: filtros además de las fechas (8.2: id_vendedor). Si no se eligió
    uno, la primera vez solo se muestra el formulario.
    """
    campos = (*extra, "fecha_inicio", "fecha_fin")
    datos = {c: (args.get(c) or "").strip() for c in campos}
    enviado = any(datos.values())
    if not datos["fecha_inicio"] and not datos["fecha_fin"]:
        datos.update(mes_actual())
    resultado = {"fechas": datos, "reporte": None, "error": None, "periodo": None,
                 "limites": {"min": FECHA_MINIMA, "max": hoy().isoformat()}}
    if not enviado and any(not datos[c] for c in extra):
        return resultado
    try:
        resultado["reporte"] = pedir(datos)
    except (ErrorValidacion, api.ApiError) as exc:
        mensaje = getattr(exc, "mensaje", None) or str(exc)
        if not asignar(mensaje, "reporte", datos):
            resultado["error"] = mensaje
        elif not set(g.errores) & set(extra):
            # Solo fallaron las fechas: en lugar de dejar la tabla vacía se
            # muestra el mes actual (con los demás filtros que sí son válidos).
            respaldo = {**{c: datos[c] for c in extra}, **mes_actual()}
            try:
                resultado["reporte"] = pedir(respaldo)
                resultado["periodo"] = {"desde": _dma(respaldo["fecha_inicio"]),
                                        "hasta": _dma(respaldo["fecha_fin"])}
            except (ErrorValidacion, api.ApiError, ErrorRespuesta):
                resultado["reporte"] = None
    except ErrorRespuesta:
        resultado["error"] = MSG_ERROR_INTERNO
    return resultado
