"""Regresión de NOSTROMO-D0402: `doctor` debe fallar (exit 1) si el aislamiento no está operativo."""

import json

from typer.testing import CliRunner

from nostromo import cli

runner = CliRunner()


def test_sin_bwrap_el_doctor_sale_1(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    res = runner.invoke(cli.app, ["doctor", "--json"])
    assert res.exit_code == 1
    datos = json.loads(res.output)
    assert datos["ok"] is False
    assert datos["componentes"][0]["estado"] == "ERROR"


def test_con_bwrap_operativo_el_doctor_sale_0(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setattr(cli, "_bwrap_funciona", lambda _: True)
    res = runner.invoke(cli.app, ["doctor"])
    assert res.exit_code == 0


def test_bwrap_presente_pero_que_no_arranca_es_error(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setattr(cli, "_bwrap_funciona", lambda _: False)
    res = runner.invoke(cli.app, ["doctor", "--json"])
    assert res.exit_code == 1
    assert "no arranca" in json.loads(res.output)["componentes"][0]["detalle"]


def _bwrap_sin_user_namespaces(carpeta, monkeypatch):
    """Un bwrap instalado que aborta como en Ubuntu ≥ 23.10 con AppArmor."""
    import os

    from nostromo.core import sandbox

    falso = carpeta / "bwrap"
    falso.write_text("#!/bin/sh\necho 'bwrap: setting up uid map: Permission denied' >&2\nexit 1\n")
    falso.chmod(0o755)
    monkeypatch.setenv("PATH", f"{carpeta}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(sandbox, "_BWRAP_FLAGS_CACHE", None)
    monkeypatch.setattr(sandbox, "_BWRAP_ARRANCA", {})
    return str(falso)


def test_bwrap_funciona_detecta_el_que_no_arranca(tmp_path, monkeypatch):
    from nostromo.core.sandbox import bwrap_funciona

    assert bwrap_funciona(_bwrap_sin_user_namespaces(tmp_path, monkeypatch)) is False


def test_con_un_bwrap_que_no_arranca_se_ejecuta_sin_el(tmp_path, monkeypatch):
    # Antes devolvía 1 con el error de bwrap, como si fuera la salida del programa.
    import shutil
    from pathlib import Path

    from nostromo.core.sandbox import ejecutar_aislado

    _bwrap_sin_user_namespaces(tmp_path, monkeypatch)
    res = ejecutar_aislado(Path(shutil.which("true")))
    assert res.codigo_retorno == 0
    assert "bwrap" not in res.stderr


def test_en_windows_bwrap_es_un_aviso_y_no_un_error(monkeypatch):
    # bwrap no existe en Windows: instalarlo es imposible y nostromo igual corre (N-ECO-10).
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    monkeypatch.setattr(cli, "_es_windows", lambda: True)
    res = runner.invoke(cli.app, ["doctor", "--json"])
    datos = json.loads(res.output)
    assert res.exit_code == 0 and datos["ok"] is True
    bwrap = datos["componentes"][0]
    assert bwrap["estado"] == "ADVERTENCIA" and bwrap["requerido"] is False and "WSL" in bwrap["detalle"]
