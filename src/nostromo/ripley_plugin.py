"""Plugin de NOSTROMO para integración transparente con RIPLEY."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from nostromo import __version__
from nostromo.core.models import SCHEMA_VERSION
from nostromo.core.runner import descubrir_casos_prueba, evaluar_binario


class NostromoPlugin:
    """Plugin de ejecución en Sandbox y evaluación de testcases para Ripley.

    Contrato de `execute` (`schema_version` 1.0.0): las claves canónicas son las
    inglesas (`total`, `passed`, `failed`, `cases`, y `name`/`passed` en cada
    caso), que es lo que lee ripley. Las españolas (`total_casos`, `aprobados`,
    `fallidos`, `casos`) son alias de compatibilidad con consumidores anteriores
    y se conservan idénticas; no agregar claves nuevas solo en español.
    """

    name = "sandbox"
    version = __version__

    def is_available(self) -> bool:
        return True

    def execute(self, workspace: Path, manifest_config: Dict[str, Any]) -> Dict[str, Any]:
        binario = manifest_config.get("binary_path") or manifest_config.get("binary")
        if binario:
            binario = Path(binario)
        else:
            binarios = [p for p in workspace.glob("*") if p.is_file() and not p.suffix and not p.name.startswith(".")]
            if not binarios:
                return {"ok": False, "observaciones": [{"codigo": "NO_BINARY", "mensaje": "No se encontró un ejecutable en el workspace."}]}
            binario = binarios[0]

        testcases_dir = manifest_config.get("test_dir")
        if testcases_dir:
            testcases_dir = Path(testcases_dir)
        else:
            testcases_dir = workspace / "testcases" if (workspace / "testcases").is_dir() else (workspace / "tests" if (workspace / "tests").is_dir() else workspace)

        casos = descubrir_casos_prueba(testcases_dir)
        if not casos:
            return {"schema_version": SCHEMA_VERSION, "ok": True, "total_casos": 0, "total": 0, "aprobados": 0, "passed": 0, "fallidos": 0, "failed": 0, "casos": [], "cases": [], "observaciones": []}

        rep = evaluar_binario(binario, casos)
        observaciones = []
        cases_list = []
        for r in rep.resultados:
            cases_list.append({
                "name": r.nombre,
                "passed": r.paso,
                "input_data": r.stdin_texto,
                "expected_output": getattr(r, "stdout_esperado", ""),
                "actual_output": getattr(r, "stdout_obtenido", ""),
                "timed_out": (r.error_tipo == "TIMEOUT"),
                "sanitizer_error": r.stderr_obtenido if not r.paso else None,
                "memory_leak": ("leak" in (r.stderr_obtenido or "").lower()),
                "return_code": r.codigo_retorno,
            })
            if not r.paso:
                observaciones.append({
                    "codigo": f"TEST_{r.error_tipo or 'FAIL'}",
                    "rule_code": f"TEST_{r.error_tipo or 'FAIL'}",
                    "rule_name": f"Fallo en Caso: {r.nombre}",
                    "severidad": "ERROR",
                    "severity": "ERROR",
                    "mensaje": f"Caso de prueba '{r.nombre}' falló: {r.error_tipo or 'Diferencia en salida'}",
                    "message": f"Caso de prueba '{r.nombre}' falló: {r.error_tipo or 'Diferencia en salida'}",
                    "detalle": r.diff_lineas[:5],
                    "source_plugin": "nostromo",
                })

        return {
            "schema_version": SCHEMA_VERSION,
            "ok": rep.ok,
            "total_casos": rep.total_casos,
            "total": rep.total_casos,
            "aprobados": rep.casos_aprobados,
            "passed": rep.casos_aprobados,
            "fallidos": rep.casos_fallidos,
            "failed": rep.casos_fallidos,
            "porcentaje": rep.porcentaje_aprobacion,
            "casos": cases_list,
            "cases": cases_list,
            "observaciones": observaciones,
        }
