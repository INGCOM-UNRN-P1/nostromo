"""Regresión de NOSTROMO-D0305 y NOSTROMO-D0801.

D0305: bajo bwrap `max_rss_kb` y `cpu_tiempo_us` medían al lanzador (9 MB y 3 ms
       para un programa que reserva 80 MB y gasta ~1 s de CPU).
D0801: el README prometía límites de tiempo de CPU y de tamaño de archivos que
       no existían.
"""

import shutil
import subprocess

import pytest

import nostromo.core.sandbox as sandbox
from nostromo.core.sandbox import ejecutar_aislado

necesita_bwrap = pytest.mark.skipif(
    not (shutil.which("bwrap") and sandbox._python_del_sistema()),
    reason="requiere bwrap y un python3 del sistema visible dentro del sandbox",
)
necesita_gcc = pytest.mark.skipif(not shutil.which("gcc"), reason="requiere gcc")

MEMORIA_80MB = """#include <stdlib.h>
#include <string.h>
#include <stdio.h>
int main(void) {
    size_t n = 80u * 1024 * 1024;
    char *p = malloc(n);
    if (!p) return 3;
    memset(p, 1, n);
    volatile long s = 0;
    for (long i = 0; i < 200000000L; i++) s += i;
    printf("%d\\n", p[n - 1]);
    return 0;
}
"""


def _compilar(tmp_path, nombre, fuente, extra=()):
    c = tmp_path / f"{nombre}.c"
    c.write_text(fuente, encoding="utf-8")
    binario = tmp_path / nombre
    subprocess.run(["gcc", "-O0", str(c), "-o", str(binario), *extra], check=True)
    return binario


@necesita_gcc
@necesita_bwrap
def test_bajo_bwrap_se_mide_al_programa_y_no_al_lanzador(tmp_path):
    binario = _compilar(tmp_path, "mem", MEMORIA_80MB)
    directo = ejecutar_aislado(binario, timeout_segundos=10, memoria_mb=512, usar_bwrap=False)
    sandbox_ = ejecutar_aislado(binario, timeout_segundos=10, memoria_mb=512, usar_bwrap=True)

    assert sandbox_.uso_medido is True
    assert sandbox_.max_rss_kb > 80 * 1024, "el pico de 80 MB del programa debe verse"
    assert sandbox_.cpu_tiempo_us > 100_000
    # Con el sandbox se mide lo mismo que sin él (tolerancia por el lanzador).
    assert abs(sandbox_.max_rss_kb - directo.max_rss_kb) < 0.1 * directo.max_rss_kb
    assert abs(sandbox_.cpu_tiempo_us - directo.cpu_tiempo_us) < 0.5 * directo.cpu_tiempo_us


@necesita_gcc
@necesita_bwrap
def test_un_programa_liviano_no_hereda_el_consumo_de_uno_pesado(tmp_path):
    pesado = _compilar(tmp_path, "mem", MEMORIA_80MB)
    liviano = _compilar(tmp_path, "liv", "int main(void) { return 0; }\n")
    ejecutar_aislado(pesado, timeout_segundos=10, memoria_mb=512)
    r = ejecutar_aislado(liviano, timeout_segundos=10, memoria_mb=512)
    assert r.max_rss_kb < 20 * 1024


def test_sin_lanzador_el_consumo_bajo_bwrap_queda_como_no_medido(tmp_path, monkeypatch):
    if not shutil.which("bwrap"):
        pytest.skip("requiere bwrap")
    binario = _compilar(tmp_path, "liv", "int main(void) { return 0; }\n")
    monkeypatch.setattr(sandbox, "_python_del_sistema", lambda: None)
    r = ejecutar_aislado(binario, timeout_segundos=5)
    assert r.codigo_retorno == 0
    assert r.uso_medido is False
    assert (r.cpu_tiempo_us, r.max_rss_kb) == (0, 0)


@necesita_gcc
def test_en_ejecucion_directa_el_consumo_siempre_esta_medido(tmp_path):
    binario = _compilar(tmp_path, "liv", "int main(void) { return 0; }\n")
    assert ejecutar_aislado(binario, usar_bwrap=False).uso_medido is True


@necesita_gcc
@necesita_bwrap
@pytest.mark.parametrize(
    "codigo, esperado",
    [
        ("int main(void){int *p=0; return *p;}", "SEGFAULT"),
        ("#include <stdlib.h>\nint main(void){abort();}", "ABORT"),
        ("int main(void){return 7;}", "NON_ZERO"),
    ],
)
def test_el_lanzador_no_altera_la_clasificacion_de_la_terminacion(tmp_path, codigo, esperado):
    r = ejecutar_aislado(_compilar(tmp_path, "p", codigo), timeout_segundos=5)
    assert r.error_tipo == esperado


@necesita_gcc
@necesita_bwrap
def test_el_limite_de_memoria_sigue_aplicandose_al_programa(tmp_path):
    binario = _compilar(tmp_path, "mem", MEMORIA_80MB)
    r = ejecutar_aislado(binario, timeout_segundos=10, memoria_mb=32)
    assert r.codigo_retorno == 3, "malloc de 80 MB debe fallar con un límite de 32 MB"


@necesita_gcc
@necesita_bwrap
def test_un_limite_de_memoria_chico_no_impide_arrancar_el_lanzador(tmp_path):
    binario = _compilar(tmp_path, "liv", "int main(void) { return 0; }\n")
    assert ejecutar_aislado(binario, timeout_segundos=5, memoria_mb=16).codigo_retorno == 0


@necesita_gcc
@pytest.mark.parametrize("usar_bwrap", [False, True])
def test_el_tamanio_de_archivo_esta_limitado(tmp_path, usar_bwrap):
    if usar_bwrap and not shutil.which("bwrap"):
        pytest.skip("requiere bwrap")
    binario = _compilar(
        tmp_path, "salida",
        '#include <stdio.h>\nint main(void) { for (;;) puts("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"); }\n',
    )
    r = ejecutar_aislado(binario, timeout_segundos=10, usar_bwrap=usar_bwrap, archivo_mb=1)
    assert r.error_tipo == "FILE_SIZE_LIMIT"
    assert len(r.stdout) <= 1024 * 1024 + 4096


@necesita_gcc
@pytest.mark.parametrize("usar_bwrap", [False, True])
def test_el_tiempo_de_cpu_esta_limitado_aun_con_varios_hilos(tmp_path, usar_bwrap):
    if usar_bwrap and not shutil.which("bwrap"):
        pytest.skip("requiere bwrap")
    binario = _compilar(
        tmp_path, "hilos",
        "#include <pthread.h>\n"
        "static void *quema(void *a) { volatile long s = 0; for (;;) s++; return a; }\n"
        "int main(void) { pthread_t t[4]; for (int i = 0; i < 4; i++) pthread_create(&t[i], 0, quema, 0);\n"
        "  for (int i = 0; i < 4; i++) pthread_join(t[i], 0); return 0; }\n",
        extra=("-pthread",),
    )
    # Timeout de pared de 2 s => 3 s de CPU: cuatro hilos lo agotan en ~0,75 s de reloj.
    r = ejecutar_aislado(binario, timeout_segundos=2, usar_bwrap=usar_bwrap)
    assert r.error_tipo in ("CPU_LIMIT", "SIGNAL_9"), r
    assert r.tiempo_ms < 1900


def test_un_consumo_no_medido_se_muestra_como_nd_y_no_como_cero(tmp_path, monkeypatch):
    import json
    from typer.testing import CliRunner
    from nostromo.cli import app

    if not shutil.which("bwrap"):
        pytest.skip("requiere bwrap")
    binario = _compilar(tmp_path, "liv", "int main(void) { return 0; }\n")
    monkeypatch.setattr(sandbox, "_python_del_sistema", lambda: None)
    res = CliRunner().invoke(app, ["run", str(binario), "--json"])
    datos = json.loads(res.stdout)
    assert datos["uso_medido"] is False
    assert datos["max_rss_kb"] is None and datos["cpu_tiempo_us"] is None


def test_la_heuristica_de_fuga_no_dispara_con_un_consumo_no_medido(tmp_path, monkeypatch):
    from nostromo.core.models import CasoPrueba
    from nostromo.core.runner import evaluar_binario

    if not shutil.which("bwrap"):
        pytest.skip("requiere bwrap")
    binario = _compilar(tmp_path, "liv", "int main(void) { return 0; }\n")
    monkeypatch.setattr(sandbox, "_python_del_sistema", lambda: None)
    resultado = evaluar_binario(binario, [CasoPrueba(nombre="c", stdin_texto="", stdout_esperado="")]).resultados[0]
    assert resultado.uso_medido is False
    assert resultado.posible_leak is False
