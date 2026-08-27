"""Tests adicionales para maximizar la cobertura en NOSTROMO."""

import json
from pathlib import Path
from typer.testing import CliRunner
import subprocess
import nostromo.cli
from nostromo.cli import app
from nostromo.core.runner import CasoPrueba, evaluar_binario, descubrir_casos_prueba
from nostromo.core.sandbox import ejecutar_aislado
from nostromo.ripley_plugin import NostromoPlugin

runner = CliRunner()


def test_plugin_execution_completo(tmp_path):
    p = NostromoPlugin()
    assert p.is_available() is True

    # No binary
    res_no_bin = p.execute(tmp_path, {})
    assert res_no_bin["ok"] is False

    # Binary with testcases
    fuente = tmp_path / "prog.c"
    fuente.write_text("""
    #include <stdio.h>
    int main(void) {
        int x;
        if (scanf("%d", &x) == 1) printf("RES: %d\\n", x * 2);
        return 0;
    }
    """)
    binario = tmp_path / "prog"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)])

    tc_dir = tmp_path / "testcases"
    tc_dir.mkdir()
    (tc_dir / "01.in").write_text("5\n")
    (tc_dir / "01.out").write_text("RES: 10\n")

    res_ok = p.execute(tmp_path, {})
    assert res_ok["ok"] is True
    assert res_ok["aprobados"] == 1


def test_cli_run_rich_output_and_signals(tmp_path):
    fuente = tmp_path / "echo.c"
    fuente.write_text('#include <stdio.h>\nint main(void) { printf("HOLA\\n"); return 0; }\n')
    binario = tmp_path / "echo"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)])

    res = runner.invoke(app, ["run", str(binario)])
    assert res.exit_code == 0
    assert "HOLA" in res.stdout

    # Run JSON
    res_j = runner.invoke(app, ["run", str(binario), "--json"])
    assert res_j.exit_code == 0
    data = json.loads(res_j.stdout)
    assert data["codigo_retorno"] == 0

    # Segfault
    f_seg = tmp_path / "seg.c"
    f_seg.write_text("int main() { int *p = 0; return *p; }\n")
    b_seg = tmp_path / "seg"
    subprocess.run(["gcc", str(f_seg), "-o", str(b_seg)])
    res_seg = runner.invoke(app, ["run", str(b_seg)])
    assert res_seg.exit_code != 0


def test_cli_test_rich_output(tmp_path):
    fuente = tmp_path / "prog.c"
    fuente.write_text('#include <stdio.h>\nint main(void) { printf("42\\n"); return 0; }\n')
    binario = tmp_path / "prog"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)])

    tc_dir = tmp_path / "tests"
    tc_dir.mkdir()
    (tc_dir / "case.in").write_text("")
    (tc_dir / "case.out").write_text("42\n")

    res = runner.invoke(app, ["test", str(binario), str(tc_dir)])
    assert res.exit_code == 0
    assert "PASS" in res.stdout


def test_cli_test_no_cases(tmp_path):
    binario = tmp_path / "dummy"
    binario.touch()
    res = runner.invoke(app, ["test", str(binario), str(tmp_path)])
    assert res.exit_code == 2


def test_cli_doctor():
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "Bubblewrap" in res.stdout


def test_sandbox_edge_cases(tmp_path):
    # Non existent
    ret, out, err, t, e_type = ejecutar_aislado(Path("/no/binario"))
    assert e_type == "FILE_NOT_FOUND"

    # Infinite loop / timeout
    f_loop = tmp_path / "loop.c"
    f_loop.write_text("int main() { while(1); }\n")
    b_loop = tmp_path / "loop"
    subprocess.run(["gcc", str(f_loop), "-o", str(b_loop)])
    ret, out, err, t, e_type = ejecutar_aislado(b_loop, timeout_segundos=0.5, usar_bwrap=False)
    assert e_type == "TIMEOUT"


def test_cli_main_block(monkeypatch):
    monkeypatch.setattr("sys.argv", ["nostromo", "--version"])
    try:
        nostromo.cli.main()
    except SystemExit as e:
        assert e.code == 0
