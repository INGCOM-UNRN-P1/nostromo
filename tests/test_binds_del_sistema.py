"""Regresión de NOSTROMO-D0303: no montar directorios del sistema que no existen."""

from nostromo.core.sandbox import _binds_del_sistema


def _pares(args):
    return list(zip(args[1::3], args[2::3]))


def test_sin_lib64_no_se_monta_lib_sobre_lib64():
    args = _binds_del_sistema(existe=lambda d: d != "/lib64")
    assert "/lib64" not in args
    assert ("/lib", "/lib") in _pares(args)


def test_cada_directorio_se_monta_sobre_si_mismo():
    args = _binds_del_sistema(existe=lambda d: True)
    assert all(origen == destino for origen, destino in _pares(args))
    assert {o for o, _ in _pares(args)} == {"/usr", "/lib", "/lib64", "/bin"}


def test_un_directorio_ausente_se_omite():
    assert _binds_del_sistema(existe=lambda d: d == "/usr") == ["--ro-bind", "/usr", "/usr"]
