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


def _codigo_de_salida(ret: int, err_tipo: Optional[str], propagar: bool) -> int:
    """Contrato 0/1/2 de la CLI: 0 el programa terminó bien, 1 falló, 2 no se pudo ejecutar.

    Antes `run` devolvía el código del programa evaluado tal cual (139, o 245 para
    una señal), y un script no podía distinguir un fallo de nostromo de un retorno
    arbitrario del estudiante. Con `--exit-code` se conserva la transparencia de
    `env`/`timeout`: el código del programa, con la señal como 128+n.
    """
    if err_tipo in ("FILE_NOT_FOUND", "EXCEPTION"):
        return 2
    if propagar:
        return ret if 0 <= ret <= 255 else (128 + -ret if ret < 0 else ret & 0xFF)
    return 0 if ret == 0 and not err_tipo else 1


@app.command("run")
def run_cmd(
    binario: Path = typer.Argument(..., help="Binario ejecutable a correr."),
    args: Optional[List[str]] = typer.Argument(None, help="Argumentos a pasar al binario."),
    stdin: Optional[str] = typer.Option(None, "--stdin", "-i", help="Datos enviados por stdin."),
    timeout: float = typer.Option(2.0, "--timeout", "-t", help="Timeout máximo en segundos."),
    memory: int = typer.Option(128, "--memory", "-m", help="Límite de memoria en Megabytes."),
    json_output: bool = typer.Option(False, "--json", help="Salida en JSON."),
    propagar_codigo: bool = typer.Option(False, "--exit-code", help="Salir con el código del programa (señal = 128+n) en vez de 0/1/2."),
) -> None:
    """Ejecuta un binario dentro del sandbox con límites estrictos de CPU y memoria.

    Sale con 0 si el programa terminó bien, 1 si falló (retorno distinto de cero,
    señal o timeout) y 2 si no se pudo ejecutar; el código del programa está en el
    JSON (`codigo_retorno`) o se obtiene con --exit-code.
    """
    res = ejecutar_aislado(
        binario=binario,
        args=args or [],
        stdin_texto=stdin or "",
        timeout_segundos=timeout,
        memoria_mb=memory,
    )
    ret, stdout, stderr, t_ms, err_tipo = res
    cpu_us = getattr(res, "cpu_tiempo_us", 0)
    rss_kb = getattr(res, "max_rss_kb", 0)
    uso_medido = getattr(res, "uso_medido", True)

    if json_output:
        data = {
            "binario": str(binario),
            "codigo_retorno": ret,
            "tiempo_ms": round(t_ms, 2),
            "cpu_tiempo_us": cpu_us if uso_medido else None,
            "max_rss_kb": rss_kb if uso_medido else None,
            "uso_medido": uso_medido,
            "error_tipo": err_tipo,
            "stdout": stdout,
            "stderr": stderr,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        raise typer.Exit(code=_codigo_de_salida(ret, err_tipo, propagar_codigo))

    if stdout:
        console.print("[bold green]--- STDOUT ---[/bold green]")
        console.print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        err_console.print("[bold yellow]--- STDERR ---[/bold yellow]")
        err_console.print(f"[red]{stderr}[/red]", end="" if stderr.endswith("\n") else "\n")
    if err_tipo:
        err_console.print(f"\n[bold red]Terminado con señal / error: {err_tipo} ({t_ms:.1f} ms, CPU: {cpu_us if uso_medido else 'N/D'} μs, RSS: {rss_kb if uso_medido else 'N/D'} KB)[/bold red]")

    raise typer.Exit(code=_codigo_de_salida(ret, err_tipo, propagar_codigo))


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
        lines.append("| Caso | Estado | Retorno | Tiempo | CPU (μs) | RAM (KB) | Diagnóstico |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")
        for r in reporte.resultados:
            st = "✓ PASS" if r.paso else f"❌ FAIL ({r.error_tipo or 'Mismatch'})"
            diag = "OK" if r.paso else (r.diff_lineas[0].strip() if r.diff_lineas else r.stderr_obtenido[:40] or "Salida distinta")
            if r.hal_diagnostico:
                diag += f" | HAL: {r.hal_diagnostico}"
            lines.append(f"| `{r.nombre}` | **{st}** | `{r.codigo_retorno}` | {r.tiempo_ms:.1f} ms | {r.cpu_tiempo_us if r.uso_medido else 'N/D'} | {r.max_rss_kb if r.uso_medido else 'N/D'} | {diag} |")
        lines.append("")
    return "\n".join(lines)


@app.command("test")
@app.command("check")
def test_cmd(
    binario: Path = typer.Argument(..., help="Binario ejecutable a evaluar."),
    test_dir: Path = typer.Argument(..., help="Directorio con archivos .in y .out."),
    timeout: float = typer.Option(2.0, "--timeout", "-t", help="Timeout por caso en segundos."),
    memory: int = typer.Option(128, "--memory", "-m", help="Límite de memoria en MB."),
    adaptive_timeout: bool = typer.Option(False, "--adaptive-timeout", "-a", help="Ajustar timeout según tamaño de entrada."),
    no_hal: bool = typer.Option(False, "--no-hal", help="Desactivar diagnóstico con HAL."),
    side_by_side: bool = typer.Option(False, "--side-by-side", "-s", help="Mostrar diff lado a lado en fallos."),
    json_output: bool = typer.Option(False, "--json", help="Salida estructurada en JSON."),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", "-o", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
) -> None:
    """Ejecuta una suite completa de casos de prueba .in/.out y genera el reporte de evaluación."""
    casos = descubrir_casos_prueba(test_dir)
    if not casos:
        err_console.print(f"[red]Error:[/red] No se encontraron casos de prueba (.in/.out) en '{test_dir}'.")
        raise typer.Exit(code=2)

    reporte = evaluar_binario(
        binario=binario,
        casos=casos,
        timeout_segundos=timeout,
        memoria_mb=memory,
        timeout_adaptativo=adaptive_timeout,
        integrar_hal=not no_hal,
    )

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
    tabla.add_column("CPU (μs)", justify="right", style="dim")
    tabla.add_column("RAM (KB)", justify="right", style="dim")
    tabla.add_column("Detalle")

    for r in reporte.resultados:
        res_str = "[bold green]PASS[/bold green]" if r.paso else f"[bold red]FAIL ({r.error_tipo})[/bold red]"
        detalle = "Coincidencia exacta" if r.paso else (r.diff_lineas[0].strip() if r.diff_lineas else r.stderr_obtenido[:40])
        tabla.add_row(r.nombre, res_str, str(r.codigo_retorno), f"{r.tiempo_ms:.1f} ms", str(r.cpu_tiempo_us) if r.uso_medido else "N/D", str(r.max_rss_kb) if r.uso_medido else "N/D", detalle)

    console.print(tabla)

    # Mostrar diff lado a lado si se solicitó o si hubo fallos de diff
    for r in reporte.resultados:
        if not r.paso and r.diff_lado_a_lado and (side_by_side or r.error_tipo == "DIFF"):
            diff_table = Table(title=f"Discrepancia en caso '{r.nombre}' (Lado a Lado)")
            diff_table.add_column("Salida Esperada", style="green")
            diff_table.add_column("Salida Obtenida", style="red")
            for exp_l, obt_l in r.diff_lado_a_lado[:25]:
                diff_table.add_row(exp_l, obt_l)
            console.print(diff_table)

        if r.hal_diagnostico:
            console.print(Panel(
                f"[bold red]Diagnóstico Forense de HAL:[/bold red]\n{r.hal_diagnostico}",
                title=f"💥 Crash detectado en '{r.nombre}'",
                border_style="red",
            ))

    color_score = "green" if reporte.ok else "yellow" if reporte.porcentaje_aprobacion >= 60 else "red"
    console.print(Panel(
        f"Aprobados: [bold green]{reporte.casos_aprobados}/{reporte.total_casos}[/bold green] "
        f"([bold {color_score}]{reporte.porcentaje_aprobacion:.1f}%[/bold {color_score}]) · "
        f"Tiempo Total: [cyan]{reporte.tiempo_total_ms:.1f} ms[/cyan] · "
        f"CPU Total: [magenta]{reporte.cpu_tiempo_total_us} μs[/magenta] · "
        f"Pico RAM: [blue]{reporte.max_rss_pico_kb} KB[/blue]",
        title="Resumen de Evaluación",
        border_style=color_score,
    ))

    raise typer.Exit(code=0 if reporte.ok else 1)


@app.command("stress")
def stress_cmd(
    binario: Path = typer.Argument(..., help="Binario ejecutable a someter a prueba de estrés."),
    test_in: Path = typer.Argument(..., help="Archivo .in con datos de entrada o directorio de pruebas."),
    test_out: Optional[Path] = typer.Option(None, "--out", "-o", help="Archivo .out con salida esperada."),
    iterations: int = typer.Option(100, "--iterations", "-n", help="Cantidad de iteraciones consecutivas."),
    timeout: float = typer.Option(2.0, "--timeout", "-t", help="Timeout máximo por iteración en segundos."),
    memory: int = typer.Option(128, "--memory", "-m", help="Límite de memoria por iteración en MB."),
    json_output: bool = typer.Option(False, "--json", help="Emitir reporte en JSON."),
) -> None:
    """Ejecuta N repeticiones masivas para verificar estabilidad, memoria y evitar condiciones de carrera."""
    from nostromo.core.runner import normalizar_salida

    if test_in.is_file():
        stdin_texto = test_in.read_text(encoding="utf-8")
        expected_stdout = test_out.read_text(encoding="utf-8") if test_out and test_out.is_file() else None
    elif test_in.is_dir():
        casos = descubrir_casos_prueba(test_in)
        if not casos:
            err_console.print(f"[red]Error:[/red] No hay casos en '{test_in}'.")
            raise typer.Exit(code=2)
        stdin_texto = casos[0].stdin_texto
        expected_stdout = casos[0].stdout_esperado
    else:
        err_console.print(f"[red]Error:[/red] '{test_in}' no existe.")
        raise typer.Exit(code=2)

    exitos = 0
    fallos = 0
    tiempos_ms = []
    rss_lista = []
    codigos_retorno = {}

    for _ in range(iterations):
        res = ejecutar_aislado(binario=binario, stdin_texto=stdin_texto, timeout_segundos=timeout, memoria_mb=memory)
        ret, stdout, stderr, t_ms, err_tipo = res
        rss_kb = getattr(res, "max_rss_kb", 0)
        tiempos_ms.append(t_ms)
        rss_lista.append(rss_kb)
        codigos_retorno[ret] = codigos_retorno.get(ret, 0) + 1

        ok = (ret == 0)
        if expected_stdout is not None:
            ok = ok and (normalizar_salida(stdout) == normalizar_salida(expected_stdout))

        if ok:
            exitos += 1
        else:
            fallos += 1

    t_prom = sum(tiempos_ms) / len(tiempos_ms) if tiempos_ms else 0.0
    t_min = min(tiempos_ms) if tiempos_ms else 0.0
    t_max = max(tiempos_ms) if tiempos_ms else 0.0
    rss_inicial = rss_lista[0] if rss_lista else 0
    rss_final = rss_lista[-1] if rss_lista else 0
    leak_sospechoso = (rss_final > rss_inicial * 1.5 and (rss_final - rss_inicial) > 1024)

    reporte = {
        "binario": str(binario),
        "iteraciones": iterations,
        "exitos": exitos,
        "fallos": fallos,
        "tasa_exito_pct": round((exitos / iterations * 100.0) if iterations > 0 else 0.0, 2),
        "tiempo_promedio_ms": round(t_prom, 2),
        "tiempo_min_ms": round(t_min, 2),
        "tiempo_max_ms": round(t_max, 2),
        "rss_inicial_kb": rss_inicial,
        "rss_final_kb": rss_final,
        "posible_fuga_acumulativa": leak_sospechoso,
        "codigos_retorno": codigos_retorno,
    }

    if json_output:
        print(json.dumps(reporte, indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if fallos == 0 else 1)

    color = "green" if fallos == 0 else "red"
    tabla_stress = Table(title=f"Resultados de Prueba de Estrés ({iterations} iteraciones)")
    tabla_stress.add_column("Métrica", style="bold cyan")
    tabla_stress.add_column("Valor", style="yellow")
    tabla_stress.add_row("Iteraciones Exitosas", f"[green]{exitos}/{iterations}[/green]")
    tabla_stress.add_row("Iteraciones Fallidas", f"[{color}]{fallos}[/{color}]")
    tabla_stress.add_row("Tiempo Mín / Prom / Máx", f"{t_min:.1f} / {t_prom:.1f} / {t_max:.1f} ms")
    tabla_stress.add_row("Memoria RSS Inicial / Final", f"{rss_inicial} KB / {rss_final} KB")
    tabla_stress.add_row("Fuga Acumulativa", "[red]⚠️ Posible fuga detectada[/red]" if leak_sospechoso else "[green]✓ Estable[/green]")
    console.print(tabla_stress)
    raise typer.Exit(code=0 if fallos == 0 else 1)


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
