"""Regresión de NOSTROMO-D0401: `run` propagaba el código del programa evaluado.

Un script consumidor no podía distinguir un fallo de nostromo de un retorno
arbitrario (139, 245 para señales). El contrato es 0/1/2.
"""

import subprocess

import pytest
from typer.testing import CliRunner

from nostromo.cli import _codigo_de_salida, app

runner = CliRunner()


def _compilar(tmp_path, nombre, codigo):
    fuente = tmp_path / f"{nombre}.c"
    fuente.write_text(codigo, encoding="utf-8")
    binario = tmp_path / nombre
    subprocess.run(["gcc", str(fuente), "-o", str(binario)], check=True)
    return binario


@pytest.mark.parametrize(
    "codigo, esperado",
    [
        ("int main(void){return 0;}", 0),
        ("int main(void){return 3;}", 1),
        ("int main(void){return 139;}", 1),
        ("int main(void){int *p=0; return *p;}", 1),
    ],
)
def test_el_codigo_de_salida_es_0_o_1_segun_el_programa(tmp_path, codigo, esperado):
    binario = _compilar(tmp_path, "p", codigo)
    assert runner.invoke(app, ["run", str(binario)]).exit_code == esperado
    assert runner.invoke(app, ["run", str(binario), "--json"]).exit_code == esperado


def test_el_codigo_del_programa_sigue_disponible_en_el_json(tmp_path):
    import json

    binario = _compilar(tmp_path, "p", "int main(void){return 3;}")
    res = runner.invoke(app, ["run", str(binario), "--json"])
    assert res.exit_code == 1
    assert json.loads(res.stdout)["codigo_retorno"] == 3


def test_un_binario_inexistente_es_error_de_uso(tmp_path):
    assert runner.invoke(app, ["run", str(tmp_path / "no_existe")]).exit_code == 2


def test_exit_code_conserva_el_retorno_del_programa(tmp_path):
    binario = _compilar(tmp_path, "p", "int main(void){return 3;}")
    assert runner.invoke(app, ["run", str(binario), "--exit-code"]).exit_code == 3


@pytest.mark.parametrize(
    "ret, err_tipo, propagar, esperado",
    [
        (0, None, False, 0),
        (5, "NON_ZERO", False, 1),
        (-11, "SEGFAULT", False, 1),
        (139, "SEGFAULT", False, 1),
        (124, "TIMEOUT", False, 1),
        (1, "FILE_NOT_FOUND", False, 2),
        (1, "EXCEPTION", True, 2),
        (-11, "SEGFAULT", True, 139),
        (139, "SEGFAULT", True, 139),
        (5, "NON_ZERO", True, 5),
        (0, None, True, 0),
    ],
)
def test_tabla_de_codigos(ret, err_tipo, propagar, esperado):
    assert _codigo_de_salida(ret, err_tipo, propagar) == esperado
