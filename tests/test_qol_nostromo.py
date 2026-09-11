"""Pruebas unitarias de las mejoras QoL en NOSTROMO."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typer.testing import CliRunner

from nostromo.cli import app
from nostromo.core.models import CasoPrueba, ReporteEvaluacion, ResultadoCaso
from nostromo.core.runner import (
    calcular_timeout_adaptativo,
    descubrir_casos_prueba,
    evaluar_binario,
    generar_diff_lado_a_lado,
    normalizar_salida,
)
from nostromo.core.sandbox import ejecutar_aislado

runner = CliRunner()


def compilar_c(tmp_path: Path, nombre: str, codigo: str) -> Path:
    src = tmp_path / f"{nombre}.c"
    out = tmp_path / nombre
    src.write_text(codigo, encoding="utf-8")
    subprocess.run(["gcc", "-O0", str(src), "-o", str(out)], check=True)
    return out


def test_normalizacion_salida_rn_y_espacios():
    raw_dos = "linea 1   \r\nlinea 2  \r\n\r\n"
    norm = normalizar_salida(raw_dos)
    assert norm == "linea 1\nlinea 2"


def test_generar_diff_lado_a_lado():
    esp = "alpha\nbeta\ngamma"
    obt = "alpha\nBETA\ngamma\ndelta"
    pares = generar_diff_lado_a_lado(esp, obt)
    assert len(pares) == 4
    assert pares[0] == ("alpha", "alpha")
    assert pares[1] == ("beta", "BETA")
    assert pares[3] == ("", "delta")


def test_calcular_timeout_adaptativo():
    t_peq = calcular_timeout_adaptativo(100, 2.0)
    assert t_peq == 2.0
    t_gran = calcular_timeout_adaptativo(110_000, 2.0)
    assert t_gran > 2.0
    assert t_gran <= 20.0


def test_medicion_cpu_y_memoria(tmp_path: Path):
    binario = compilar_c(tmp_path, "busy", """
    #include <stdio.h>
    int main(void) {
        volatile long s = 0;
        for (long i = 0; i < 500000; i++) s += i;
        printf("suma=%ld\\n", s);
        return 0;
    }
    """)
    res = ejecutar_aislado(binario, timeout_segundos=2.0, usar_bwrap=False)
    assert res.codigo_retorno == 0
    assert hasattr(res, "cpu_tiempo_us")
    assert hasattr(res, "max_rss_kb")
    assert res.cpu_tiempo_us >= 0
    assert res.max_rss_kb >= 0


def test_limite_memoria_virtual_estricto(tmp_path: Path):
    # Intentar alocar 200 MB con límite de 32 MB
    binario = compilar_c(tmp_path, "oom", """
    #include <stdlib.h>
    #include <string.h>
    int main(void) {
        size_t n = 200 * 1024 * 1024;
        char *p = malloc(n);
        if (!p) return 42;
        memset(p, 1, n);
        return 0;
    }
    """)
    res = ejecutar_aislado(binario, memoria_mb=32, usar_bwrap=False)
    # Debe retornar 42 (malloc falló) o recibir señal
    assert res.codigo_retorno in (42, 137, -9, 1) or res.error_tipo in ("NON_ZERO", "OOM", "SIGNAL_9", "SIGNAL_11")


def test_evaluar_binario_con_diff_y_metricas(tmp_path: Path):
    binario = compilar_c(tmp_path, "echo_app", """
    #include <stdio.h>
    int main(void) {
        char buf[64];
        if (fgets(buf, sizeof(buf), stdin)) {
            printf("RESP:%s", buf);
        }
        return 0;
    }
    """)
    casos = [
        CasoPrueba(nombre="c1", stdin_texto="hola\n", stdout_esperado="RESP:hola\n"),
        CasoPrueba(nombre="c2", stdin_texto="chau\n", stdout_esperado="RESP:distinto\n"),
    ]
    rep = evaluar_binario(binario, casos, timeout_adaptativo=True, integrar_hal=False)
    assert rep.total_casos == 2
    assert rep.casos_aprobados == 1
    assert rep.casos_fallidos == 1
    assert len(rep.resultados[1].diff_lado_a_lado) > 0


def test_cli_stress_cmd(tmp_path: Path):
    binario = compilar_c(tmp_path, "simple", """
    #include <stdio.h>
    int main(void) {
        printf("OK\\n");
        return 0;
    }
    """)
    in_f = tmp_path / "in.txt"
    in_f.write_text("dummy", encoding="utf-8")
    out_f = tmp_path / "out.txt"
    out_f.write_text("OK\n", encoding="utf-8")

    res = runner.invoke(app, ["stress", str(binario), str(in_f), "--out", str(out_f), "--iterations", "10", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["iteraciones"] == 10
    assert data["exitos"] == 10
    assert data["fallos"] == 0
    assert "rss_inicial_kb" in data


def test_cli_run_con_captura_separada(tmp_path: Path):
    binario = compilar_c(tmp_path, "stds", """
    #include <stdio.h>
    int main(void) {
        fprintf(stdout, "stdout msg\\n");
        fprintf(stderr, "stderr msg\\n");
        return 0;
    }
    """)
    res = runner.invoke(app, ["run", str(binario), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert "stdout msg" in data["stdout"]
    assert "stderr msg" in data["stderr"]
    assert data["cpu_tiempo_us"] >= 0
