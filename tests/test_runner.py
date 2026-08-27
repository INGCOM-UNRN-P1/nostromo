"""Tests unitarios para el runner de nostromo."""

import subprocess
from pathlib import Path
import pytest
from nostromo.core.models import CasoPrueba
from nostromo.core.runner import descubrir_casos_prueba, evaluar_binario, normalizar_salida


def test_normalizar_salida():
    raw = "Hola mundo \r\nLinea 2  \n\n\n"
    norm = normalizar_salida(raw)
    assert norm == "Hola mundo\nLinea 2"


def test_descubrir_casos(tmp_path):
    (tmp_path / "01_sum.in").write_text("10 20\n")
    (tmp_path / "01_sum.out").write_text("30\n")
    (tmp_path / "02_resta.in").write_text("20 10\n")
    (tmp_path / "02_resta.out").write_text("10\n")

    casos = descubrir_casos_prueba(tmp_path)
    assert len(casos) == 2
    assert casos[0].nombre == "01_sum"
    assert casos[0].stdin_texto.strip() == "10 20"
    assert casos[0].stdout_esperado.strip() == "30"


def test_evaluar_binario_exitoso(tmp_path):
    fuente = tmp_path / "eco.c"
    fuente.write_text("""
    #include <stdio.h>
    int main(void) {
        int a, b;
        if (scanf("%d %d", &a, &b) == 2) {
            printf("%d\\n", a + b);
        }
        return 0;
    }
    """)
    binario = tmp_path / "eco"
    subprocess.run(["gcc", str(fuente), "-o", str(binario)], check=True)

    (tmp_path / "01.in").write_text("5 7\n")
    (tmp_path / "01.out").write_text("12\n")

    casos = descubrir_casos_prueba(tmp_path)
    rep = evaluar_binario(binario, casos)
    assert rep.ok is True
    assert rep.casos_aprobados == 1
