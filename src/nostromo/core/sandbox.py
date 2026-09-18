"""Aislamiento y sandboxing de procesos con Bubblewrap (bwrap) o RLIMIT."""

from __future__ import annotations

import os
import resource
import shutil
import subprocess
import tempfile
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


def _ejecutar_midiendo(cmd, stdin_texto, timeout_segundos, preexec):
    """Ejecuta `cmd` y devuelve (retorno, stdout, stderr, cpu_us, max_rss_kb, timeout).

    El uso de recursos sale de `os.wait4` sobre ESE hijo. Antes se leía
    `getrusage(RUSAGE_CHILDREN).ru_maxrss`, que es el máximo acumulado de todos
    los hijos esperados por el proceso: en una suite, un caso liviano heredaba el
    pico de uno anterior y aparecía con esa memoria (lo consumen la heurística
    de fuga y las columnas de RAM del reporte).

    Para poder llamar a `wait4` sin que `communicate()` compita por el mismo
    `waitpid`, la entrada y las salidas viajan por archivos temporales en lugar
    de pipes.
    """
    with tempfile.TemporaryFile() as fin, tempfile.TemporaryFile() as fout, tempfile.TemporaryFile() as ferr:
        fin.write((stdin_texto or "").encode("utf-8", errors="replace"))
        fin.seek(0)

        proc = subprocess.Popen(cmd, stdin=fin, stdout=fout, stderr=ferr, preexec_fn=preexec)
        limite = time.monotonic() + timeout_segundos
        expirado = False
        espera = 0.001

        while True:
            pid, estado, uso = os.wait4(proc.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() >= limite:
                proc.kill()
                pid, estado, uso = os.wait4(proc.pid, 0)
                expirado = True
                break
            time.sleep(espera)
            espera = min(espera * 2, 0.02)

        retorno = os.waitstatus_to_exitcode(estado)
        # `wait4` ya recogió al hijo: se fija el código para que Popen no intente
        # esperarlo de nuevo ni avise de un proceso "todavía corriendo".
        proc.returncode = retorno

        fout.seek(0)
        ferr.seek(0)
        stdout = fout.read().decode("utf-8", errors="replace")
        stderr = ferr.read().decode("utf-8", errors="replace")

    cpu_us = int((uso.ru_utime + uso.ru_stime) * 1_000_000)
    return retorno, stdout, stderr, cpu_us, uso.ru_maxrss, expirado


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

    try:
        ret, stdout, stderr, cpu_us, max_rss, expirado = _ejecutar_midiendo(
            cmd, stdin_texto, timeout_segundos, preexec
        )
        t_ms = (time.perf_counter() - t0) * 1000.0

        if expirado:
            return ResultadoEjecucion(
                124, "", "Tiempo límite de ejecución excedido (Timeout).", t_ms, "TIMEOUT", cpu_us, max_rss
            )

        err_tipo = clasificar_terminacion(ret, bajo_bwrap=bool(bwrap_bin))
        return ResultadoEjecucion(ret, stdout, stderr, t_ms, err_tipo, cpu_us, max_rss)

    except Exception as e:
        t_ms = (time.perf_counter() - t0) * 1000.0
        return ResultadoEjecucion(1, "", str(e), t_ms, "EXCEPTION", 0, 0)
