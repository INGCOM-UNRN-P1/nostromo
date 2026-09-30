"""nostromo en Windows (N-ECO-10): sin `resource` ni `os.wait4`, sin bwrap.

`import resource` sin protección hacía que nostromo no arrancara en Windows, y el camino de
ejecución usaba `os.wait4`: cada programa se informaba como una falla. Se simula quitándolos.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nostromo.core import sandbox


def test_nostromo_importa_sin_resource():
    programa = "import sys\nsys.modules['resource'] = None\nimport nostromo.cli, nostromo.core.runner\n"
    proc = subprocess.run([sys.executable, "-c", programa], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr


@pytest.fixture
def como_windows(monkeypatch):
    monkeypatch.setattr(sandbox, "resource", None)
    monkeypatch.delattr(os, "wait4")


@pytest.mark.skipif(not (shutil.which("cat") and shutil.which("sleep")), reason="requiere cat y sleep")
def test_ejecuta_sin_wait4_ni_limites(como_windows):
    res = sandbox.ejecutar_aislado(Path(shutil.which("cat")), stdin_texto="hola\n", usar_bwrap=False)
    assert res.codigo_retorno == 0 and res.stdout == "hola\n"
    assert res.uso_medido is False  # sin wait4 el consumo no se mide

    res = sandbox.ejecutar_aislado(Path(shutil.which("sleep")), args=["5"], timeout_segundos=0.3, usar_bwrap=False)
    assert res.codigo_retorno == 124 and res.error_tipo == "TIMEOUT"


def test_sin_resource_no_hay_preexec_fn(monkeypatch):
    monkeypatch.setattr(sandbox, "resource", None)
    assert sandbox._configurar_limites(64, 2, 16, limitar_memoria=True) is None


@pytest.mark.parametrize("codigo, tipo", [
    (0xC0000005, "SEGFAULT"),  # acceso inválido
    (0xC00000FD, "SEGFAULT"),  # desborde de pila
    (0xC0000409, "ABORT"),     # abort() del UCRT
    (0xC0000094, "FPE"),       # división entera por cero
    (3, "NON_ZERO"),           # un exit(3) legítimo sigue siendo NON_ZERO
])
def test_crashes_de_windows(codigo, tipo):
    assert sandbox.clasificar_terminacion(codigo, bajo_bwrap=False) == tipo
