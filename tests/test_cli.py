"""Tests de integración de la CLI de NOSTROMO."""

import json
import subprocess
from pathlib import Path
from typer.testing import CliRunner
from nostromo.cli import app

runner = CliRunner()


def test_cli_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "NOSTROMO" in res.stdout


def test_cli_doctor():
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "Bubblewrap" in res.stdout


def test_cli_run_directo(tmp_path):
    fuente = tmp_path / "hola.c"
    fuente.write_text('#include <stdio.h>\nint main(void) { printf("Hola Mundo\\n"); return 0; }\n')
    binario = tmp_path / "hola"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)], check=True)

    res = runner.invoke(app, ["run", str(binario)])
    assert res.exit_code == 0
    assert "Hola Mundo" in res.stdout


def test_cli_test_suite_json(tmp_path):
    fuente = tmp_path / "calc.c"
    fuente.write_text('#include <stdio.h>\nint main(void) { int x; if (scanf("%d", &x) == 1) printf("%d\\n", x*2); return 0; }\n')
    binario = tmp_path / "calc"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)], check=True)

    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "01.in").write_text("10\n")
    (test_dir / "01.out").write_text("20\n")

    res = runner.invoke(app, ["test", str(binario), str(test_dir), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["ok"] is True
    assert data["total_casos"] == 1
    assert data["casos_aprobados"] == 1
