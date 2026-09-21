"""Regresión de NOSTROMO-D0102/D0902: una sola versión y una sola identidad de plugin."""

import tomllib
from pathlib import Path

import nostromo
from nostromo.ripley_plugin import NostromoPlugin

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_la_version_del_plugin_es_la_del_paquete():
    assert NostromoPlugin.version == nostromo.__version__


def test_el_nombre_del_plugin_es_el_del_entry_point():
    datos = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    entry_points = datos["project"]["entry-points"]["ripley.plugins"]
    assert list(entry_points) == [NostromoPlugin.name]
