"""Parsers em processo separado com timeout; memoria limitada pelo hospedeiro."""
from __future__ import annotations
from dataclasses import asdict
import json
import subprocess
import sys
from freoa_verifica.parsers.model import Issue, ParsedDocument, document_from_dict

_PROFILES = ("planalto", "cvm_docx", "bcb_json")

def _failure(profile: str, detail: str) -> ParsedDocument:
    return ParsedDocument(profile, "0", "", None, "", issues=[
        Issue("TRUNCATED", None, detail, blocking_scope="document"),
    ])

def parse_isolated(profile: str, data: bytes | str, timeout: float) -> ParsedDocument:
    """Executa em filho; timeout, falha ou saida invalida geram quarentena."""
    if profile not in _PROFILES:
        return _failure(profile, "perfil desconhecido")
    raw = data.encode("utf-8") if isinstance(data, str) else data
    with subprocess.Popen(
        [sys.executable, "-m", "freoa_verifica.parsers.isolated", profile],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as proc:
        try:
            output, _ = proc.communicate(raw, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return _failure(profile, f"parse_isolated excedeu timeout={timeout}s")
        if proc.returncode != 0:
            return _failure(profile, "parse_isolated falhou no filho")
    try:
        return document_from_dict(json.loads(output))
    except (ValueError, TypeError, KeyError):
        return _failure(profile, "parse_isolated sem resultado valido do filho")

def _main() -> None:
    from freoa_verifica.parsers.planalto import parse_planalto
    from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
    from freoa_verifica.parsers.bcb_json import parse_bcb_json
    parsers = dict(zip(_PROFILES, (parse_planalto, parse_cvm_docx, parse_bcb_json)))
    document = parsers[sys.argv[1]](sys.stdin.buffer.read())
    sys.stdout.buffer.write(json.dumps(asdict(document), ensure_ascii=False).encode("utf-8"))

if __name__ == "__main__":
    _main()
