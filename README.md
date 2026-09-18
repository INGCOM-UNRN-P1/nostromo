# 📦 NOSTROMO — Sandbox de Ejecución y Test Runner en C

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
- CLI `nostromo`. Plugin registrado en `ripley.plugins` (`sandbox`). Consumido por `ripley` y `dredd`. Subcomando `nostromo doctor`.

---

## Uso Rápido

```bash
# 1. Ejecutar binario dentro del sandbox con límites
nostromo run ./programa --timeout 1.5 --memory 64

# 2. Evaluar suite de casos .in / .out
nostromo test ./programa ./testcases/

# 3. Salida estructurada JSON para evaluación desatendida
nostromo test ./programa ./testcases/ --json

# 4. Comprobar salud del sandbox (bwrap, límites)
nostromo doctor
```
