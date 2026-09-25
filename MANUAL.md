# Manual de Uso y Referencia Técnica: nostromo

> **NOSTROMO** — Sandbox de ejecución aislada con Bubblewrap y evaluador de casos de prueba .in/.out
> **Versión:** `0.1.0` · **CLI principal:** `nostromo` · **Plugin Ripley:** `sandbox`

---

## 1. Arquitectura y Propósito Pedagógico

`nostromo` forma parte del ecosistema de herramientas de la cátedra de Programación 1 (UNRN). Su objetivo central es resolver de forma modular, determinista y automatizada las tareas asociadas a su dominio específico dentro del ciclo de desarrollo, evaluación y aprendizaje de software en C.

### Alcance Funcional (Qué cubre)
- Aislamiento seguro en tiempo de ejecución (Sandbox) de programas compilados en C.
- Contención no privilegiada mediante Bubblewrap (`bwrap`) con aislamiento de sistema de archivos, red y procesos, y degradación controlada a POSIX `setrlimit`.
- Imposición de límites de tiempo de pared (`--timeout`), tiempo de CPU (el timeout redondeado hacia arriba más un segundo, que corta también a los programas con varios hilos), memoria máxima (`--memory`) y tamaño de cada archivo escrito, salida estándar incluida (16 MB).
- Evaluación desatendida y automática de suites de casos de prueba de entrada/salida (`.in / .out`).
- Captura y reporte estructurado de estadísticas de consumo (`rusage`: tiempo de usuario y de sistema, memoria pico) **del programa evaluado**, también bajo `bwrap`.

### Límites de Responsabilidad y Delegación (Qué no cubre)
- Compilación de código fuente C (delega en `daedalus`).
- Análisis forense post-mortem con GDB (delega en `hal`).
- Calificación de la cohorte docente y almacenamiento de notas (delega en `dredd`).

### Principios de Diseño
- **Enfoque Pedagógico:** Diagnósticos y mensajes en español rioplatense orientados a facilitar la comprensión de errores conceptuales.
- **Salida Estructurada Dual:** Soporte nativo para visualización enriquecida en terminal (Rich) y salida parseable para orquestadores (`--json`).
- **Integración Contractual:** Capacidad de emitir secciones de reporte para `dredd` (`dredd-section`) y actuar como satélite orquestado por `ripley`.
- **Idempotencia y Robustez:** Validación de precondiciones y comandos de autodiagnóstico (`doctor`) para verificación del entorno.

---

## 2. Instalación y Requisitos

### Requisitos del Sistema
- **Python:** `>= 3.10` (recomendado Python 3.11 o 3.12).
- **Gestor de paquetes:** [`uv`](https://github.com/astral-sh/uv) (entorno estándar de cátedra).
- **Toolchain C (si aplica):** GCC / Clang, Make, GDB y bibliotecas estándar de desarrollo.

### Instalación en el Entorno de Usuario
Para instalar la herramienta de forma global y aislada en el sistema mediante `uv tool`:
```bash
uv tool install --editable /home/mrtin/dev/tools/nostromo
```

### Verificación de Instalación
Ejecutá el comando `doctor` para constatar que todas las dependencias y binarios requeridos estén presentes y operativos:
```bash
nostromo doctor
```

---

## 3. Guía Integral de Comandos (CLI)

| Comando | Descripción Breve |
| :--- | :--- |
| [`nostromo run`](#run) | Ejecuta un binario dentro del sandbox con límites estrictos de CPU y memoria. |
| [`nostromo check`](#check) | Ejecuta una suite completa de casos de prueba .in/.out y genera el reporte de evaluación. |
| [`nostromo test`](#test) | Ejecuta una suite completa de casos de prueba .in/.out y genera el reporte de evaluación. |
| [`nostromo stress`](#stress) | Ejecuta N repeticiones masivas para verificar estabilidad, memoria y evitar condiciones de carrera. |
| [`nostromo doctor`](#doctor) | Verifica el aislamiento del sandbox (Bubblewrap) y sale 1 si no está operativo. |
| [`nostromo report`](#report) | Genera directamente la sección de reporte Markdown de NOSTROMO para Dredd. |

### `nostromo run`

Ejecuta un binario dentro del sandbox con límites estrictos de CPU y memoria.

Sale con 0 si el programa terminó bien, 1 si falló (retorno distinto de cero,
señal o timeout) y 2 si no se pudo ejecutar; el código del programa está en el
JSON (`codigo_retorno`) o se obtiene con --exit-code.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `binario` | `Path` | Binario ejecutable a correr. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--args` | `Optional[List[str]]` | `None` | Argumentos a pasar al binario. |
| `--stdin`, `-i` | `Optional[str]` | `None` | Datos enviados por stdin. |
| `--timeout`, `-t` | `float` | `2.0` | Timeout máximo en segundos. |
| `--memory`, `-m` | `int` | `128` | Límite de memoria en Megabytes. |
| `--json` | `bool` | `False` | Salida en JSON. |
| `--exit-code` | `bool` | `False` | Salir con el código del programa (señal = 128+n) en vez de 0/1/2. |

#### Ejemplo de Invocación
```bash
nostromo run <binario>
```

### `nostromo check`

Ejecuta una suite completa de casos de prueba .in/.out y genera el reporte de evaluación.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `binario` | `Path` | Binario ejecutable a evaluar. |
| `test_dir` | `Path` | Directorio con archivos .in y .out. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--timeout`, `-t` | `float` | `2.0` | Timeout por caso en segundos. |
| `--memory`, `-m` | `int` | `128` | Límite de memoria en MB. |
| `--adaptive-timeout`, `-a` | `bool` | `False` | Ajustar timeout según tamaño de entrada. |
| `--no-hal` | `bool` | `False` | Desactivar diagnóstico con HAL. |
| `--side-by-side`, `-s` | `bool` | `False` | Mostrar diff lado a lado en fallos. |
| `--json` | `bool` | `False` | Salida estructurada en JSON. |
| `--md`, `--output-md`, `-o` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |

#### Ejemplo de Invocación
```bash
nostromo check <binario> <test_dir>
```

### `nostromo test`

Ejecuta una suite completa de casos de prueba .in/.out y genera el reporte de evaluación.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `binario` | `Path` | Binario ejecutable a evaluar. |
| `test_dir` | `Path` | Directorio con archivos .in y .out. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--timeout`, `-t` | `float` | `2.0` | Timeout por caso en segundos. |
| `--memory`, `-m` | `int` | `128` | Límite de memoria en MB. |
| `--adaptive-timeout`, `-a` | `bool` | `False` | Ajustar timeout según tamaño de entrada. |
| `--no-hal` | `bool` | `False` | Desactivar diagnóstico con HAL. |
| `--side-by-side`, `-s` | `bool` | `False` | Mostrar diff lado a lado en fallos. |
| `--json` | `bool` | `False` | Salida estructurada en JSON. |
| `--md`, `--output-md`, `-o` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |

#### Ejemplo de Invocación
```bash
nostromo test <binario> <test_dir>
```

### `nostromo stress`

Ejecuta N repeticiones masivas para verificar estabilidad, memoria y evitar condiciones de carrera.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `binario` | `Path` | Binario ejecutable a someter a prueba de estrés. |
| `test_in` | `Path` | Archivo .in con datos de entrada o directorio de pruebas. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--out`, `-o` | `Optional[Path]` | `None` | Archivo .out con salida esperada. |
| `--iterations`, `-n` | `int` | `100` | Cantidad de iteraciones consecutivas. |
| `--timeout`, `-t` | `float` | `2.0` | Timeout máximo por iteración en segundos. |
| `--memory`, `-m` | `int` | `128` | Límite de memoria por iteración en MB. |
| `--json` | `bool` | `False` | Emitir reporte en JSON. |

#### Ejemplo de Invocación
```bash
nostromo stress <binario> <test_in>
```

### `nostromo doctor`

Verifica el aislamiento del sandbox (Bubblewrap) y sale 1 si no está operativo.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Diagnóstico en JSON. |

#### Ejemplo de Invocación
```bash
nostromo doctor
```

### `nostromo report`

Genera directamente la sección de reporte Markdown de NOSTROMO para Dredd.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `binario` | `Path` | Binario ejecutable a evaluar. |
| `test_dir` | `Path` | Directorio con archivos .in y .out. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--output`, `-o` | `Optional[Path]` | `None` | Ruta de destino del archivo Markdown. |

#### Ejemplo de Invocación
```bash
nostromo report <binario> <test_dir>
```

---

## 4. Formatos de Salida e Integración con el Ecosistema

### Modo Interactivo / Terminal (Rich)
Por defecto, la herramienta renderiza paneles, árboles y tablas estilizadas para facilitar la lectura del estudiante y docente en terminales modernas con soporte ANSI.

### Modo Estructurado JSON (`--json`)
Para integración con pipelines de CI/CD, scripts de automatización u orquestadores externos, la opción `--json` emite un documento JSON estricto por la salida estándar (`stdout`), dirigiendo cualquier mensaje de logging a `stderr`:
```bash
nostromo run --json
```

### Integración con Dredd (`dredd-section`)
Cuando la herramienta genera reportes de evaluación para entregas de alumnos, produce una sección Markdown estandarizada conforme al contrato de integración de Dredd (v1.0.0):
```markdown
<!-- dredd-section: nostromo, tool=nostromo, version=0.1.0, status=ok -->
```
Este encabezado garantiza la agregación determinista de los hallazgos en la rúbrica docente.

### Integración con Ripley
`nostromo` está registrada en el catálogo de plugins satélites de Ripley (`SATELLITE_CATALOG`). Puede invocarse directamente a través del motor de evaluación de Ripley configurando el análisis en `ripley.toml`.

---

## 5. Diagnóstico y Códigos de Salida

### Códigos de Retorno (`exit code`)
| Código | Significado |
| :---: | :--- |
| `0` | Ejecución exitosa sin hallazgos críticos ni errores de sintaxis. |
| `1` | Hallazgos pedagógicos detectados, infracción de reglas o advertencias activas. |
| `2` | Error de sintaxis en argumentos CLI o archivo fuente no encontrado. |
| `>2` | Error no recuperable del sistema, fallo de memoria o excepción interna. |

### Diagnóstico del Entorno (`doctor`)
Ante comportamientos inesperados, verificá el estado operativo con:
```bash
nostromo doctor
```
Comprueba la presencia de las dependencias requeridas y la integridad de los componentes del paquete.