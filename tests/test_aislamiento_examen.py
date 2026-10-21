"""Perfil de examen del sandbox (Ola 9, QoL #747 y #764): sin sockets de red, /proc propio,
procesos limitados y escritura sólo en el directorio temporal asignado. No se degrada."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import nostromo.core.sandbox as sandbox
from nostromo.cli import app
from nostromo.core.sandbox import ejecutar_aislado, requisitos_examen
from nostromo.core.seccomp import ARQUITECTURAS, filtro_sin_red

runner = CliRunner()

disponible = pytest.mark.skipif(
    os.name == "nt" or not shutil.which("gcc") or bool(requisitos_examen()),
    reason="requiere gcc, bwrap con user namespaces, python3 del sistema y seccomp para la arquitectura",
)

RED = r"""
#include <stdio.h>
#include <sys/socket.h>
int main(void) {
    printf("inet=%d inet6=%d unix=%d\n", socket(AF_INET, SOCK_STREAM, 0) >= 0,
           socket(AF_INET6, SOCK_DGRAM, 0) >= 0, socket(AF_UNIX, SOCK_STREAM, 0) >= 0);
    return 0;
}
"""

PROCESOS = r"""
#include <stdio.h>
#include <dirent.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
int main(void) {
    int visibles = 0;
    DIR *d = opendir("/proc");
    for (struct dirent *e; d && (e = readdir(d)) != NULL;) {
        if (atoi(e->d_name) > 0) visibles++;
    }
    int creados = 0;
    for (int i = 0; i < 100; i++) {
        pid_t p = fork();
        if (p < 0) break;
        if (p == 0) { sleep(1); _exit(0); }
        creados++;
    }
    printf("visibles=%d creados=%d\n", visibles, creados);
    while (wait(NULL) > 0) {}
    return 0;
}
"""

ESCRITURA = r"""
#include <stdio.h>
int puede(const char *ruta) { FILE *f = fopen(ruta, "w"); if (!f) return 0; fputs("x", f); fclose(f); return 1; }
int main(int argc, char **argv) {
    printf("trabajo=%d tmp=%d junto_al_binario=%d afuera=%d\n", puede("salida.txt"), puede("/tmp/x"),
           puede(argv[1]), puede(argv[2]));
    return 0;
}
"""


def _compilar(tmp_path, nombre, codigo):
    fuente = tmp_path / f"{nombre}.c"
    fuente.write_text(codigo)
    binario = tmp_path / "bin" / nombre
    binario.parent.mkdir(exist_ok=True)
    subprocess.run(["gcc", "-o", str(binario), str(fuente)], check=True)
    return binario


def test_el_filtro_es_bpf_valido_para_cada_arquitectura():
    for maquina in ARQUITECTURAS:
        programa = filtro_sin_red(maquina)
        assert programa and len(programa) % 8 == 0
    assert filtro_sin_red("riscv64") is None


@disponible
def test_sin_sockets_de_red(tmp_path):
    res = ejecutar_aislado(_compilar(tmp_path, "red", RED), aislamiento="examen")
    assert res.codigo_retorno == 0, res.stderr
    assert res.stdout.strip() == "inet=0 inet6=0 unix=1"
    assert res.aislado and res.aislamiento == "examen"
    # el perfil estándar no filtra la syscall (sólo separa la red cuando puede)
    assert "inet=1" in ejecutar_aislado(tmp_path / "bin" / "red").stdout


@disponible
def test_proc_propio_y_procesos_limitados(tmp_path):
    res = ejecutar_aislado(_compilar(tmp_path, "procesos", PROCESOS), aislamiento="examen", max_procesos=10,
                           timeout_segundos=10)
    assert res.codigo_retorno == 0, res.stderr
    visibles, creados = (int(x.split("=")[1]) for x in res.stdout.split())
    assert visibles <= 4  # el init de bwrap, el medidor y el programa
    assert creados < 10


@disponible
def test_solo_escribe_en_el_directorio_asignado(tmp_path):
    binario = _compilar(tmp_path, "escritura", ESCRITURA)
    trabajo = tmp_path / "trabajo"
    en_casa = Path.home() / ".nostromo-examen-prueba"
    res = ejecutar_aislado(binario, args=[str(binario.parent / "copia"), str(en_casa)], aislamiento="examen",
                           directorio_trabajo=trabajo)
    assert res.stdout.strip() == "trabajo=1 tmp=1 junto_al_binario=0 afuera=0", res.stderr
    assert (trabajo / "salida.txt").read_text() == "x"
    assert not en_casa.exists() and not (binario.parent / "copia").exists()

    # Lo que escribe en /tmp (fuera del directorio asignado) queda en un tmpfs efímero.
    afuera = tmp_path / "afuera.txt"
    res = ejecutar_aislado(binario, args=["/a", str(afuera)], aislamiento="examen", directorio_trabajo=trabajo)
    assert res.codigo_retorno == 0 and not afuera.exists()

    # Sin directorio asignado se usa uno temporal que se borra al terminar.
    antes = set(os.listdir(sandbox.tempfile.gettempdir()))
    ejecutar_aislado(binario, args=["/a", "/b"], aislamiento="examen")
    nuevos = set(os.listdir(sandbox.tempfile.gettempdir())) - antes
    assert not [n for n in nuevos if n.startswith("nostromo-examen-")]


@disponible
def test_no_hereda_el_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_DEL_DOCENTE", "secreto")
    binario = _compilar(tmp_path, "entorno", '#include <stdio.h>\n#include <stdlib.h>\n'
                        'int main(void) { printf("%s\\n", getenv("TOKEN_DEL_DOCENTE") ? "si" : "no"); return 0; }\n')
    assert ejecutar_aislado(binario, aislamiento="examen").stdout.strip() == "no"


def test_no_se_degrada_sin_requisitos(tmp_path, monkeypatch):
    binario = tmp_path / "prog"
    binario.write_text("#!/bin/sh\nexit 0\n")
    binario.chmod(0o755)
    monkeypatch.setattr(sandbox, "requisitos_examen", lambda *_: ["bwrap (bubblewrap) no está instalado"])
    res = ejecutar_aislado(binario, aislamiento="examen")
    assert res.error_tipo == "SANDBOX_NO_DISPONIBLE" and not res.aislado
    assert "No se ejecutó" in res.stderr

    import nostromo.core.sandbox as modulo
    monkeypatch.setattr(modulo, "requisitos_examen", lambda *_: ["falta seccomp"])
    salida = runner.invoke(app, ["run", str(binario), "--aislamiento", "examen"])
    assert salida.exit_code == 2 and "falta seccomp" in salida.output
    assert runner.invoke(app, ["run", str(binario), "--aislamiento", "otro"]).exit_code == 2


@disponible
def test_cli_run_y_test(tmp_path):
    binario = _compilar(tmp_path, "red", RED)
    res = runner.invoke(app, ["run", str(binario), "--aislamiento", "examen", "--json"])
    assert res.exit_code == 0, res.output
    assert '"aislamiento": "examen"' in res.output and "inet=0" in res.output
    casos = tmp_path / "casos"
    casos.mkdir()
    (casos / "uno.in").write_text("")
    (casos / "uno.out").write_text("inet=0 inet6=0 unix=1\n")
    res = runner.invoke(app, ["test", str(binario), str(casos), "--aislamiento", "examen", "--json"])
    assert res.exit_code == 0, res.output


def test_python_del_sistema_para_el_medidor():
    # El medidor corre con el python del sistema dentro del sandbox: tiene que poder importarse ahí.
    assert sys.version_info >= (3, 8)
