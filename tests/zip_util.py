"""ZIP escrito à mão para testar divergências entre cabeçalho local e diretório central e as recusas da
disposição estrita (decisão 0044). Os geradores de ZIP64 só servem aos casos de recusa: o leitor não aceita ZIP64."""

from __future__ import annotations

import struct
import zipfile
import zlib


def zip_manual(entradas, *, local=None, central=None, descritor=None, z64_local=None, z64_central=False,
               z64_central_valores=None, z64_central_sentinelas=None,
               metodo=zipfile.ZIP_STORED):
    """ZIP escrito à mão. `local`/`central`: sobrescritas (flags, metodo, crc, comp, tam) de todas as entradas.
    `descritor`: None ou (assinatura, crc, comp, tam, largura); None nos valores = o correto; ativa o bit 3.
    `z64_local`: (tam, comp) do extra ZIP64 do local, ou None. `z64_central`: central com sentinela e extra.
    `z64_central_valores`: valores (Q) do extra ZIP64 central, no lugar do extra calculado.
    `z64_central_sentinelas`: subconjunto de {"tam", "comp"} cujo campo comum recebe a sentinela 0xFFFFFFFF."""
    corpo, cds, off = bytearray(), bytearray(), 0
    for nome, dado in entradas.items():
        nome_b = nome.encode("ascii")
        comp = dado if metodo == zipfile.ZIP_STORED else zlib.compress(dado)[2:-4]
        crc = zlib.crc32(dado) & 0xFFFFFFFF
        base = {"flags": 0x8 if descritor else 0, "metodo": metodo, "crc": crc, "comp": len(comp), "tam": len(dado)}
        l, c = {**base, **(local or {})}, {**base, **(central or {})}
        extra_l = b""
        if z64_local is not None:
            extra_l = struct.pack("<HHQQ", 1, 16, *z64_local)
            l["comp"] = l["tam"] = 0xFFFFFFFF
        zero = bool(descritor)
        cab = struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 45, l["flags"], l["metodo"], 0, 0x21,
                          0 if zero else l["crc"], 0 if zero else l["comp"], 0 if zero else l["tam"],
                          len(nome_b), len(extra_l))
        bloco = cab + nome_b + extra_l + comp
        if descritor:
            ass, d_crc, d_comp, d_tam, larg = descritor
            vals = (crc if d_crc is None else d_crc, len(comp) if d_comp is None else d_comp,
                    len(dado) if d_tam is None else d_tam)
            bloco += (b"PK\x07\x08" if ass else b"") + struct.pack("<I" + ("QQ" if larg == 8 else "II"), *vals)
        extra_c, c_comp, c_tam = b"", c["comp"], c["tam"]
        if z64_central_valores is not None:
            extra_c = struct.pack(f"<HH{len(z64_central_valores)}Q", 1, 8 * len(z64_central_valores), *z64_central_valores)
        if z64_central_sentinelas:
            c_tam = 0xFFFFFFFF if "tam" in z64_central_sentinelas else c_tam
            c_comp = 0xFFFFFFFF if "comp" in z64_central_sentinelas else c_comp
        if z64_central:
            if z64_central_valores is None:
                extra_c = struct.pack("<HHQQ", 1, 16, c["tam"], c["comp"])
            c_comp = c_tam = 0xFFFFFFFF
        cds += struct.pack("<4sHHHHHHIIIHHHHHII", b"PK\x01\x02", 45, 45, c["flags"], c["metodo"], 0, 0x21, c["crc"],
                           c_comp, c_tam, len(nome_b), len(extra_c), 0, 0, 0, 0, off) + nome_b + extra_c
        corpo += bloco
        off += len(bloco)
    fim = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, len(entradas), len(entradas), len(cds), off, 0)
    return bytes(corpo + cds + fim)
