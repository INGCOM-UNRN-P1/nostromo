"""Regresión de NOSTROMO-D0601/D0602: JSON versionado y claves bilingües coherentes."""

import subprocess

import pytest

from nostromo.core.models import SCHEMA_VERSION
from nostromo.core.runner import descubrir_casos_prueba, evaluar_binario
from nostromo.ripley_plugin import NostromoPlugin


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "eco.c").write_text(
        '#include <stdio.h>\nint main(void){int x; if(scanf("%d",&x)==1) printf("%d\\n",x); return 0;}\n')
    subprocess.run(["gcc", str(tmp_path / "eco.c"), "-o", str(tmp_path / "eco")], check=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "caso_1.in").write_text("7\n")
    (tmp_path / "tests" / "caso_1.out").write_text("7\n")
    (tmp_path / "tests" / "caso_2.in").write_text("8\n")
    (tmp_path / "tests" / "caso_2.out").write_text("9\n")
    return tmp_path


def test_el_reporte_lleva_schema_version(workspace):
    rep = evaluar_binario(workspace / "eco", descubrir_casos_prueba(workspace / "tests"))
    assert rep.to_dict()["schema_version"] == SCHEMA_VERSION


def test_el_plugin_lleva_schema_version_y_alias_coherentes(workspace):
    res = NostromoPlugin().execute(workspace, {"binary_path": str(workspace / "eco")})
    assert res["schema_version"] == SCHEMA_VERSION
    assert (res["total"], res["passed"], res["failed"]) == (2, 1, 1)
    assert res["total"] == res["total_casos"]
    assert res["passed"] == res["aprobados"]
    assert res["failed"] == res["fallidos"]
    assert res["cases"] == res["casos"]


def test_el_plugin_sin_casos_tambien_versiona(tmp_path):
    binario = tmp_path / "x"
    binario.write_text("")
    res = NostromoPlugin().execute(tmp_path, {"binary_path": str(binario)})
    assert res["schema_version"] == SCHEMA_VERSION
