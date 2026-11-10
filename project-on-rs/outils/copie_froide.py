"""Copie un fichier sans passer par le cache de Windows (FILE_FLAG_NO_BUFFERING).

La première lecture de la copie se fait donc depuis le disque, comme au premier lancement d'un
culte : c'est ce qui permet de comparer la 2.8 et la 3.0 « à froid » sans redémarrer le poste.

    python outils/copie_froide.py <source> <copie>
"""

import ctypes
import os
import sys
from ctypes import wintypes

GENERIC_WRITE = 0x40000000
CREATE_ALWAYS = 2
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_WRITE_THROUGH = 0x80000000
MEM_COMMIT_RESERVE = 0x3000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
SECTOR = 4096
CHUNK = 4 * 1024 * 1024


def main(source: str, target: str) -> None:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.VirtualAlloc.restype = ctypes.c_void_p
    k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
    k32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
    k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    size = os.path.getsize(source)
    handle = k32.CreateFileW(target, GENERIC_WRITE, 0, None, CREATE_ALWAYS,
                             FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise OSError(ctypes.get_last_error(), "CreateFileW")
    # Un tampon aligné sur la page : obligatoire sans cache.
    buffer = k32.VirtualAlloc(None, CHUNK, MEM_COMMIT_RESERVE, PAGE_READWRITE)
    try:
        with open(source, "rb", buffering=0) as stream:
            while data := stream.read(CHUNK):
                padded = (len(data) + SECTOR - 1) // SECTOR * SECTOR
                ctypes.memmove(buffer, data, len(data))
                ctypes.memset(buffer + len(data), 0, padded - len(data))
                written = wintypes.DWORD()
                if not k32.WriteFile(handle, buffer, padded, ctypes.byref(written), None):
                    raise OSError(ctypes.get_last_error(), "WriteFile")
    finally:
        k32.CloseHandle(handle)
        k32.VirtualFree(buffer, 0, MEM_RELEASE)
    if size % SECTOR:
        with open(target, "r+b") as stream:
            stream.truncate(size)
    print(f"{size / 1e6:.0f} Mo copiés sans cache : {target}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
