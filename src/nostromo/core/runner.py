"""Evaluador de suites de casos de prueba .in/.out en NOSTROMO."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import List, Optional

from nostromo.core.models import CasoPrueba, ReporteEvaluacion, ResultadoCaso
from nostromo.core.sandbox import ejecutar_aislado


def descubrir_casos_prueba(directorio: Path) -> List[CasoPrueba]:
    """Descubre parejas de archivos .in y .out en un directorio."""
    directorio = Path(directorio)
    if not directorio.is_dir():
        return []

    casos_dict = {}
    for p in sorted(directorio.glob("*")):
        if p.suffix == ".in":
            casos_dict.setdefault(p.stem, {})["in"] = p
        elif p.suffix == ".out":
            casos_dict.setdefault(p.stem, {})["out"] = p

    casos = []
    for stem, files in sorted(casos_dict.items()):
        f_in = files.get("in")
        f_out = files.get("out")

        stdin_txt = f_in.read_text(encoding="utf-8") if f_in else ""
        stdout_exp = f_out.read_text(encoding="utf-8") if f_out else ""

        casos.append(CasoPrueba(
            nombre=stem,
            archivo_in=f_in,
            archivo_out=f_out,
            stdin_texto=stdin_txt,
            stdout_esperado=stdout_exp,
        ))

    return casos


def normalizar_salida(texto: str) -> str:
    """Normaliza saltos de línea y trailing whitespaces para comparación robusta."""
    lineas = [l.rstrip() for l in texto.replace("\r\n", "\n").splitlines()]
    # Eliminar líneas vacías al final
    while lineas and not lineas[-1]:
        lineas.pop()
    return "\n".join(lineas)


def evaluar_binario(
    binario: Path,
    casos: List[CasoPrueba],
    timeout_segundos: float = 2.0,
    memoria_mb: int = 128,
) -> ReporteEvaluacion:
    """Ejecuta una suite de casos de prueba contra el binario."""
    resultados: List[ResultadoCaso] = []
    tiempo_total = 0.0

    for c in casos:
        ret, stdout, stderr, t_ms, err_tipo = ejecutar_aislado(
            binario=binario,
            stdin_texto=c.stdin_texto,
            timeout_segundos=c.timeout_segundos or timeout_segundos,
            memoria_mb=c.memoria_mb or memoria_mb,
        )
        tiempo_total += t_ms

        out_norm = normalizar_salida(stdout)
        exp_norm = normalizar_salida(c.stdout_esperado)

        # Chequear coincidencia
        paso = (ret == 0) and (out_norm == exp_norm)
        diff_lines = []
        if not paso and not err_tipo:
            err_tipo = "DIFF"
            diff_lines = list(difflib.unified_diff(
                exp_norm.splitlines(keepends=True),
                out_norm.splitlines(keepends=True),
                fromfile="esperado",
                tofile="obtenido",
            ))

        resultados.append(ResultadoCaso(
            nombre=c.nombre,
            paso=paso,
            codigo_retorno=ret,
            tiempo_ms=t_ms,
            stdout_obtenido=stdout,
            stderr_obtenido=stderr,
            stdout_esperado=c.stdout_esperado,
            error_tipo=err_tipo if not paso else None,
            diff_lineas=diff_lines,
        ))

    aprobados = sum(1 for r in resultados if r.paso)
    fallidos = len(resultados) - aprobados

    return ReporteEvaluacion(
        binario=binario,
        total_casos=len(casos),
        casos_aprobados=aprobados,
        casos_fallidos=fallidos,
        tiempo_total_ms=tiempo_total,
        resultados=resultados,
    )
