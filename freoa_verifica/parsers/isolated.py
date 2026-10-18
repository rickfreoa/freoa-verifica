"""Parsers em processo separado com timeout; memoria limitada pelo hospedeiro."""
from __future__ import annotations
from dataclasses import asdict
import json
import subprocess
import sys
from freoa_verifica.limites import restante
from freoa_verifica.parsers.model import Issue, ParsedDocument, document_from_dict

_PROFILES = ("planalto", "cvm_docx", "bcb_json", "cvm_pdf", "pdf_texto")
# F03: limites efetivos do filho por perfil (memória em MiB, CPU em s). Só POSIX;
# no Windows valem o timeout do pai e os limites de páginas/texto do próprio parser.
_LIMITES = {"cvm_pdf": (1024, 60), "pdf_texto": (1024, 60)}

def _failure(profile: str, detail: str) -> ParsedDocument:
    return ParsedDocument(profile, "0", "", None, "", issues=[
        Issue("TRUNCATED", None, detail, blocking_scope="document"),
    ])

def parse_isolated(profile: str, data: bytes | str, timeout: float) -> ParsedDocument:
    """Executa em filho; timeout, falha ou saida invalida geram quarentena."""
    if profile not in _PROFILES:
        return _failure(profile, "perfil desconhecido")
    raw = data.encode("utf-8") if isinstance(data, str) else data
    timeout = restante(timeout)
    if timeout <= 0:
        return _failure(profile, "orcamento esgotado")
    with subprocess.Popen(
        [sys.executable, "-m", "freoa_verifica.parsers.isolated", profile],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as proc:
        try:
            output, _stderr = proc.communicate(raw, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return _failure(profile, f"parse_isolated excedeu timeout={timeout}s")
        if proc.returncode != 0:
            motivo = (_stderr or b"").decode("utf-8", "replace").strip().splitlines()
            return _failure(profile, "parse_isolated falhou no filho: " + (motivo[-1][:200] if motivo else "sem detalhe"))
    try:
        return document_from_dict(json.loads(output))
    except (ValueError, TypeError, KeyError):
        return _failure(profile, "parse_isolated sem resultado valido do filho")

def _aplicar_limites(profile: str) -> None:
    mem_mb, cpu_s = _LIMITES.get(profile, (0, 0))
    try:
        import resource
    except ImportError:  # Windows
        return
    if mem_mb:
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb << 20, mem_mb << 20))
    if cpu_s:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 5))

def pdf_texto(body: bytes) -> ParsedDocument:
    """Texto de PDF de decisao (STF, TJSP) no filho: o pai nunca abre PDF de terceiro."""
    import io
    from pypdf import PdfReader
    from freoa_verifica.connectors.cvm_normas import PDF_MAX_PAGINAS, PDF_MAX_TEXTO
    reader = PdfReader(io.BytesIO(body))
    if len(reader.pages) > PDF_MAX_PAGINAS:
        raise ValueError("pdf_paginas_excedidas")
    parts, total = [], 0
    for page in reader.pages:
        t = page.extract_text() or ""
        total += len(t)
        if total > PDF_MAX_TEXTO:
            raise ValueError("pdf_texto_excedido")
        parts.append(t)
    return ParsedDocument("pdf_texto", "pdf-texto-1", "", None, "\n".join(parts))


def texto_pdf_isolado(body: bytes, timeout: float = 60.0) -> str:
    doc = parse_isolated("pdf_texto", body, timeout)
    return "" if doc.quarantined else doc.text


def _main() -> None:
    from freoa_verifica.parsers.planalto import parse_planalto
    from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
    from freoa_verifica.parsers.bcb_json import parse_bcb_json
    from freoa_verifica.connectors.cvm_normas import parse_pdf_direto
    parsers = dict(zip(_PROFILES, (parse_planalto, parse_cvm_docx, parse_bcb_json, parse_pdf_direto, pdf_texto)))
    _aplicar_limites(sys.argv[1])
    try:
        document = parsers[sys.argv[1]](sys.stdin.buffer.read())
    except MemoryError:
        sys.stderr.write("memoria_excedida\n")
        sys.exit(3)
    except Exception as exc:  # noqa: BLE001 — o pai transforma em quarentena
        sys.stderr.write(str(getattr(exc, "reason", None) or type(exc).__name__) + "\n")
        sys.exit(3)
    sys.stdout.buffer.write(json.dumps(asdict(document), ensure_ascii=False).encode("utf-8"))

if __name__ == "__main__":
    _main()
