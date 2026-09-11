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
    """Normaliza saltos de línea y espacios finales para comparación uniforme."""
    lineas = [l.rstrip() for l in texto.replace("\r\n", "\n").splitlines()]
    while lineas and not lineas[-1]:
        lineas.pop()
    return "\n".join(lineas)


def generar_diff_lado_a_lado(esperado: str, obtenido: str) -> List[Tuple[str, str]]:
    """Genera lista de pares de líneas (esperado, obtenido) alineadas para vista en columnas."""
    lineas_exp = normalizar_salida(esperado).splitlines()
    lineas_obt = normalizar_salida(obtenido).splitlines()
    max_len = max(len(lineas_exp), len(lineas_obt))
    pares = []
    for i in range(max_len):
        exp = lineas_exp[i] if i < len(lineas_exp) else ""
        obt = lineas_obt[i] if i < len(lineas_obt) else ""
        pares.append((exp, obt))
    return pares


def calcular_timeout_adaptativo(tam_bytes: int, timeout_base: float = 2.0) -> float:
    """Escala el tiempo límite de ejecución de forma adaptativa según el tamaño de la entrada."""
    if tam_bytes <= 10_000:
        return timeout_base
    extra = ((tam_bytes - 10_000) / 50_000) * 0.5
    return min(timeout_base + extra, 20.0)


def diagnosticar_con_hal(binario: Path, stdin_texto: str) -> Optional[str]:
    """Invoca HAL ante fallos por señales para diagnosticar la causa raíz pedagógica."""
    try:
        from hal.core.inspector import inspeccionar_fuente_o_binario
        diag = inspeccionar_fuente_o_binario(ruta_objetivo=binario, stdin_data=stdin_texto)
        if diag and diag.es_crash:
            resumen = f"{diag.causa_raiz_titulo}"
            if diag.archivo_falla and diag.linea_falla:
                resumen += f" en {Path(diag.archivo_falla).name}:{diag.linea_falla}"
            return resumen
    except Exception:
        pass
    return None


def evaluar_binario(
    binario: Path,
    casos: List[CasoPrueba],
    timeout_segundos: float = 2.0,
    memoria_mb: int = 128,
    timeout_adaptativo: bool = False,
    integrar_hal: bool = True,
) -> ReporteEvaluacion:
    """Ejecuta una suite de casos de prueba contra el binario."""
    resultados: List[ResultadoCaso] = []
    tiempo_total = 0.0
    cpu_tiempo_total = 0
    max_rss_pico = 0

    for c in casos:
        t_limit = c.timeout_segundos or timeout_segundos
        if timeout_adaptativo or c.timeout_adaptativo:
            t_limit = calcular_timeout_adaptativo(len(c.stdin_texto.encode("utf-8")), t_limit)

        res_ejec = ejecutar_aislado(
            binario=binario,
            stdin_texto=c.stdin_texto,
            timeout_segundos=t_limit,
            memoria_mb=c.memoria_mb or memoria_mb,
        )
        ret, stdout, stderr, t_ms, err_tipo = res_ejec
        cpu_us = getattr(res_ejec, "cpu_tiempo_us", 0)
        rss_kb = getattr(res_ejec, "max_rss_kb", 0)

        tiempo_total += t_ms
        cpu_tiempo_total += cpu_us
        if rss_kb > max_rss_pico:
            max_rss_pico = rss_kb

        out_norm = normalizar_salida(stdout)
        exp_norm = normalizar_salida(c.stdout_esperado)

        # Chequear coincidencia
        paso = (ret == 0) and (out_norm == exp_norm)
        diff_lines = []
        diff_side = []
        if not paso and not err_tipo:
            err_tipo = "DIFF"
            diff_lines = list(difflib.unified_diff(
                exp_norm.splitlines(keepends=True),
                out_norm.splitlines(keepends=True),
                fromfile="esperado",
                tofile="obtenido",
            ))
            diff_side = generar_diff_lado_a_lado(c.stdout_esperado, stdout)

        hal_diag = None
        if not paso and err_tipo in ("SEGFAULT", "ABORT", "FPE") and integrar_hal:
            hal_diag = diagnosticar_con_hal(binario, c.stdin_texto)

        # Detección heurística de posible fuga (ej: RSS excesivo relativo a un caso pequeño)
        posible_fuga = rss_kb > (memoria_mb * 1024 * 0.9)

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
            diff_lado_a_lado=diff_side,
            cpu_tiempo_us=cpu_us,
            max_rss_kb=rss_kb,
            posible_leak=posible_fuga,
            hal_diagnostico=hal_diag,
        ))

    aprobados = sum(1 for r in resultados if r.paso)
    fallidos = len(resultados) - aprobados

    return ReporteEvaluacion(
        binario=binario,
        total_casos=len(casos),
        casos_aprobados=aprobados,
        casos_fallidos=fallidos,
        tiempo_total_ms=tiempo_total,
        cpu_tiempo_total_us=cpu_tiempo_total,
        max_rss_pico_kb=max_rss_pico,
        resultados=resultados,
    )
