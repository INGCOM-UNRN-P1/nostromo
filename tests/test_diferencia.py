"""Diferencia pedagógica, tolerancia numérica y filtro de casos (QoL de nostromo #739, #740, #751)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nostromo.cli import app
from nostromo.core.diferencia import explicar_diferencia, hacer_visible, salidas_equivalentes
from nostromo.core.runner import descubrir_casos_prueba


def test_espacios_invisibles_se_hacen_visibles():
    msg = explicar_diferencia(["a b"], ["a  b"])
    assert "Línea 1" in msg and "espacios" in msg and "a··b" in msg
    assert hacer_visible("\tx\r") == "→x␍"


def test_primera_columna_distinta():
    msg = explicar_diferencia(["total: 10", "fin"], ["total: 10", "fon"])
    assert msg.startswith("Línea 2, columna 2")


def test_lineas_faltantes_y_sobrantes():
    assert "Faltan 2 líneas" in explicar_diferencia(["1", "2", "3"], ["1"])
    assert "Sobra 1 línea" in explicar_diferencia(["1"], ["1", "DEBUG x=3"])
    assert "DEBUG" in explicar_diferencia(["1"], ["1", "DEBUG x=3"])


def test_mayusculas_y_numeros():
    assert "mayúsculas" in explicar_diferencia(["Hola"], ["hola"])
    assert "%.2f" in explicar_diferencia(["3.50"], ["3.5"])


def test_tolerancia_numerica():
    assert not salidas_equivalentes(["pi = 3.1416"], ["pi = 3.1415"])
    assert salidas_equivalentes(["pi = 3.1416"], ["pi = 3.1415"], epsilon=0.001)
    assert not salidas_equivalentes(["pi = 3.1416"], ["PI = 3.1415"], epsilon=0.001)
    assert not salidas_equivalentes(["3.2"], ["3.1"], epsilon=0.01)


def _suite(tmp_path: Path) -> Path:
    d = tmp_path / "casos"
    d.mkdir()
    for nombre, tags in [("borde-vacio", "borde"), ("borde-uno", "borde, chico"), ("normal", "")]:
        (d / f"{nombre}.in").write_text("", encoding="utf-8")
        (d / f"{nombre}.out").write_text("ok\n", encoding="utf-8")
        if tags:
            (d / f"{nombre}.tags").write_text(tags, encoding="utf-8")
    return d


def test_filtrar_por_nombre_y_etiqueta(tmp_path):
    d = _suite(tmp_path)
    assert [c.nombre for c in descubrir_casos_prueba(d, nombres=["borde-*"])] == ["borde-uno", "borde-vacio"]
    assert [c.nombre for c in descubrir_casos_prueba(d, nombres=["normal"])] == ["normal"]
    assert [c.nombre for c in descubrir_casos_prueba(d, etiquetas=["chico"])] == ["borde-uno"]
    assert len(descubrir_casos_prueba(d)) == 3


@pytest.mark.skipif(shutil.which("gcc") is None, reason="requiere gcc")
def test_cli_explica_la_diferencia_y_filtra(tmp_path):
    fuente = tmp_path / "p.c"
    fuente.write_text('#include <stdio.h>\nint main(void){ printf("ok \\n3.1415\\n"); return 0; }\n', encoding="utf-8")
    binario = tmp_path / "p"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)], check=True)
    d = tmp_path / "casos"
    d.mkdir()
    (d / "pi.in").write_text("", encoding="utf-8")
    (d / "pi.out").write_text("ok\n3.1416\n", encoding="utf-8")
    (d / "otro.in").write_text("", encoding="utf-8")
    (d / "otro.out").write_text("nada\n", encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(app, ["test", str(binario), str(d), "--caso", "pi", "--json", "--no-hal"])
    datos = json.loads(res.stdout)
    assert res.exit_code == 1 and datos["total_casos"] == 1
    assert "Línea 2" in datos["resultados"][0]["explicacion_diferencia"]

    res = runner.invoke(app, ["test", str(binario), str(d), "--caso", "pi", "--float-epsilon", "0.001", "--json", "--no-hal"])
    assert res.exit_code == 0, res.stdout

    res = runner.invoke(app, ["test", str(binario), str(d), "--caso", "inexistente"])
    assert res.exit_code == 2
