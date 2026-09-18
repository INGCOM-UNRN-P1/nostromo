"""Modelos de datos para el motor de sandboxing y test runner de NOSTROMO."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CasoPrueba:
    """Representa un caso de prueba individual con entrada y salida esperada."""
    nombre: str
    archivo_in: Optional[Path] = None
    archivo_out: Optional[Path] = None
    stdin_texto: str = ""
    stdout_esperado: str = ""
    timeout_segundos: float = 2.0
    memoria_mb: int = 128
    timeout_adaptativo: bool = False


@dataclass
class ResultadoCaso:
    """Resultado de la ejecución de un caso de prueba."""
    nombre: str
    paso: bool
    codigo_retorno: int
    tiempo_ms: float
    stdout_obtenido: str
    stderr_obtenido: str
    stdout_esperado: str
    error_tipo: Optional[str] = None   # "TIMEOUT", "OOM", "SEGFAULT", "DIFF", "NON_ZERO"
    stdin_texto: str = ""
    diff_lineas: List[str] = field(default_factory=list)
    diff_lado_a_lado: List[Tuple[str, str]] = field(default_factory=list)
    cpu_tiempo_us: int = 0
    max_rss_kb: int = 0
    posible_leak: bool = False
    uso_medido: bool = True
    hal_diagnostico: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nombre": self.nombre,
            "paso": self.paso,
            "codigo_retorno": self.codigo_retorno,
            "tiempo_ms": round(self.tiempo_ms, 2),
            "cpu_tiempo_us": self.cpu_tiempo_us,
            "max_rss_kb": self.max_rss_kb,
            "posible_leak": self.posible_leak,
            "uso_medido": self.uso_medido,
            "error_tipo": self.error_tipo,
            "stdin_texto": self.stdin_texto[:500],
            "stdout_obtenido": self.stdout_obtenido[:500],
            "stdout_esperado": self.stdout_esperado[:500],
            "stderr_obtenido": self.stderr_obtenido[:500],
            "diff_lineas": self.diff_lineas[:20],
            "hal_diagnostico": self.hal_diagnostico,
        }


@dataclass
class ReporteEvaluacion:
    """Reporte consolidado de una suite de casos de prueba."""
    binario: Path
    total_casos: int
    casos_aprobados: int
    casos_fallidos: int
    tiempo_total_ms: float
    cpu_tiempo_total_us: int = 0
    max_rss_pico_kb: int = 0
    resultados: List[ResultadoCaso] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.casos_fallidos == 0 and self.total_casos > 0

    @property
    def porcentaje_aprobacion(self) -> float:
        return (self.casos_aprobados / self.total_casos * 100.0) if self.total_casos > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "binario": str(self.binario),
            "ok": self.ok,
            "total_casos": self.total_casos,
            "casos_aprobados": self.casos_aprobados,
            "casos_fallidos": self.casos_fallidos,
            "porcentaje_aprobacion": round(self.porcentaje_aprobacion, 1),
            "tiempo_total_ms": round(self.tiempo_total_ms, 2),
            "cpu_tiempo_total_us": self.cpu_tiempo_total_us,
            "max_rss_pico_kb": self.max_rss_pico_kb,
            "resultados": [r.to_dict() for r in self.resultados],
        }
