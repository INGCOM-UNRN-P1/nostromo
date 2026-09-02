# 📦 NOSTROMO — Sandbox de Ejecución y Test Runner en C

NOSTROMO es un entorno aislado de ejecución (sandbox basado en `Bubblewrap` / `setrlimit`) y evaluador automático de casos de prueba (`.in` / `.out`) con control estricto de timeouts, límites de memoria y reporte de diffs unificados.

---

## 🎯 Alcance

### Qué cubre
- Aislamiento seguro en tiempo de ejecución (Sandbox) de programas compilados en C.
- Contención no privilegiada mediante Bubblewrap (`bwrap`) con aislamiento de sistema de archivos, red y procesos, y degradación controlada a POSIX `setrlimit`.
- Imposición estricta de límites de tiempo de CPU (timeout), memoria RAM máxima y tamaño de archivos de salida.
- Evaluación desatendida y automática de suites de casos de prueba de entrada/salida (`.in / .out`).
- Captura y reporte estructurado de estadísticas de consumo (`rusage`: tiempo de usuario, tiempo de sistema, memoria pico).

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
