"""Filtro seccomp sin red para el perfil de examen (QoL #747).

`bwrap --unshare-net` deja al programa sin interfaces de red, pero `socket()` igual funciona (y en
los runners de CI sin CAP_NET_ADMIN ni siquiera se puede separar la red). Este filtro hace que
`socket()` falle con EACCES para toda familia que no sea AF_UNIX, y también `io_uring_setup`, que
permite abrir sockets sin pasar por la syscall `socket`. Las syscalls de otra arquitectura (las de
32 bits en un kernel de 64, el ABI x32) se rechazan enteras: por ahí se podría esquivar el filtro.

Es BPF clásico, el formato que `bwrap --seccomp FD` espera (el de `seccomp_export_bpf`): una
secuencia de `struct sock_filter {u16 code; u8 jt; u8 jf; u32 k;}` en el orden de bytes nativo.
"""

from __future__ import annotations

import errno
import platform
import struct
import sys
from typing import Dict, List, Optional, Tuple, Union

# Instrucciones de BPF clásico que se usan
_LD_W_ABS = 0x20  # BPF_LD | BPF_W | BPF_ABS
_JEQ_K = 0x15  # BPF_JMP | BPF_JEQ | BPF_K
_JGE_K = 0x35  # BPF_JMP | BPF_JGE | BPF_K
_RET_K = 0x06  # BPF_RET | BPF_K

SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000

# Desplazamientos en `struct seccomp_data`: nr (int), arch (u32), ip (u64), args[6] (u64).
_NR, _ARCH, _ARG0 = 0, 4, 16
_ARG0_ALTO = 20
AF_UNIX = 1
_X32 = 0x40000000

# arquitectura de platform.machine() → (AUDIT_ARCH, socket, io_uring_setup, tiene ABI x32)
ARQUITECTURAS: Dict[str, Tuple[int, int, int, bool]] = {
    "x86_64": (0xC000003E, 41, 425, True),
    "amd64": (0xC000003E, 41, 425, True),
    "aarch64": (0xC00000B7, 198, 425, False),
    "arm64": (0xC00000B7, 198, 425, False),
}

Instruccion = Tuple[int, Union[int, str], Union[int, str], int]


def _ensamblar(programa: List[Tuple[Optional[str], Instruccion]]) -> bytes:
    """Resuelve los saltos a etiquetas (relativos a la instrucción siguiente) y empaqueta."""
    etiquetas = {nombre: i for i, (nombre, _) in enumerate(programa) if nombre}
    orden = "<" if sys.byteorder == "little" else ">"
    salida = b""

    def salto(destino: Union[int, str], desde: int) -> int:
        if isinstance(destino, int):
            return destino
        desplazamiento = etiquetas[destino] - desde - 1
        assert 0 <= desplazamiento < 256, destino
        return desplazamiento

    for i, (_, (codigo, jt, jf, k)) in enumerate(programa):
        salida += struct.pack(orden + "HBBI", codigo, salto(jt, i), salto(jf, i), k)
    return salida


def filtro_sin_red(maquina: Optional[str] = None) -> Optional[bytes]:
    """El programa BPF para esta arquitectura (None si no está soportada: el examen no corre)."""
    datos = ARQUITECTURAS.get((maquina or platform.machine()).lower())
    if datos is None:
        return None
    arch, nr_socket, nr_io_uring, x32 = datos
    deny = SECCOMP_RET_ERRNO | errno.EACCES
    programa: List[Tuple[Optional[str], Instruccion]] = [
        (None, (_LD_W_ABS, 0, 0, _ARCH)),
        (None, (_JEQ_K, 0, "denegar", arch)),
        (None, (_LD_W_ABS, 0, 0, _NR)),
    ]
    if x32:
        programa.append((None, (_JGE_K, "denegar", 0, _X32)))
    programa += [
        (None, (_JEQ_K, "denegar", 0, nr_io_uring)),
        (None, (_JEQ_K, 0, "permitir", nr_socket)),
        # socket(dominio, …): sólo AF_UNIX (los 32 bits altos del argumento tienen que ser 0).
        (None, (_LD_W_ABS, 0, 0, _ARG0_ALTO if sys.byteorder == "little" else _ARG0)),
        (None, (_JEQ_K, 0, "denegar", 0)),
        (None, (_LD_W_ABS, 0, 0, _ARG0 if sys.byteorder == "little" else _ARG0_ALTO)),
        (None, (_JEQ_K, "permitir", "denegar", AF_UNIX)),
        ("permitir", (_RET_K, 0, 0, SECCOMP_RET_ALLOW)),
        ("denegar", (_RET_K, 0, 0, deny)),
    ]
    return _ensamblar(programa)
