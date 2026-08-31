---
title: "Manual de Referencia: nostromo"
subtitle: "Nostromo — Sandbox de Ejecución Segura en Linux con Bubblewrap y Test Runner"
author: "Cátedra de Algoritmos y Programación"
date: "2026-08-31"
---

(manual-nostromo)=
# Nostromo — Sandbox de Ejecución Segura en Linux con Bubblewrap y Test Runner

````{abstract}
**Rol en el ecosistema:** Ejecución aislada y segura de binarios de estudiantes en contenedores ligeros de kernel (Bubblewrap / setrlimit), control de tiempo de CPU, memoria máxima y evaluación de casos de prueba .in/.out.
````

---

(manual-nostromo-proposito)=
## 1. Propósito y Filosofía Pedagógica

La herramienta **`nostromo`** forma parte del ecosistema oficial de software de la cátedra. Su diseño sigue principios pedagógicos rigurosos:

1. **Evidencia Técnica Directa**: Todo diagnóstico se fundamenta en la norma ISO C (C11/C23), en el modelo de memoria del sistema o en convenciones arquitectónicas formales.
2. **Acción Correctiva Concreta**: Cada advertencia incluye la prescripción técnica inmediata para resolver el defecto sin recurrir a conjeturas.
3. **Autonomía del Estudiante**: Facilita la autoevaluación local antes de la entrega final del trabajo práctico.
4. **Objetividad Docente**: Estandariza la corrección automática eliminando discrepancias subjetivas en la evaluación.

---

(manual-nostromo-instalacion)=
## 2. Instalación y Diagnóstico del Entorno

````{important}
Asegurate de contar con el compilador GCC/Clang y las librerías del sistema instaladas antes de ejecutar `nostromo`.
````

Para comprobar el estado de salud de tu entorno de trabajo y las dependencias auxiliares:

````{code-block} bash
# Comprobación de dependencias del sistema
nostromo doctor
````

Si se detecta la falta de alguna utilidad (como `gdb`, `valgrind`, `clang-format` o `typst`), el comando indicará el paquete exacto a instalar según tu distribución GNU/Linux o entorno MSYS2.

---

(manual-nostromo-comandos)=
## 3. Referencia Completa de Comandos CLI

A continuación se detallan los subcomandos principales disponibles en `nostromo`:

| Sintaxis del Comando | Descripción y Efecto |
| :--- | :--- |
| `nostromo run --binary ./bin/programa --testcases testcases/` | Evalúa la suite de pruebas .in/.out en sandbox aislado. |
| `nostromo exec --timeout 2s --mem 32M -- ./bin/programa` | Ejecuta un binario con cuotas estrictas de CPU y RAM. |
| `nostromo doctor` | Verifica capacidades no privilegiadas de Bubblewrap en el kernel. |
| `nostromo gen-testcases --binary ./bin/canon -i inputs/` | Genera los archivos .out canónicos esperados. |

````{tip}
Podés agregar el flag `--json` a la mayoría de los comandos para exportar resultados en formato estructurado o `--md` para generar reportes Markdown para el informe de entrega.
````

---

(manual-nostromo-tutorial)=
## 4. Tutorial Paso a Paso con Ejemplos Reales

### Caso de Estudio

Considerá el siguiente fragmento de código representativo:

````{code-block} c
:linenos:
// Programa de alumno evaluado bajo sandbox Nostromo
#include <stdio.h>

int main(void) {
    int a, b;
    if (scanf("%d %d", &a, &b) == 2) {
        printf("%d\n", a + b);
    }
    return 0;
}
````

### Ejecución de la Herramienta

Ejecutá el análisis desde tu terminal:

````{code-block} bash
nostromo run --binary ./bin/programa --testcases testcases/
````

### Salida Obtenida en Consola

````{code-block} text
EVALUACIÓN NOSTROMO SANDBOX:
 ✓ Testcase 01 (suma_positivos.in): PASSED (12 ms, 4.2 MB)
 ✓ Testcase 02 (suma_negativos.in): PASSED (10 ms, 4.1 MB)
 ✓ Testcase 03 (limite_maximo.in): PASSED (11 ms, 4.2 MB)
[✓] 3/3 casos de prueba aprobados (Sandbox: Bubblewrap bwrap).
````

````{note}
Prestá atención a la explicación pedagógica generada: la herramienta no solo señala la línea del problema, sino que explica la causa raíz y el impacto en memoria o arquitectura.
````

---

(manual-nostromo-ejercicios)=
## 5. Ejercicios Prácticos y Desafíos

Practicá el uso avanzado de **`nostromo`** resolviendo los siguientes ejercicios:

````{exercise} Desafío 1: Evaluación de Casos de Prueba en Sandbox
Correr una suite de 10 testcases sobre el ejecutable del TP.

**Instrucción de ejecución:**
```bash
nostromo run --binary ./bin/tp1 --testcases testcases/
```
````

````{solution} Desafío 1
```bash
nostromo run --binary ./bin/tp1 --testcases testcases/
# Verificá que la operación concluya exitosamente con código de salida 0.
```
````

````{exercise} Desafío 2: Detección de Lazos Infinitos (Timeout)
Verificar que el sandbox interrumpe procesos que superan 2 segundos.

**Instrucción de ejecución:**
```bash
nostromo exec --timeout 2s -- ./bin/bucle_infinito
```
````

````{solution} Desafío 2
```bash
nostromo exec --timeout 2s -- ./bin/bucle_infinito
# Revisá el archivo generado o el informe en terminal para confirmar la resolución del problema.
```
````

````{exercise} Desafío 3: Límite de Consumo de Memoria
Comprobar que un programa que solicita 500 MB es abortado con cuota de 32 MB.

**Instrucción de ejecución:**
```bash
nostromo exec --mem 32M -- ./bin/come_memoria
```
````

````{solution} Desafío 3
```bash
nostromo exec --mem 32M -- ./bin/come_memoria
# Comprobá que la salida confirme la ausencia de advertencias o errores pendientes.
```
````

---

(manual-nostromo-makefile)=
## 6. Integración en el Flujo de Trabajo y Makefile

Para incorporar `nostromo` de forma automática a tu flujo de desarrollo, agregá la siguiente regla en el `Makefile` de tu proyecto:

````{code-block} makefile
check-nostromo:
	@echo "=== Ejecutando verificación con nostromo ==="
	nostromo check src/ include/

.PHONY: check-nostromo
````

Ejecutá `make check-nostromo` antes de cada commit para asegurar que tu código conserve el estado de aprobación.
