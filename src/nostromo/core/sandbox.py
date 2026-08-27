"""Aislamiento y sandboxing de procesos con Bubblewrap (bwrap) o RLIMIT."""

from __future__ import annotations

import os
import resource
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple


def _configurar_limites(memoria_mb: int):
    """Configura límites de memoria del proceso hijo vía setrlimit (POSIX)."""
    def preexec_fn():
        bytes_max = memoria_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (bytes_max, bytes_max))
        except (ValueError, resource.error):
            pass
        # Prevenir generación de core dumps gigantes en tests
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, resource.error):
            pass
    return preexec_fn


def ejecutar_aislado(
    binario: Path,
    args: Optional[List[str]] = None,
    stdin_texto: str = "",
    timeout_segundos: float = 2.0,
    memoria_mb: int = 128,
    usar_bwrap: bool = True,
) -> Tuple[int, str, str, float, Optional[str]]:
    """Ejecuta un binario de forma aislada retornando (exit_code, stdout, stderr, tiempo_ms, error_tipo)."""
    binario = Path(binario).resolve()
    if not binario.is_file():
        return 1, "", f"El binario no existe: {binario}", 0.0, "FILE_NOT_FOUND"

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
        res = subprocess.run(
            cmd,
            input=stdin_texto,
            capture_output=True,
            text=True,
            timeout=timeout_segundos,
            preexec_fn=preexec,
        )
        t_ms = (time.perf_counter() - t0) * 1000.0
        ret = res.returncode
        err_tipo = None
        if ret < 0:
            sig = -ret
            err_tipo = "SEGFAULT" if sig == 11 else "ABORT" if sig == 6 else "FPE" if sig == 8 else f"SIGNAL_{sig}"
        elif ret != 0:
            err_tipo = "NON_ZERO"

        return ret, res.stdout, res.stderr, t_ms, err_tipo

    except subprocess.TimeoutExpired:
        t_ms = (time.perf_counter() - t0) * 1000.0
        return 124, "", "Tiempo límite de ejecución excedido (Timeout).", t_ms, "TIMEOUT"
    except Exception as e:
        t_ms = (time.perf_counter() - t0) * 1000.0
        return 1, "", str(e), t_ms, "EXCEPTION"
