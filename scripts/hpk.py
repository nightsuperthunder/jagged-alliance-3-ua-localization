"""Читання архівів .hpk рушія Haemimont (JA3): заголовок BPUL, файли стиснуті блоками ZSTD.

  python scripts/hpk.py <архів.hpk>                 # список файлів
  python scripts/hpk.py <архів.hpk> <файл> <куди>   # витягти один файл

Потрібен Python 3.14+ (compression.zstd у стандартній бібліотеці) — нічого встановлювати не треба.
"""
import struct
import sys
import zlib


def _unchunk(buf):
    """Файл усередині архіву: або сирий, або 'ZSTD' + розмір + розмір блоку + зміщення блоків."""
    magic = buf[:4]
    if magic not in (b"ZSTD", b"ZLIB"):
        return buf
    total, chunk, first = struct.unpack_from("<III", buf, 4)
    n = (first - 12) // 4
    offs = list(struct.unpack_from(f"<{n}I", buf, 12)) + [len(buf)]
    out = bytearray()
    for i in range(n):
        part = buf[offs[i]:offs[i + 1]]
        if len(part) == min(chunk, total - len(out)):
            out += part  # блок не стискався
        elif magic == b"ZSTD":
            from compression import zstd
            out += zstd.decompress(part)
        else:
            out += zlib.decompress(part)
    return bytes(out)


class Hpk:
    def __init__(self, path):
        self.f = open(path, "rb")
        head = self.f.read(36)
        if head[:4] != b"BPUL":
            raise ValueError(f"{path}: не hpk-архів")
        fs_off, fs_len = struct.unpack_from("<II", head, 28)
        table = _unchunk(self._raw(fs_off, fs_len))
        self.frags = [struct.unpack_from("<II", table, i) for i in range(0, len(table), 8)]
        self.files = {}  # шлях -> номер фрагмента
        self._walk(0, "")

    def _raw(self, off, size):
        self.f.seek(off)
        return self.f.read(size)

    def _walk(self, idx, prefix):
        data = self._raw(*self.frags[idx])
        p = 0
        while p < len(data):
            frag, flags, nlen = struct.unpack_from("<IIH", data, p)
            name = data[p + 10:p + 10 + nlen].decode("utf-8")
            p += 10 + nlen
            if flags & 1:
                self._walk(frag - 1, prefix + name + "/")
            else:
                self.files[prefix + name] = frag - 1

    def read(self, name):
        return _unchunk(self._raw(*self.frags[self.files[name]]))


if __name__ == "__main__":
    h = Hpk(sys.argv[1])
    if len(sys.argv) == 4:
        with open(sys.argv[3], "wb") as out:
            out.write(h.read(sys.argv[2]))
    else:
        for n, i in h.files.items():
            print(f"{h.frags[i][1]:>10}  {n}")
