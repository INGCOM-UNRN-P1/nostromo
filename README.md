# 📦 NOSTROMO — Sandbox de Ejecución y Test Runner en C

> 📖 **Manual de Usuario:** Para una guía exhaustiva de comandos, banderas, arquitectura y ejemplos, consultá el [Manual de Uso](MANUAL.md).

NOSTROMO es un entorno aislado de ejecución (sandbox basado en `Bubblewrap` / `setrlimit`) y evaluador automático de casos de prueba (`.in` / `.out`) con control estricto de timeouts, límites de memoria y reporte de diffs unificados.

---

## 🎯 Alcance

### Qué cubre
- Aislamiento seguro en tiempo de ejecución (Sandbox) de programas compilados en C.
- Contención no privilegiada mediante Bubblewrap (`bwrap`) con aislamiento de sistema de archivos, red y procesos, y degradación controlada a POSIX `setrlimit`.
- Imposición de límites de tiempo de pared (`--timeout`), tiempo de CPU (el timeout redondeado hacia arriba más un segundo, que corta también a los programas con varios hilos), memoria máxima (`--memory`) y tamaño de cada archivo escrito, salida estándar incluida (16 MB).
- Evaluación desatendida y automática de suites de casos de prueba de entrada/salida (`.in / .out`).
- Captura y reporte estructurado de estadísticas de consumo (`rusage`: tiempo de usuario y de sistema, memoria pico) **del programa evaluado**, también bajo `bwrap`.

### Qué no cubre (Límites y Delegación)
- Compilación de código fuente C (delega en `daedalus`).
- Análisis forense post-mortem con GDB (delega en `hal`).
- Calificación de la cohorte docente y almacenamiento de notas (delega en `dredd`).

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Linux con soporte de user namespaces (`bwrap`) o fallback a llamadas POSIX `setrlimit`. Python >= 3.10.

### Dependencias Externas y Binarios
- `bwrap` (recomendado para aislamiento fuerte).
- `python3` del sistema en `/usr/bin` (o `/bin`, `/usr/local/bin`): bajo `bwrap` corre un pequeño lanzador que mide el consumo real del programa. Sin él la ejecución sigue funcionando, pero el consumo se informa como `N/D` en lugar de mostrar el del sandbox.

### Integración en el Ecosistema
- CLI `nostromo`. Plugin registrado en `ripley.plugins` (`sandbox`). Consumido por `ripley` (invoca `nostromo check <binario> <tests> --json` desde su catálogo de satélites) y por `dredd`, que importa `nostromo.core.sandbox.ejecutar_aislado` como motor de aislamiento y cae a su propio sandbox si `nostromo` no está instalado. Subcomando `nostromo doctor`.

---

## Uso Rápido

```bash
# 1. Ejecutar binario dentro del sandbox con límites
nostromo run ./programa --timeout 1.5 --memory 64

# 2. Evaluar suite de casos .in / .out
nostromo test ./programa ./testcases/

# 3. Salida estructurada JSON para evaluación desatendida
nostromo test ./programa ./testcases/ --json

# 4. Prueba de estrés: N ejecuciones consecutivas (estabilidad, tiempos y fuga de memoria)
nostromo stress ./programa ./testcases/caso_1.in --out ./testcases/caso_1.out -n 50

# 5. Sección de reporte Markdown lista para fusionar en Dredd
nostromo report ./programa ./testcases/ -o reporte_nostromo.md

# 6. Comprobar el sandbox (bwrap operativo, python3 para medir consumo); sale 1 si falla
nostromo doctor
```

`nostromo check` es un alias de `nostromo test`. Los comandos `run`, `test`/`check`, `stress`, `report` y `doctor` son todos los que existen; `nostromo --help` los lista.
