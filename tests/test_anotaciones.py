"""Regresión de NOSTROMO-D0201: `Tuple` se usaba en runner.py sin importarse."""

import typing

from nostromo.core import runner


def test_las_anotaciones_de_runner_se_resuelven():
    # `from __future__ import annotations` difiere el NameError hasta que alguien
    # resuelve las anotaciones (typer, sphinx, mypy en runtime...).
    sugerencias = typing.get_type_hints(runner.generar_diff_lado_a_lado)
    assert sugerencias["return"] == typing.List[typing.Tuple[str, str]]
