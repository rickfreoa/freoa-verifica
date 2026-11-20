"""Fixtures SINTÉTICAS br/zstd: blocos sem compressão, sem biblioteca adicional.

Gerador determinista para o harness local da §3.1; não é captura de fonte.
"""

import hashlib
import json
import re
from pathlib import Path

BODY = b"<html><body>Art. 1. Sintetico.</body></html>"


def gerar():
    n = len(BODY)
    assert 0 < n < 256
    return {
        # WBITS=22; meta-bloco não final de n bytes, sem compressão; fim vazio.
        "br": (0xB | ((n - 1) << 7) | (1 << 23)).to_bytes(3, "little") + BODY + b"\x03",
        # Magic Zstandard, single segment, tamanho de 1 byte, bloco raw final.
        "zstd": b"\x28\xb5\x2f\xfd\x20"
        + bytes([n])
        + ((n << 3) | 1).to_bytes(3, "little")
        + BODY,
    }


if __name__ == "__main__":
    raiz = Path(__file__).parent / "fixtures"
    path = raiz / "FIXTURES.json"
    texto = path.read_bytes().decode("utf-8")
    novas = {}
    for encoding, body in gerar().items():
        nome = f"0089_wire_{encoding}"
        arquivo = nome + ".bin"
        (raiz / arquivo).write_bytes(body)
        novas[nome] = {
            "file": arquivo,
            "categoria": "sintetica",
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "gerador": "tests/gerar_0089_wire.py:gerar",
            "proposito": f"0089 §3.1: resposta HTTPS local Content-Encoding {encoding}; bloco raw sintético",
        }
        texto = re.sub(r'(?ms)^ "' + nome + r'": \{.*?^ \},?\r?\n', "", texto)
    # Preserva os bytes e os finais de linha de TODAS as entradas anteriores.
    # O manifesto legado mistura CRLF/LF e está marcado -text no Git.
    bloco = json.dumps(novas, ensure_ascii=False, indent=1)[2:-2] + ",\n"
    inicio = re.search(r'(?m)^ "', texto).start()
    path.write_bytes((texto[:inicio] + bloco + texto[inicio:]).encode("utf-8"))
