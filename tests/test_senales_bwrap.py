"""Regresión de NOSTROMO-D0301/D0901: señales bajo bwrap y delegación a HAL."""

import shutil
import subprocess
from pathlib import Path

import pytest

from nostromo.core.runner import (
    descubrir_casos_prueba,
    diagnosticar_con_hal,
    evaluar_binario,
)
from nostromo.core.sandbox import clasificar_terminacion, ejecutar_aislado

CRASH = "int main(void) { int *p = 0; *p = 1; return 0; }\n"


@pytest.fixture
def binario_que_revienta(tmp_path):
    fuente = tmp_path / "crash.c"
    fuente.write_text(CRASH, encoding="utf-8")
    binario = tmp_path / "crash"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)], check=True)
    return binario


def test_senal_negativa_en_ejecucion_directa():
    assert clasificar_terminacion(-11, bajo_bwrap=False) == "SEGFAULT"
    assert clasificar_terminacion(-6, bajo_bwrap=False) == "ABORT"
    assert clasificar_terminacion(-8, bajo_bwrap=False) == "FPE"


def test_senal_como_128_mas_n_bajo_bwrap():
    """NOSTROMO-D0301: bajo bwrap la señal llega como 128+n, no como negativo."""
    assert clasificar_terminacion(139, bajo_bwrap=True) == "SEGFAULT"
    assert clasificar_terminacion(134, bajo_bwrap=True) == "ABORT"
    assert clasificar_terminacion(136, bajo_bwrap=True) == "FPE"


def test_exit_139_legitimo_sin_bwrap_no_es_senal():
    """En ejecución directa, `exit(139)` es un código de salida, no un SIGSEGV."""
    assert clasificar_terminacion(139, bajo_bwrap=False) == "NON_ZERO"


def test_salida_exitosa_no_tiene_tipo_de_error():
    assert clasificar_terminacion(0, bajo_bwrap=True) is None


@pytest.mark.skipif(not shutil.which("gcc"), reason="requiere gcc")
@pytest.mark.parametrize("usar_bwrap", [True, False])
def test_segfault_se_clasifica_igual_con_y_sin_sandbox(binario_que_revienta, usar_bwrap):
    resultado = ejecutar_aislado(binario_que_revienta, usar_bwrap=usar_bwrap)
    assert resultado.error_tipo == "SEGFAULT"


@pytest.mark.skipif(
    not (shutil.which("gcc") and shutil.which("hal")), reason="requiere gcc y hal"
)
def test_hal_se_alcanza_en_la_configuracion_por_defecto(binario_que_revienta, tmp_path):
    """NOSTROMO-D0901: la integración con HAL estaba declarada pero nunca ocurría."""
    casos_dir = tmp_path / "tests"
    casos_dir.mkdir()
    (casos_dir / "caso1.in").write_text("", encoding="utf-8")
    (casos_dir / "caso1.out").write_text("x\n", encoding="utf-8")

    reporte = evaluar_binario(binario_que_revienta, descubrir_casos_prueba(casos_dir))
    resultado = reporte.resultados[0]
    assert resultado.error_tipo == "SEGFAULT"
    assert resultado.hal_diagnostico, "HAL no produjo diagnóstico pese al SEGFAULT"


@pytest.mark.skipif(not shutil.which("gcc"), reason="requiere gcc")
def test_sin_hal_disponible_no_revienta(binario_que_revienta, monkeypatch):
    monkeypatch.setattr("nostromo.core.runner.shutil.which", lambda _: None)
    assert diagnosticar_con_hal(binario_que_revienta, "") is None
