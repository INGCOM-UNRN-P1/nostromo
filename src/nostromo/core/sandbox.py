"""Aislamiento y sandboxing de procesos con Bubblewrap (bwrap) o RLIMIT."""

from __future__ import annotations

import os
import resource
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple


class ResultadoEjecucion(tuple):
    """Tupla compatible hacia atrás con atributos extendidos de uso de CPU y memoria."""
    codigo_retorno: int
    stdout: str
    stderr: str
    tiempo_ms: float
    error_tipo: Optional[str]
    cpu_tiempo_us: int
    max_rss_kb: int

    def __new__(
        cls,
        codigo_retorno: int,
        stdout: str,
        stderr: str,
        tiempo_ms: float,
        error_tipo: Optional[str],
        cpu_tiempo_us: int = 0,
        max_rss_kb: int = 0,
    ):
        instance = super().__new__(cls, (codigo_retorno, stdout, stderr, tiempo_ms, error_tipo))
        instance.codigo_retorno = codigo_retorno
        instance.stdout = stdout
        instance.stderr = stderr
        instance.tiempo_ms = tiempo_ms
        instance.error_tipo = error_tipo
        instance.cpu_tiempo_us = cpu_tiempo_us
        instance.max_rss_kb = max_rss_kb
        return instance


def _configurar_limites(memoria_mb: int):
    """Configura límites de memoria virtual y de datos del proceso hijo vía setrlimit (POSIX)."""
    def preexec_fn():
        bytes_max = memoria_mb * 1024 * 1024
        try:
            # Límite estricto de memoria virtual (ulimit -v)
            resource.setrlimit(resource.RLIMIT_AS, (bytes_max, bytes_max))
        except (ValueError, resource.error):
            pass
        try:
            # Límite de segmento de datos (heap)
            resource.setrlimit(resource.RLIMIT_DATA, (bytes_max, bytes_max))
        except (ValueError, resource.error):
            pass
        # Desactivar generación de core dumps gigantes en tests
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, resource.error):
            pass
    return preexec_fn


# Nombres de las señales que interesan pedagógicamente; el resto se reporta
# como SIGNAL_<n>.
_SENALES = {11: "SEGFAULT", 6: "ABORT", 8: "FPE"}


def clasificar_terminacion(codigo_retorno: int, bajo_bwrap: bool) -> Optional[str]:
    """Traduce el código de retorno al tipo de error.

    En ejecución directa Python informa la señal como retorno negativo, pero
    bajo bwrap —el modo por defecto y recomendado— llega como 128+señal. Sin
    contemplar ese caso, un SIGSEGV se clasificaba NON_ZERO y el disparador de
    HAL, que exige SEGFAULT/ABORT/FPE, quedaba inalcanzable en la
    configuración por defecto.

    La forma 128+señal solo se interpreta bajo bwrap: en ejecución directa un
    `exit(139)` legítimo debe seguir siendo NON_ZERO.
    """
    if codigo_retorno == 0:
        return None
    senal = None
    if codigo_retorno < 0:
        senal = -codigo_retorno
    elif bajo_bwrap and 128 < codigo_retorno < 160:
        senal = codigo_retorno - 128
    if senal is not None:
        return _SENALES.get(senal, f"SIGNAL_{senal}")
    return "NON_ZERO"


def ejecutar_aislado(
    binario: Path,
    args: Optional[List[str]] = None,
    stdin_texto: str = "",
    timeout_segundos: float = 2.0,
    memoria_mb: int = 128,
    usar_bwrap: bool = True,
) -> ResultadoEjecucion:
    """Ejecuta un binario de forma aislada retornando ResultadoEjecucion."""
    binario = Path(binario).resolve()
    if not binario.is_file():
        return ResultadoEjecucion(1, "", f"El binario no existe: {binario}", 0.0, "FILE_NOT_FOUND", 0, 0)

    bwrap_bin = shutil.which("bwrap") if usar_bwrap else None
    t0 = time.perf_counter()

    if bwrap_bin:
        cmd = [
            bwrap_bin,
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64" if os.path.exists("/lib64") else "/lib",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", str(binario.parent), str(binario.parent),
            "--proc", "/proc",
            "--dev", "/dev",
            "--unshare-all",
            "--die-with-parent",
            str(binario),
        ] + (args or [])
    else:
        cmd = [str(binario)] + (args or [])

    preexec = _configurar_limites(memoria_mb)
    ru_before = resource.getrusage(resource.RUSAGE_CHILDREN)

    try:
        res = subprocess.run(
            cmd,
            input=stdin_texto,
            capture_output=True,
            text=True,
            timeout=timeout_segundos,
            preexec_fn=preexec,
        )
        t_ms = (time.perf_counter() - t0) * 1000.0
        ru_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu_us = int(((ru_after.ru_utime - ru_before.ru_utime) + (ru_after.ru_stime - ru_before.ru_stime)) * 1_000_000)
        max_rss = ru_after.ru_maxrss

        ret = res.returncode
        err_tipo = clasificar_terminacion(ret, bajo_bwrap=bool(bwrap_bin))

        return ResultadoEjecucion(ret, res.stdout, res.stderr, t_ms, err_tipo, cpu_us, max_rss)

    except subprocess.TimeoutExpired:
        t_ms = (time.perf_counter() - t0) * 1000.0
        ru_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu_us = int(((ru_after.ru_utime - ru_before.ru_utime) + (ru_after.ru_stime - ru_before.ru_stime)) * 1_000_000)
        return ResultadoEjecucion(124, "", "Tiempo límite de ejecución excedido (Timeout).", t_ms, "TIMEOUT", cpu_us, ru_after.ru_maxrss)
    except Exception as e:
        t_ms = (time.perf_counter() - t0) * 1000.0
        return ResultadoEjecucion(1, "", str(e), t_ms, "EXCEPTION", 0, 0)
