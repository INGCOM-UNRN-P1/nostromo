"""Aislamiento y sandboxing de procesos con Bubblewrap (bwrap) o RLIMIT."""

from __future__ import annotations

import math
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
    uso_medido: bool

    def __new__(
        cls,
        codigo_retorno: int,
        stdout: str,
        stderr: str,
        tiempo_ms: float,
        error_tipo: Optional[str],
        cpu_tiempo_us: int = 0,
        max_rss_kb: int = 0,
        uso_medido: bool = True,
    ):
        instance = super().__new__(cls, (codigo_retorno, stdout, stderr, tiempo_ms, error_tipo))
        instance.codigo_retorno = codigo_retorno
        instance.stdout = stdout
        instance.stderr = stderr
        instance.tiempo_ms = tiempo_ms
        instance.error_tipo = error_tipo
        instance.cpu_tiempo_us = cpu_tiempo_us
        instance.max_rss_kb = max_rss_kb
        instance.uso_medido = uso_medido
        return instance


def _configurar_limites(memoria_mb: int, cpu_segundos: int, archivo_mb: int, limitar_memoria: bool = True):
    """Configura límites del proceso hijo vía setrlimit (POSIX).

    - memoria virtual y segmento de datos (`limitar_memoria`; con el lanzador de
      medición los aplica él mismo al programa, no a sí mismo);
    - tiempo de CPU: a diferencia del timeout de pared, corta un programa con
      varios hilos que gasta N segundos de CPU por segundo de reloj;
    - tamaño de cada archivo escrito (incluida la salida estándar): un bucle
      que imprime sin parar llenaba el disco hasta el timeout.
    """
    def preexec_fn():
        bytes_max = memoria_mb * 1024 * 1024
        limites = [
            (resource.RLIMIT_CPU, (cpu_segundos, cpu_segundos + 1)),  # SIGXCPU y luego SIGKILL
            (resource.RLIMIT_FSIZE, (archivo_mb * 1024 * 1024, archivo_mb * 1024 * 1024)),
            (resource.RLIMIT_CORE, (0, 0)),  # sin core dumps gigantes en tests
        ]
        if limitar_memoria:
            limites += [
                (resource.RLIMIT_AS, (bytes_max, bytes_max)),    # memoria virtual (ulimit -v)
                (resource.RLIMIT_DATA, (bytes_max, bytes_max)),  # segmento de datos (heap)
            ]
        for recurso, valores in limites:
            try:
                resource.setrlimit(recurso, valores)
            except (ValueError, resource.error):
                pass
    return preexec_fn


_MEDIDOR = Path(__file__).with_name("_medidor.py")
_PYTHON_DEL_SISTEMA = ("/usr/bin/python3", "/bin/python3", "/usr/local/bin/python3")


def _python_del_sistema() -> Optional[str]:
    """Intérprete visible dentro del sandbox (que solo monta /usr, /lib y /bin)."""
    for candidato in _PYTHON_DEL_SISTEMA:
        if os.path.exists(candidato):
            return candidato
    return None


def _leer_medicion(archivo: Path) -> Optional[Tuple[int, int]]:
    try:
        utime, stime, maxrss = archivo.read_text().split()
        return int((float(utime) + float(stime)) * 1_000_000), int(maxrss)
    except (OSError, ValueError):
        return None


# Nombres de las señales que interesan pedagógicamente; el resto se reporta
# como SIGNAL_<n>.
_SENALES = {11: "SEGFAULT", 6: "ABORT", 8: "FPE", 24: "CPU_LIMIT", 25: "FILE_SIZE_LIMIT"}


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
    archivo_mb: int = 16,
) -> ResultadoEjecucion:
    """Ejecuta un binario de forma aislada retornando ResultadoEjecucion.

    Límites: memoria (`memoria_mb`), tiempo de pared (`timeout_segundos`), tiempo
    de CPU (el timeout redondeado hacia arriba más un segundo) y tamaño de cada
    archivo escrito (`archivo_mb`, incluida la salida estándar).
    """
    binario = Path(binario).resolve()
    if not binario.is_file():
        return ResultadoEjecucion(1, "", f"El binario no existe: {binario}", 0.0, "FILE_NOT_FOUND", 0, 0)

    bwrap_bin = shutil.which("bwrap") if usar_bwrap else None
    python_sandbox = _python_del_sistema() if bwrap_bin else None
    medicion: Optional[Path] = None
    directorio_medicion: Optional[str] = None
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
        ]
        if python_sandbox:
            directorio_medicion = tempfile.mkdtemp(prefix="nostromo-uso-")
            medicion = Path(directorio_medicion) / "uso"
            cmd += [
                "--bind", directorio_medicion, directorio_medicion,
                "--ro-bind", str(_MEDIDOR), str(_MEDIDOR),
                python_sandbox, "-S", "-E", str(_MEDIDOR),
                str(medicion), str(memoria_mb * 1024 * 1024), str(binario),
            ] + (args or [])
        else:
            cmd += [str(binario)] + (args or [])
    else:
        cmd = [str(binario)] + (args or [])

    preexec = _configurar_limites(
        memoria_mb,
        cpu_segundos=max(1, math.ceil(timeout_segundos)) + 1,
        archivo_mb=archivo_mb,
        limitar_memoria=python_sandbox is None,
    )

    try:
        ret, stdout, stderr, cpu_us, max_rss, expirado = _ejecutar_midiendo(
            cmd, stdin_texto, timeout_segundos, preexec
        )
        t_ms = (time.perf_counter() - t0) * 1000.0

        # Bajo bwrap el `rusage` que devuelve wait4 es el del lanzador, no el del
        # programa. Si hay lanzador de medición se usa su registro; si no, el
        # consumo queda como no medido en vez de mostrar el del sandbox.
        uso_medido = True
        if bwrap_bin:
            leido = _leer_medicion(medicion) if medicion else None
            if leido is not None:
                cpu_us, max_rss = leido
            else:
                cpu_us, max_rss, uso_medido = 0, 0, False

        if expirado:
            return ResultadoEjecucion(
                124, "", "Tiempo límite de ejecución excedido (Timeout).", t_ms, "TIMEOUT", cpu_us, max_rss, uso_medido
            )

        err_tipo = clasificar_terminacion(ret, bajo_bwrap=bool(bwrap_bin))
        return ResultadoEjecucion(ret, stdout, stderr, t_ms, err_tipo, cpu_us, max_rss, uso_medido)

    except Exception as e:
        t_ms = (time.perf_counter() - t0) * 1000.0
        return ResultadoEjecucion(1, "", str(e), t_ms, "EXCEPTION", 0, 0, False)
    finally:
        if directorio_medicion:
            shutil.rmtree(directorio_medicion, ignore_errors=True)
