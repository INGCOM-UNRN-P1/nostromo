"""Diferencia pedagógica entre la salida esperada y la obtenida.

El diff unificado («--- esperado») no le dice al estudiante qué mirar: si sobra un espacio, si
falta la última línea o si imprimió `3.50` en lugar de `3.5`, el mensaje era el mismo «no coincide
la salida». Acá se ubica la primera diferencia (línea y columna), se hacen visibles los espacios,
tabulaciones y retornos de carro, y se compara con tolerancia numérica cuando se pide
(`--float-epsilon`, QoL #751).
"""

from __future__ import annotations

import math
import re
from typing import List, Optional

_VISIBLES = {" ": "·", "\t": "→", "\r": "␍", " ": "⍽"}
_NUMERO = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def hacer_visible(texto: str) -> str:
    """Espacios como `·`, tabulaciones como `→`, `\\r` como `␍` y espacio duro como `⍽`."""
    return "".join(_VISIBLES.get(c, c) for c in texto)


def _iguales_con_tolerancia(esperada: str, obtenida: str, epsilon: float) -> bool:
    a, b = esperada.split(), obtenida.split()
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        if not (_NUMERO.match(x) and _NUMERO.match(y)):
            return False
        if not math.isclose(float(x), float(y), rel_tol=0.0, abs_tol=epsilon):
            return False
    return True


def lineas_equivalentes(esperada: str, obtenida: str, epsilon: Optional[float] = None) -> bool:
    if esperada == obtenida:
        return True
    return epsilon is not None and _iguales_con_tolerancia(esperada, obtenida, epsilon)


def salidas_equivalentes(esperado: List[str], obtenido: List[str], epsilon: Optional[float] = None) -> bool:
    """Igualdad línea a línea; con `epsilon`, los números que difieren a lo sumo en epsilon cuentan
    como iguales (y el resto de las palabras tiene que coincidir)."""
    return len(esperado) == len(obtenido) and all(
        lineas_equivalentes(e, o, epsilon) for e, o in zip(esperado, obtenido))


def _primera_columna_distinta(a: str, b: str) -> int:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def explicar_diferencia(esperado: List[str], obtenido: List[str], epsilon: Optional[float] = None) -> str:
    """Una o dos oraciones sobre la primera diferencia, pensadas para el estudiante."""
    for n, (e, o) in enumerate(zip(esperado, obtenido), 1):
        if lineas_equivalentes(e, o, epsilon):
            continue
        if e.split() == o.split():
            col = _primera_columna_distinta(e, o) + 1
            return (f"Línea {n}: el texto coincide pero difieren los espacios (columna {col}). "
                    f"Se esperaba «{hacer_visible(e)}» y se obtuvo «{hacer_visible(o)}» "
                    "(· espacio, → tabulación, ␍ retorno de carro).")
        if e.lower() == o.lower():
            return f"Línea {n}: difieren las mayúsculas y minúsculas. Se esperaba «{e}» y se obtuvo «{o}»."
        if _solo_numeros_distintos(e, o):
            return (f"Línea {n}: difiere un número. Se esperaba «{e}» y se obtuvo «{o}». "
                    "Revisá la cantidad de decimales del printf (por ejemplo `%.2f`).")
        col = _primera_columna_distinta(e, o) + 1
        return (f"Línea {n}, columna {col}: se esperaba «{hacer_visible(e)}» y se obtuvo «{hacer_visible(o)}».")
    if len(obtenido) < len(esperado):
        faltan = len(esperado) - len(obtenido)
        return (f"Faltan {faltan} línea{'s' if faltan > 1 else ''} al final: la primera que falta es "
                f"«{hacer_visible(esperado[len(obtenido)])}» (línea {len(obtenido) + 1}).")
    if len(obtenido) > len(esperado):
        sobran = len(obtenido) - len(esperado)
        return (f"Sobra{'n' if sobran > 1 else ''} {sobran} línea{'s' if sobran > 1 else ''} al final: la primera es "
                f"«{hacer_visible(obtenido[len(esperado)])}» (línea {len(esperado) + 1}). "
                "¿Quedó un printf de depuración?")
    return "Las salidas coinciden."


def _solo_numeros_distintos(e: str, o: str) -> bool:
    a, b = e.split(), o.split()
    if len(a) != len(b):
        return False
    distintos = [(x, y) for x, y in zip(a, b) if x != y]
    return bool(distintos) and all(_NUMERO.match(x) and _NUMERO.match(y) for x, y in distintos)
