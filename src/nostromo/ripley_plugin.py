"""Plugin de NOSTROMO para integración transparente con RIPLEY."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from nostromo.core.runner import descubrir_casos_prueba, evaluar_binario


class NostromoPlugin:
    """Plugin de ejecución en Sandbox y evaluación de testcases para Ripley."""

    name = "sandbox_runner"
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def execute(self, workspace: Path, manifest_config: Dict[str, Any]) -> Dict[str, Any]:
        # Buscar binario compilado en workspace
        binarios = [p for p in workspace.glob("*") if p.is_file() and not p.suffix and not p.name.startswith(".")]
        if not binarios:
            return {"ok": False, "observaciones": [{"codigo": "NO_BINARY", "mensaje": "No se encontró un ejecutable en el workspace."}]}

        binario = binarios[0]
        testcases_dir = workspace / "testcases" if (workspace / "testcases").is_dir() else workspace
        casos = descubrir_casos_prueba(testcases_dir)

        if not casos:
            return {"ok": True, "total_casos": 0, "observaciones": []}

        rep = evaluar_binario(binario, casos)
        observaciones = []
        for r in rep.resultados:
            if not r.paso:
                observaciones.append({
                    "codigo": f"TEST_{r.error_tipo or 'FAIL'}",
                    "severidad": "ERROR",
                    "mensaje": f"Caso de prueba '{r.nombre}' falló: {r.error_tipo or 'Diferencia en salida'}",
                    "detalle": r.diff_lineas[:5],
                })

        return {
            "ok": rep.ok,
            "total_casos": rep.total_casos,
            "aprobados": rep.casos_aprobados,
            "fallidos": rep.casos_fallidos,
            "porcentaje": rep.porcentaje_aprobacion,
            "observaciones": observaciones,
        }
