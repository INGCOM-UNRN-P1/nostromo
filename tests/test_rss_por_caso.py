"""Regresión de NOSTROMO-D0302: el pico de memoria es de CADA caso, no el acumulado.

`getrusage(RUSAGE_CHILDREN).ru_maxrss` es el máximo de todos los hijos que el
proceso esperó hasta ese momento: en una suite, un caso liviano heredaba el
pico de uno anterior. Lo consumen la heurística `posible_leak` y las columnas de
RAM del reporte.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from nostromo.core.sandbox import ejecutar_aislado

necesita_gcc = pytest.mark.skipif(not shutil.which("gcc"), reason="requiere gcc")

PESADO = """#include <stdlib.h>
#include <string.h>
int main(void) { size_t n = 60u * 1024 * 1024; char *p = malloc(n); if (!p) return 1; memset(p, 1, n); free(p); return 0; }
"""
LIVIANO = "int main(void) { return 0; }\n"


def _compilar(tmp_path: Path, nombre: str, fuente: str) -> Path:
    c = tmp_path / f"{nombre}.c"
    c.write_text(fuente, encoding="utf-8")
    binario = tmp_path / nombre
    subprocess.run(["gcc", "-O0", str(c), "-o", str(binario)], check=True)
    return binario


@necesita_gcc
def test_un_caso_liviano_no_hereda_el_pico_de_uno_pesado(tmp_path):
    pesado = _compilar(tmp_path, "pesado", PESADO)
    liviano = _compilar(tmp_path, "liviano", LIVIANO)

    r_pesado = ejecutar_aislado(pesado, memoria_mb=512, usar_bwrap=False)
    r_liviano = ejecutar_aislado(liviano, memoria_mb=512, usar_bwrap=False)

    assert r_pesado.max_rss_kb > 50 * 1024, "el caso pesado debe medir su propio pico"
    assert r_liviano.max_rss_kb < 20 * 1024, "el liviano no puede heredar el del pesado"


@necesita_gcc
def test_el_orden_de_ejecucion_no_altera_la_medicion(tmp_path):
    liviano = _compilar(tmp_path, "liviano", LIVIANO)
    pesado = _compilar(tmp_path, "pesado", PESADO)

    antes = ejecutar_aislado(liviano, usar_bwrap=False).max_rss_kb
    ejecutar_aislado(pesado, memoria_mb=512, usar_bwrap=False)
    despues = ejecutar_aislado(liviano, usar_bwrap=False).max_rss_kb
    assert abs(despues - antes) < 4 * 1024


@necesita_gcc
def test_el_tiempo_de_cpu_es_del_caso(tmp_path):
    pesado = _compilar(tmp_path, "pesado", PESADO)
    liviano = _compilar(tmp_path, "liviano", LIVIANO)
    ejecutar_aislado(pesado, memoria_mb=512, usar_bwrap=False)
    r = ejecutar_aislado(liviano, usar_bwrap=False)
    assert r.cpu_tiempo_us < 20_000


@necesita_gcc
def test_el_timeout_sigue_funcionando_con_la_nueva_medicion(tmp_path):
    lazo = _compilar(tmp_path, "lazo", "int main(void) { volatile int x = 0; for (;;) { x++; } }\n")
    r = ejecutar_aislado(lazo, timeout_segundos=0.5, usar_bwrap=False)
    assert (r.codigo_retorno, r.error_tipo) == (124, "TIMEOUT")


@necesita_gcc
def test_stdout_y_stdin_siguen_viajando_bien(tmp_path):
    eco = _compilar(
        tmp_path,
        "eco",
        '#include <stdio.h>\nint main(void){ char b[64]; if (fgets(b, sizeof b, stdin)) fputs(b, stdout); return 0; }\n',
    )
    r = ejecutar_aislado(eco, stdin_texto="hola mundo\n", usar_bwrap=False)
    assert r.stdout == "hola mundo\n"
    assert r.codigo_retorno == 0
