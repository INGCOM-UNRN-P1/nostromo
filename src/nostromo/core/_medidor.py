"""Lanzador que corre DENTRO del sandbox: ejecuta el programa como hijo y registra su uso de recursos.

Bajo bwrap el programa evaluado vive en un namespace de PIDs propio y su
`rusage` no llega al proceso que lo lanzó: se medía al propio bwrap (9 MB y 3 ms
para un programa que reserva 80 MB). Acá el programa es hijo directo de este
proceso, así que `wait4` sí informa SU consumo.

Uso: python3 -S _medidor.py <archivo_de_medicion> <memoria_bytes> <programa> [args...]
Escribe "<utime> <stime> <maxrss_kb>" en el archivo y sale con el código del
programa (128+n si murió por la señal n, igual que bwrap).
"""

import os
import resource
import signal
import sys


def _es_binario_asan(programa: str) -> bool:
    try:
        with open(programa, "rb") as f:
            bloque = f.read(512 * 1024)
            if b"libasan" in bloque or b"__asan" in bloque:
                return True
            f.seek(0, os.SEEK_END)
            tamano = f.tell()
            if tamano > 512 * 1024:
                f.seek(max(0, tamano - 64 * 1024))
                if b"libasan" in f.read() or b"__asan" in f.read():
                    return True
    except Exception:
        pass
    return False


def main() -> int:
    destino, memoria, programa, *args = sys.argv[1:]
    limite = int(memoria)
    pid = os.fork()
    if pid == 0:
        # Python ignora SIGPIPE y SIGXFSZ al arrancar y esa disposición sobrevive a
        # `exec`: sin restaurarlas, el programa evaluado no moriría por escribir
        # en un pipe cerrado ni por pasarse del límite de tamaño de archivo.
        for senal in (signal.SIGPIPE, signal.SIGXFSZ):
            signal.signal(senal, signal.SIG_DFL)
        # Los límites de memoria se aplican acá y no al lanzador: contando el
        # intérprete de este script, un límite chico impediría hasta arrancar.
        # Si el binario usa ASan, RLIMIT_AS rompería la reserva de memoria virtual.
        recursos = [resource.RLIMIT_DATA]
        if not _es_binario_asan(programa):
            recursos.append(resource.RLIMIT_AS)
        for recurso in recursos:
            try:
                resource.setrlimit(recurso, (limite, limite))
            except (ValueError, OSError):
                pass
        try:
            os.execv(programa, [programa, *args])
        finally:
            os._exit(127)

    _, estado, uso = os.wait4(pid, 0)
    with open(destino, "w") as f:
        f.write(f"{uso.ru_utime!r} {uso.ru_stime!r} {uso.ru_maxrss}\n")
    if os.WIFSIGNALED(estado):
        return 128 + os.WTERMSIG(estado)
    return os.WEXITSTATUS(estado)


if __name__ == "__main__":
    sys.exit(main())
