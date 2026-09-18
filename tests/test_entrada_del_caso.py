"""Regresión de NOSTROMO-D0903: el plugin informaba la salida esperada como entrada del caso.

`input_data` se llenaba con `stdout_esperado` y `ResultadoCaso` ni siquiera
guardaba el stdin, así que ripley nunca recibía la entrada real del caso.
"""

import subprocess

from nostromo.core.runner import evaluar_binario
from nostromo.core.models import CasoPrueba
from nostromo.ripley_plugin import NostromoPlugin


def _programa(tmp_path):
    fuente = tmp_path / "doble.c"
    fuente.write_text(
        '#include <stdio.h>\nint main(void) { int x; if (scanf("%d", &x) == 1) printf("%d\\n", x * 2); return 0; }\n',
        encoding="utf-8",
    )
    binario = tmp_path / "doble"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)], check=True)
    return binario


def test_el_resultado_conserva_la_entrada_del_caso(tmp_path):
    binario = _programa(tmp_path)
    caso = CasoPrueba(nombre="c1", archivo_in=None, stdin_texto="21\n", stdout_esperado="42\n")
    resultado = evaluar_binario(binario, [caso]).resultados[0]
    assert resultado.stdin_texto == "21\n"
    assert resultado.to_dict()["stdin_texto"] == "21\n"


def test_el_plugin_reporta_la_entrada_y_la_salida_por_separado(tmp_path):
    binario = _programa(tmp_path)
    pruebas = tmp_path / "testcases"
    pruebas.mkdir()
    (pruebas / "caso.in").write_text("21\n", encoding="utf-8")
    (pruebas / "caso.out").write_text("42\n", encoding="utf-8")

    res = NostromoPlugin().execute(tmp_path, {"binary_path": str(binario), "test_dir": str(pruebas)})
    caso = res["casos"][0]
    assert caso["input_data"] == "21\n"
    assert caso["expected_output"] == "42\n"
    assert caso["input_data"] != caso["expected_output"]
