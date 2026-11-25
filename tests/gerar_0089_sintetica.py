"""Gerador offline da fixture sintética 0089; nenhum dado observado de navegador."""

import base64
import hashlib
import json
import re
from pathlib import Path


def gerar():
    casos = [
        (
            "utf8",
            "<html>Ação</html>".encode(),
            "text/html; charset=utf-8",
            "Ação",
            True,
        ),
        (
            "meta",
            '<html><meta charset="utf-8">Ação</html>'.encode(),
            "text/html",
            "Ação",
            True,
        ),
        ("invalido", b"<html>\xf0\x9f\x92\xff</html>", "text/html", "", False),
        ("incompleto", b"<html>\xf0\x9f\x92", "text/html", "", False),
        ("ufffd", "<html>\ufffd</html>".encode(), "text/html", "\ufffd", True),
        (
            "bom",
            "<html>Ação</html>".encode("utf-16"),
            "text/html; charset=utf-8",
            "Ação",
            True,
        ),
        (
            "latin1",
            "<html>Ação</html>".encode("latin-1"),
            "text/html; charset=iso-8859-1",
            "Ação",
            True,
        ),
        (
            "cp1252",
            "<html>Ação €</html>".encode("cp1252"),
            "text/html; charset=windows-1252",
            "Ação €",
            True,
        ),
    ]
    dados = (
        json.dumps(
            [
                {
                    "nome": n,
                    "base64": base64.b64encode(b).decode("ascii"),
                    "content_type": ct,
                    "texto": t,
                    "aceito": ok,
                }
                for n, b, ct, t, ok in casos
            ],
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    raiz = Path(__file__).parent / "fixtures"
    arquivo = raiz / "0089_streaming_sintetico.json"
    arquivo.write_bytes(dados)
    manifesto = raiz / "FIXTURES.json"
    entrada = {
        "bytes": len(dados),
        "categoria": "sintetica",
        "file": arquivo.name,
        "gerador": "tests/gerar_0089_sintetica.py:gerar",
        "proposito": "0089 §2.4(11), §2.5(2): identidade de bytes e interpretação estrita offline",
        "sha256": hashlib.sha256(dados).hexdigest(),
    }
    # Preserva os bytes/terminadores das entradas históricas; só nossa entrada
    # sintética é gerada em UTF-8/LF. Idempotente, sem reformatar o manifesto.
    anterior = re.sub(
        rb'^ "0089_streaming_sintetico": \{.*?^ \},\r?\n',
        b"",
        manifesto.read_bytes(),
        flags=re.M | re.S,
    )
    item = (
        json.dumps(
            {"0089_streaming_sintetico": entrada},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )[2:-2]
        + ",\n"
    )
    inicio = anterior.index(b"\n") + 1
    manifesto.write_bytes(anterior[:inicio] + item.encode("utf-8") + anterior[inicio:])


if __name__ == "__main__":
    gerar()
