"""ejecutar_comando_aislado: compilar dentro del sandbox (lo que pedía N-RIPLEY-03 para que
ripley evaluate compile con daedalus sin perder el aislamiento)."""

import os
import shutil

import pytest

import nostromo.core.sandbox as sandbox
from nostromo.core.sandbox import ejecutar_comando_aislado

necesita_bwrap = pytest.mark.skipif(
    not (shutil.which("bwrap") and sandbox.bwrap_funciona(shutil.which("bwrap") or "")),
    reason="requiere bwrap con user namespaces",
)
necesita_gcc = pytest.mark.skipif(not shutil.which("gcc"), reason="requiere gcc")
# sh, sleep y binarios sin .exe: en Windows no hay bwrap y el aislamiento es solo el timeout.
pytestmark_posix = pytest.mark.skipif(os.name == "nt", reason="comandos POSIX")


@pytestmark_posix
@necesita_gcc
def test_compila_y_escribe_solo_donde_se_le_permite(tmp_path):
    fuentes = tmp_path / "fuentes"
    salida = tmp_path / "salida"
    fuentes.mkdir()
    salida.mkdir()
    (fuentes / "a.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    res = ejecutar_comando_aislado(
        ["gcc", "-std=c11", str(fuentes / "a.c"), "-o", str(salida / "a")],
        escribibles=[salida], legibles=[fuentes], timeout_segundos=30,
    )
    assert res.codigo_retorno == 0, res.stderr
    assert (salida / "a").exists()


@pytestmark_posix
@necesita_bwrap
@necesita_gcc
def test_el_codigo_compilado_no_ve_archivos_de_afuera(tmp_path):
    """Un #include con ruta absoluta a la solución canónica no la encuentra dentro del sandbox."""
    secreto = tmp_path / "canon" / "solucion.c"
    secreto.parent.mkdir()
    secreto.write_text("int secreto(void) { return 42; }\n", encoding="utf-8")
    trabajo = tmp_path / "entrega"
    trabajo.mkdir()
    (trabajo / "a.c").write_text(f'#include "{secreto}"\nint main(void) {{ return secreto(); }}\n', encoding="utf-8")
    res = ejecutar_comando_aislado(
        ["gcc", str(trabajo / "a.c"), "-o", str(trabajo / "a")],
        escribibles=[trabajo], timeout_segundos=30,
    )
    assert res.aislado
    assert res.codigo_retorno != 0
    assert "solucion.c" in res.stderr


@pytestmark_posix
@necesita_bwrap
def test_no_puede_escribir_fuera_de_los_escribibles(tmp_path):
    legible = tmp_path / "solo_lectura"
    legible.mkdir()
    res = ejecutar_comando_aislado(["sh", "-c", f"echo x > {legible}/intento"], legibles=[legible])
    assert res.aislado
    assert res.codigo_retorno != 0
    assert not (legible / "intento").exists()


@pytestmark_posix
@necesita_bwrap
def test_tmp_es_propio_y_hay_directorio_de_trabajo(tmp_path):
    (tmp_path / "marca").write_text("", encoding="utf-8")
    res = ejecutar_comando_aislado(["sh", "-c", "touch /tmp/intermedio && ls"],
                                   escribibles=[tmp_path], directorio=tmp_path)
    assert res.codigo_retorno == 0, res.stderr
    assert "marca" in res.stdout


@pytestmark_posix
def test_sin_bwrap_corre_con_limites_y_lo_informa(tmp_path):
    res = ejecutar_comando_aislado(["sh", "-c", "pwd"], directorio=tmp_path, usar_bwrap=False)
    assert res.codigo_retorno == 0
    assert not res.aislado
    assert os.path.realpath(res.stdout.strip()) == os.path.realpath(tmp_path)


@pytestmark_posix
def test_timeout(tmp_path):
    res = ejecutar_comando_aislado(["sleep", "5"], timeout_segundos=0.5, usar_bwrap=False)
    assert res.error_tipo == "TIMEOUT"


def test_comando_vacio():
    assert ejecutar_comando_aislado([]).codigo_retorno == 1
