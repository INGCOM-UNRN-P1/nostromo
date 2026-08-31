"""CLI de NOSTROMO — Sandbox de ejecución aislada y evaluador de casos de prueba."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nostromo import __version__
from nostromo.core.runner import descubrir_casos_prueba, evaluar_binario
from nostromo.core.sandbox import ejecutar_aislado

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="nostromo",
    help="📦 NOSTROMO — Sandbox de ejecución aislada con Bubblewrap y evaluador de casos de prueba .in/.out.",
    add_completion=True,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]NOSTROMO[/bold cyan] versión [bold]{__version__}[/bold]")
        raise typer.Exit(code=0)


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Muestra la versión de NOSTROMO.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    pass


@app.command("run")
def run_cmd(
    binario: Path = typer.Argument(..., help="Binario ejecutable a correr."),
    args: Optional[List[str]] = typer.Argument(None, help="Argumentos a pasar al binario."),
    stdin: Optional[str] = typer.Option(None, "--stdin", "-i", help="Datos enviados por stdin."),
    timeout: float = typer.Option(2.0, "--timeout", "-t", help="Timeout máximo en segundos."),
    memory: int = typer.Option(128, "--memory", "-m", help="Límite de memoria en Megabytes."),
    json_output: bool = typer.Option(False, "--json", help="Salida en JSON."),
) -> None:
    """Ejecuta un binario dentro del sandbox con límites estrictos de CPU y memoria."""
    ret, stdout, stderr, t_ms, err_tipo = ejecutar_aislado(
        binario=binario,
        args=args or [],
        stdin_texto=stdin or "",
        timeout_segundos=timeout,
        memoria_mb=memory,
    )

    if json_output:
        data = {
            "binario": str(binario),
            "codigo_retorno": ret,
            "tiempo_ms": round(t_ms, 2),
            "error_tipo": err_tipo,
            "stdout": stdout,
            "stderr": stderr,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        raise typer.Exit(code=ret if ret != 0 else 0)

    if stdout:
        console.print(stdout, end="")
    if stderr:
        err_console.print(f"[red]{stderr}[/red]", end="")
    if err_tipo:
        err_console.print(f"\n[bold red]Terminado con señal / error: {err_tipo} ({t_ms:.1f} ms)[/bold red]")

    raise typer.Exit(code=ret if ret != 0 else 0)


def generar_seccion_markdown(reporte) -> str:
    """Genera sección de evaluación en sandbox de casos de prueba para Dredd."""
    lines = ["## Pruebas Funcionales en Sandbox (Nostromo)\n"]
    lines.append(f"- **Binario evaluado:** `{reporte.binario.name}`")
    lines.append(f"- **Casos de prueba evaluados:** {reporte.total_casos}")
    lines.append(f"- **Aprobados:** {reporte.casos_aprobados}/{reporte.total_casos} ({reporte.porcentaje_aprobacion:.1f}%)\n")
    if reporte.ok:
        lines.append("> [!TIP]\n> **Casos de Prueba Aprobados:** El binario superó el 100% de los casos de prueba dentro del sandbox.\n")
    else:
        lines.append("> [!WARNING]\n> **Fallo en Casos de Prueba:** Se detectaron salidas incorrectas, errores de ejecución o timeouts.\n")
        lines.append("| Caso | Estado | Retorno | Tiempo (ms) | Diagnóstico |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        for r in reporte.resultados:
            st = "✓ PASS" if r.paso else f"❌ FAIL ({r.error_tipo or 'Mismatch'})"
            diag = "OK" if r.paso else (r.diff_lineas[0].strip() if r.diff_lineas else r.stderr_obtenido[:40] or "Salida distinta")
            lines.append(f"| `{r.nombre}` | **{st}** | `{r.codigo_retorno}` | {r.tiempo_ms:.1f} ms | {diag} |")
        lines.append("")
    return "\n".join(lines)


@app.command("test")
@app.command("check")
def test_cmd(
    binario: Path = typer.Argument(..., help="Binario ejecutable a evaluar."),
    test_dir: Path = typer.Argument(..., help="Directorio con archivos .in y .out."),
    timeout: float = typer.Option(2.0, "--timeout", "-t", help="Timeout por caso en segundos."),
    memory: int = typer.Option(128, "--memory", "-m", help="Límite de memoria en MB."),
    json_output: bool = typer.Option(False, "--json", help="Salida estructurada en JSON."),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", "-o", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
) -> None:
    """Ejecuta una suite completa de casos de prueba .in/.out y genera el reporte de evaluación."""
    casos = descubrir_casos_prueba(test_dir)
    if not casos:
        err_console.print(f"[red]Error:[/red] No se encontraron casos de prueba (.in/.out) en '{test_dir}'.")
        raise typer.Exit(code=2)

    reporte = evaluar_binario(binario, casos, timeout_segundos=timeout, memoria_mb=memory)

    if output_md:
        md_text = generar_seccion_markdown(reporte)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")
        console.print(f"[green]✓ Sección Markdown generada en:[/green] [cyan]{output_md}[/cyan]")
        raise typer.Exit(code=0 if reporte.ok else 1)

    if json_output:
        print(json.dumps(reporte.to_dict(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if reporte.ok else 1)

    # Renderizar tabla Rich
    tabla = Table(title=f"Evaluación de Casos de Prueba: {binario.name}")
    tabla.add_column("Caso", style="bold cyan")
    tabla.add_column("Resultado", justify="center")
    tabla.add_column("Retorno", justify="center")
    tabla.add_column("Tiempo", justify="right")
    tabla.add_column("Detalle")

    for r in reporte.resultados:
        res_str = "[bold green]PASS[/bold green]" if r.paso else f"[bold red]FAIL ({r.error_tipo})[/bold red]"
        detalle = "Coincidencia exacta" if r.paso else (r.diff_lineas[0].strip() if r.diff_lineas else r.stderr_obtenido[:40])
        tabla.add_row(r.nombre, res_str, str(r.codigo_retorno), f"{r.tiempo_ms:.1f} ms", detalle)

    console.print(tabla)

    color_score = "green" if reporte.ok else "yellow" if reporte.porcentaje_aprobacion >= 60 else "red"
    console.print(Panel(
        f"Aprobados: [bold green]{reporte.casos_aprobados}/{reporte.total_casos}[/bold green] "
        f"([bold {color_score}]{reporte.porcentaje_aprobacion:.1f}%[/bold {color_score}]) · "
        f"Tiempo Total: [cyan]{reporte.tiempo_total_ms:.1f} ms[/cyan]",
        title="Resumen de Evaluación",
        border_style=color_score,
    ))

    raise typer.Exit(code=0 if reporte.ok else 1)


@app.command("doctor")
def doctor_cmd() -> None:
    """Verifica disponibilidad del motor de sandbox (Bubblewrap / namespaces del kernel)."""
    tabla = Table(title="Diagnóstico del Sandbox NOSTROMO")
    tabla.add_column("Componente", style="bold cyan")
    tabla.add_column("Estado", justify="center")
    tabla.add_column("Detalle")

    bwrap = shutil.which("bwrap")
    tabla.add_row("Bubblewrap (bwrap)", "[green]✓ Presente[/green]" if bwrap else "[yellow]⚠️ Ausente (fallback a setrlimit)[/yellow]", bwrap or "Instalar bubblewrap con sudo apt install bubblewrap")
    console.print(tabla)


@app.command("report")
def report_cmd(
    binario: Path = typer.Argument(..., help="Binario ejecutable a evaluar."),
    test_dir: Path = typer.Argument(..., help="Directorio con archivos .in y .out."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta de destino del archivo Markdown."),
) -> None:
    """Genera directamente la sección de reporte Markdown de NOSTROMO para Dredd."""
    casos = descubrir_casos_prueba(test_dir)
    if not casos:
        err_console.print(f"[red]Error:[/red] No se encontraron casos de prueba (.in/.out) en '{test_dir}'.")
        raise typer.Exit(code=2)
    reporte = evaluar_binario(binario, casos)
    md_content = generar_seccion_markdown(reporte)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")
        console.print(f"[green]✓ Reporte Markdown generado en:[/green] [cyan]{output}[/cyan]")
    else:
        print(md_content)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
