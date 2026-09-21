"""Regresión de NOSTROMO-D0803: el README documenta todos los comandos de la CLI."""

from pathlib import Path

from nostromo.cli import app

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_el_readme_menciona_cada_comando_de_la_cli():
    nombres = {c.name or c.callback.__name__.removesuffix("_cmd") for c in app.registered_commands}
    faltan = {n for n in nombres if f"nostromo {n}" not in README}
    assert not faltan, f"comandos sin documentar en el README: {faltan}"
