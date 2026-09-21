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
