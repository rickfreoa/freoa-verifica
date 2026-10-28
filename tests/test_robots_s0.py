"""S0b: leitura do robots.txt pelo RFC 9309 (decisão 0071): módulo puro, instrumento e evidência da recusa."""

from __future__ import annotations

import ast
import hashlib
import json
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from freoa_verifica import captura, robots_s0
from freoa_verifica.connectors import httputil
from freoa_verifica.robots_s0 import (
    BARREIRA, MIMES_ROBOTS, SEGUIR, SEM_RESTRICOES, SHA256_VAZIO, VEDADO, ler_do_registro, ler_robots,
)
from freoa_verifica.transport import HTTPMetadata, RespostaInvalida, Timeout, TooLarge, TransportError
from tests.test_transport import _fast_guards, _wire_local

HOST = "https://jurisprudencia.tst.jus.br"
ROBOTS = HOST + "/robots.txt"
SIMPLES = b"User-agent: *\nDisallow: /admin/\nAllow: /\nSitemap: https://x.jus.br/s.xml\n"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --- módulo puro: tabela da regra -----------------------------------------------------------------------------


@pytest.mark.parametrize("status,motivo", [(404, "ausente_404"), (410, "ausente_410")])
def test_ausencia_404_410_sem_restricoes(status, motivo):
    r = ler_robots(status, None, None)
    assert (r.estado, r.motivo) == (SEM_RESTRICOES, motivo)
    assert r.decidir(HOST + "/qualquer").acao == SEM_RESTRICOES


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503, 504, 599])
def test_recusas_e_5xx_sao_barreira(status):
    r = ler_robots(status, None, None)
    assert (r.estado, r.motivo) == (BARREIRA, f"http_{status}")
    assert r.decidir(HOST + "/x").acao == BARREIRA


@pytest.mark.parametrize("status", [400, 402, 405, 406, 408, 409, 418, 451])
def test_outros_4xx_sao_barreira_por_conservadorismo(status):
    r = ler_robots(status, None, None)
    assert r.estado == BARREIRA and r.motivo == f"http_{status}_outro_4xx" and "conservadorismo" in r.detalhe


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirecionamento_e_barreira(status):
    assert ler_robots(status, None, None).motivo == "redirecionamento"


@pytest.mark.parametrize("status", [None, 100, 204, 206])
def test_status_sem_regra_e_barreira(status):
    assert ler_robots(status, None, None).estado == BARREIRA


def test_200_com_regras_interpretaveis_obedece_disallow():
    r = ler_robots(200, "text/plain; charset=utf-8", SIMPLES)
    assert r.estado == robots_s0.REGRAS and r.sha256 == _sha(SIMPLES) and r.content_type.startswith("text/plain")
    assert r.decidir(HOST + "/admin/x").acao == VEDADO
    assert r.decidir(HOST + "/admin/x").motivo == "disallow_aplicavel"
    assert r.decidir(HOST + "/jurisprudencia/").acao == SEGUIR


def test_regras_do_agente_do_produto_prevalecem_sobre_o_curinga():
    corpo = b"User-agent: *\nDisallow: /\n\nUser-agent: freoa-verifica\nDisallow: /privado/\n"
    r = ler_robots(200, "text/plain", corpo)
    assert r.decidir(HOST + "/publico").acao == SEGUIR and r.decidir(HOST + "/privado/x").acao == VEDADO


def test_disallow_tudo_veda_tudo_e_disallow_vazio_libera():
    assert ler_robots(200, "text/plain", b"User-agent: *\nDisallow: /\n").decidir(HOST + "/a").acao == VEDADO
    assert ler_robots(200, "text/plain", b"User-agent: *\nDisallow:\n").decidir(HOST + "/a").acao == SEGUIR


def test_curinga_e_ancora_do_rfc_9309_somam_restricao_que_o_robotparser_nao_conhece():
    corpo = b"User-agent: *\nDisallow: /*.pdf$\nDisallow: /busca*privado\n"
    r = ler_robots(200, "text/plain", corpo)
    assert r.decidir(HOST + "/a/b.pdf").acao == VEDADO
    assert r.decidir(HOST + "/busca/x/privado").acao == VEDADO
    assert r.decidir(HOST + "/a/b.pdf?x=1").acao == SEGUIR  # `$` ancora o fim
    assert r.decidir(HOST + "/a/b.html").acao == SEGUIR


def test_avaliador_rfc_aplica_a_correspondencia_mais_longa_e_allow_vence_empate():
    linhas = ("User-agent: *", "Disallow: /a/", "Allow: /a/b")
    assert robots_s0._permitido_rfc(linhas, HOST + "/a/b") is True  # Allow mais longo (4 > 3)
    assert robots_s0._permitido_rfc(linhas, HOST + "/a/c") is False
    assert robots_s0._permitido_rfc(("User-agent: *", "Disallow: /a", "Allow: /a"), HOST + "/a") is True  # empate
    assert robots_s0._permitido_rfc(("User-agent: *", "Disallow: /"), HOST + "/") is False


def test_a_decisao_soma_restricoes_do_robotparser_e_do_avaliador_rfc(monkeypatch):
    """O robotparser muda entre versões do Python (curingas, precedência): vedado se QUALQUER um vedar."""
    leitura = ler_robots(200, "text/plain", b"User-agent: *\nDisallow: /x/\n")
    monkeypatch.setattr(robots_s0.urllib.robotparser.RobotFileParser, "can_fetch", lambda self, a, u: True)
    monkeypatch.setattr(robots_s0, "_permitido_rfc", lambda linhas, url: False)
    d = leitura.decidir(HOST + "/y")
    assert d.acao == VEDADO and "RFC" in d.detalhe
    monkeypatch.setattr(robots_s0, "_permitido_rfc", lambda linhas, url: True)
    monkeypatch.setattr(robots_s0.urllib.robotparser.RobotFileParser, "can_fetch", lambda self, a, u: False)
    d = leitura.decidir(HOST + "/y")
    assert d.acao == VEDADO and "robotparser" in d.detalhe


@pytest.mark.parametrize("mime,corpo", [
    ("text/html", b"<!doctype html><html><head><title>SPA</title></head><body><div id=app></div></body></html>"),
    ("text/html; charset=utf-8", b"<html><body>Pagina nao encontrada</body></html>"),
    ("application/octet-stream", b"\x00\x01\x02\xff binario qualquer"),
    ("application/json", b'{"ok":true}'),
    ("text/plain", b"Bem-vindo ao portal"),
    ("text/plain", b"# so comentario\n\n"),
    ("application/xml", b"<?xml version='1.0'?><erro/>"),
])
def test_200_sem_regras_interpretaveis_nao_restringe_e_registra_content_type_e_sha(mime, corpo):
    r = ler_robots(200, mime, corpo)
    assert r.estado == SEM_RESTRICOES and r.motivo == "200_sem_regras_interpretaveis"
    assert r.content_type == mime and r.sha256 == _sha(corpo) and r.status == 200
    assert r.decidir(HOST + "/tudo").acao == SEM_RESTRICOES


def test_200_vazio_sem_restricoes_com_sha_do_vazio():
    for vazio in (b"", None):
        r = ler_robots(200, "text/plain", vazio)
        assert (r.estado, r.motivo, r.sha256) == (SEM_RESTRICOES, "200_corpo_vazio", SHA256_VAZIO)


def test_200_html_com_marcador_de_desafio_e_barreira_e_robots_com_captcha_no_disallow_nao():
    html = b"<html><body><div class='g-recaptcha'></div>captcha</body></html>"
    r = ler_robots(200, "text/html", html)
    assert r.estado == BARREIRA and r.motivo == "desafio_captcha" and r.sha256 == _sha(html)
    legitimo = b"User-agent: *\nDisallow: /captcha/\n"
    assert ler_robots(200, "text/plain", legitimo).estado == robots_s0.REGRAS


@pytest.mark.parametrize("corpo", [
    b"Disallow: /\n",  # sem grupo User-agent
    b"User-agent: *\nDisallow: /\nIsto nao e diretiva\n",  # misturado a linha desconhecida
])
def test_allow_disallow_nao_interpretavel_e_barreira_por_conservadorismo(corpo):
    r = ler_robots(200, "text/plain", corpo)
    assert r.estado == BARREIRA and r.motivo == "regras_ambiguas" and r.sha256 == _sha(corpo)


def test_diretivas_nao_padrao_comuns_nao_escondem_o_disallow():
    corpo = b"User-agent: *\nHost: x.jus.br\nCrawl-delay: 10\nDisallow: /\n"
    assert ler_robots(200, "text/plain", corpo).decidir(HOST + "/a").acao == VEDADO


def test_charset_que_nao_fecha_usa_a_vista_latin1_para_ler_as_diretivas():
    corpo = "User-agent: *\n# não indexar\nDisallow: /admin/\n".encode("latin-1")
    r = ler_robots(200, "text/plain", corpo)
    assert r.estado == robots_s0.REGRAS and r.decidir(HOST + "/admin/").acao == VEDADO


def test_bom_utf8_e_utf16():
    assert ler_robots(200, "text/plain", b"\xef\xbb\xbf" + SIMPLES).decidir(HOST + "/admin/").acao == VEDADO
    u16 = "User-agent: *\nDisallow: /admin/\n".encode("utf-16")
    assert ler_robots(200, "text/plain", u16).decidir(HOST + "/admin/").acao == VEDADO


# --- módulo puro: a partir do registro `.captura.json` ----------------------------------------------------------


def _reg(**kw):
    base = {"unavailable": True, "motivo": None, "categoria": None, "evidencia": {}, "status": None,
            "content_type": None, "cabecalhos": {}, "sha256": None, "arquivo": None}
    base.update(kw)
    return base


def test_registro_200_confere_o_sha256_do_corpo():
    ok = _reg(unavailable=False, status=200, content_type="text/plain", sha256=_sha(SIMPLES))
    assert ler_do_registro(ok, SIMPLES).estado == robots_s0.REGRAS
    assert ler_do_registro(ok, SIMPLES + b"x").motivo == "corpo_nao_confere"
    assert ler_do_registro(ok, None).motivo == "registro_inconsistente"


@pytest.mark.parametrize("registro,estado,motivo", [
    (_reg(motivo="http_404", evidencia={"status": 404}), SEM_RESTRICOES, "ausente_404"),
    (_reg(motivo="http_410", evidencia={"status": 410}), SEM_RESTRICOES, "ausente_410"),
    (_reg(motivo="http_403", categoria="recusa_identificado", evidencia={"status": 403}), BARREIRA, "http_403"),
    (_reg(motivo="http_429", evidencia={"status": 429}), BARREIRA, "http_429"),
    (_reg(motivo="http_503", categoria="fonte_fora", evidencia={"status": 503}), BARREIRA, "http_503"),
    (_reg(motivo="http_418", evidencia={"status": 418}), BARREIRA, "http_418_outro_4xx"),
    (_reg(motivo="desafio_cloudflare", categoria="ambiental_desafio", evidencia={"status": 403}), BARREIRA,
     "desafio_cloudflare"),
    (_reg(motivo="transporte_Timeout", categoria="fonte_fora", evidencia={"excecao": "Timeout"}), BARREIRA, "timeout"),
    (_reg(motivo="transporte_TransportError", categoria="fonte_fora", evidencia={"excecao": "TransportError"}), BARREIRA,
     "erro_transporte"),
    (_reg(motivo="transporte_BlockedHost", evidencia={"excecao": "BlockedHost", "saltos": [
        {"url": ROBOTS, "status": 302}]}), BARREIRA, "redirecionamento"),
    (_reg(motivo="transporte_BlockedHost", evidencia={"excecao": "BlockedHost"}), BARREIRA, "bloqueio_do_transporte"),
    (_reg(motivo="corpo_vazio", categoria="resposta_inesperada", evidencia={"status": 200}), SEM_RESTRICOES,
     "200_corpo_vazio"),
    (_reg(motivo="transporte_RespostaInvalida", categoria="resposta_inesperada", evidencia={
        "status": 200, "excecao": "RespostaInvalida", "mensagem": "MIME não permitido: (ausente)"}), BARREIRA,
     "content_type_ausente"),
    (_reg(motivo="transporte_RespostaInvalida", categoria="resposta_inesperada", evidencia={
        "status": 200, "excecao": "RespostaInvalida", "content_type": "image/png",
        "mensagem": "MIME não permitido: image/png"}), BARREIRA, "resposta_200_recusada"),
    (_reg(motivo="algo_novo"), BARREIRA, "indisponivel_algo_novo"),
])
def test_registro_indisponivel_mapeado_pela_regra(registro, estado, motivo):
    r = ler_do_registro(registro)
    assert (r.estado, r.motivo) == (estado, motivo)


# --- teste estrutural: fora do grafo do serviço, do MCP e da CLI ---------------------------------------------------

PACOTE = Path(__file__).resolve().parents[1] / "freoa_verifica"


def _importa(caminho: Path) -> set[str]:
    achados: set[str] = set()
    for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8-sig"))):
        if isinstance(no, ast.Import):
            achados |= {a.name for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            achados.add(no.module)
            achados |= {f"{no.module}.{a.name}" for a in no.names}
    return {a for a in achados if a == "freoa_verifica" or a.startswith("freoa_verifica.")}


def _fecho(partida: str) -> set[str]:
    visto, fila = set(), [partida]
    while fila:
        mod = fila.pop()
        if mod in visto:
            continue
        rel = PACOTE.parent / (mod.replace(".", "/") + ".py")
        pacote = PACOTE.parent / mod.replace(".", "/") / "__init__.py"
        arquivo = rel if rel.is_file() else pacote if pacote.is_file() else None
        if arquivo is None:
            continue
        visto.add(mod)
        fila.extend(_importa(arquivo))
    return visto


@pytest.mark.repositorio
@pytest.mark.parametrize("entrada", ["freoa_verifica.service", "freoa_verifica.mcp_server", "freoa_verifica.cli"])
def test_servico_mcp_e_cli_nao_importam_robots_s0_nem_a_captura(entrada):
    fecho = _fecho(entrada)
    assert entrada in fecho and len(fecho) > 5
    assert "freoa_verifica.robots_s0" not in fecho and "freoa_verifica.captura" not in fecho


@pytest.mark.repositorio
def test_so_o_instrumento_e_o_orquestrador_importam_robots_s0():
    raiz = PACOTE.parent
    importadores = set()
    for arquivo in [*PACOTE.rglob("*.py"), *(raiz / "scripts").glob("*.py")]:
        if "freoa_verifica.robots_s0" in _importa(arquivo) and arquivo.name != "robots_s0.py":
            importadores.add(arquivo.relative_to(raiz).as_posix())
    assert importadores == {"freoa_verifica/captura.py", "scripts/s0_orquestrar.py"}


def test_importar_servico_mcp_e_cli_nao_carrega_robots_s0_em_execucao():
    codigo = ("import sys, freoa_verifica.service, freoa_verifica.cli\n"
              "try:\n    import freoa_verifica.mcp_server\nexcept ImportError:\n    pass\n"
              "assert 'freoa_verifica.robots_s0' not in sys.modules and 'freoa_verifica.captura' not in sys.modules\n")
    r = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --- instrumento: servidor local com o transporte real -----------------------------------------------------------


def _servidor(respostas: dict[str, bytes]):
    """Servidor local: devolve os bytes crus por caminho (ou 404) e registra cada caminho pedido."""

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            try:
                dados = self.request.recv(65536)
            except OSError:
                return
            caminho = dados.split(b"\r\n", 1)[0].decode("latin-1").split(" ")[1]
            self.server.percursos.append(caminho)
            cru = respostas.get(caminho, b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            if cru:
                self.request.sendall(cru)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    server.percursos = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _http(status: int, corpo: bytes = b"", ct: str | None = None, extra: str = "") -> bytes:
    cab = f"HTTP/1.1 {status} X\r\n" + (f"Content-Type: {ct}\r\n" if ct else "") + extra
    return cab.encode("latin-1") + b"Content-Length: %d\r\n\r\n" % len(corpo) + corpo


def _sondar(monkeypatch, tmp_path, resposta: bytes, *, url=ROBOTS, fonte="tst"):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    server = _servidor({"/robots.txt": resposta})
    _fast_guards(monkeypatch)
    _wire_local(monkeypatch, server.server_address[1])
    try:
        reg = captura.capturar(None, url=url, destino=tmp_path, sonda=True, chave="r", fonte_sonda=fonte)
    finally:
        server.shutdown()
        server.server_close()
    salvo = json.loads((tmp_path / "r.captura.json").read_text(encoding="utf-8"))
    arquivo = tmp_path / salvo["arquivo"] if salvo.get("arquivo") else None
    corpo = arquivo.read_bytes() if arquivo else None
    return reg, salvo, corpo, ler_do_registro(salvo, corpo), server


@pytest.mark.parametrize("mime,corpo", [
    ("text/html; charset=utf-8", b"<!doctype html><html><body><div id=root></div></body></html>"),
    ("application/octet-stream", b"\x00\x01 qualquer coisa"),
    ("application/json", b'{"nao":"e robots"}'),
    ("text/plain", b"pagina de boas-vindas"),
])
def test_200_de_qualquer_mime_da_lista_grava_o_corpo_e_nao_restringe(monkeypatch, tmp_path, mime, corpo):
    reg, salvo, gravado, leitura, server = _sondar(monkeypatch, tmp_path, _http(200, corpo, mime))
    assert not reg.unavailable and salvo["status"] == 200 and gravado == corpo
    assert salvo["content_type"] == mime.split(";")[0] and salvo["sha256"] == _sha(corpo)
    assert (leitura.estado, leitura.motivo) == (SEM_RESTRICOES, "200_sem_regras_interpretaveis")
    assert leitura.sha256 == _sha(corpo) and server.percursos == ["/robots.txt"]


def test_200_text_plain_com_regras_obedece_e_veda(monkeypatch, tmp_path):
    reg, salvo, gravado, leitura, _ = _sondar(monkeypatch, tmp_path, _http(200, SIMPLES, "text/plain; charset=utf-8"))
    assert gravado == SIMPLES and leitura.estado == robots_s0.REGRAS
    assert leitura.decidir(HOST + "/admin/x").acao == VEDADO and leitura.decidir(HOST + "/config.json").acao == SEGUIR


def test_200_vazio_vira_sem_restricoes(monkeypatch, tmp_path):
    reg, salvo, gravado, leitura, _ = _sondar(monkeypatch, tmp_path, _http(200, b"", "text/plain"))
    assert reg.unavailable and salvo["motivo"] == "corpo_vazio" and salvo["evidencia"]["excecao"] == "EmptyBody"
    assert (leitura.estado, leitura.motivo, leitura.sha256) == (SEM_RESTRICOES, "200_corpo_vazio", SHA256_VAZIO)


@pytest.mark.parametrize("status,estado,motivo", [
    (404, SEM_RESTRICOES, "ausente_404"), (410, SEM_RESTRICOES, "ausente_410"),
    (401, BARREIRA, "http_401"), (403, BARREIRA, "http_403"), (429, BARREIRA, "http_429"),
    (500, BARREIRA, "http_500"), (503, BARREIRA, "http_503"), (418, BARREIRA, "http_418_outro_4xx"),
])
def test_status_http_ponta_a_ponta_um_unico_pedido(monkeypatch, tmp_path, status, estado, motivo):
    reg, salvo, gravado, leitura, server = _sondar(
        monkeypatch, tmp_path, _http(status, b"corpo de erro", "text/plain"))
    assert (leitura.estado, leitura.motivo) == (estado, motivo)
    assert salvo["unavailable"] and gravado is None and salvo["evidencia"]["status"] == status
    assert server.percursos == ["/robots.txt"]  # sem repetição, mesmo em 503


@pytest.mark.parametrize("destino", ["/admin/login", "/robots.txt.bak", "https://jurisprudencia-backend.tst.jus.br/robots.txt"])
def test_redirecionamento_nao_e_seguido_e_e_barreira_com_evidencia(monkeypatch, tmp_path, destino):
    resposta = f"HTTP/1.1 302 Found\r\nLocation: {destino}\r\nContent-Length: 0\r\n\r\n".encode("latin-1")
    reg, salvo, gravado, leitura, server = _sondar(monkeypatch, tmp_path, resposta)
    assert server.percursos == ["/robots.txt"] and gravado is None
    assert (leitura.estado, leitura.motivo) == (BARREIRA, "redirecionamento")
    ev = salvo["evidencia"]
    assert ev["excecao"] == "BlockedHost" and ev["saltos"] == [{"url": ROBOTS, "status": 302}]


def test_200_sem_content_type_e_recusa_do_transporte_registrada_e_barreira(monkeypatch, tmp_path):
    reg, salvo, gravado, leitura, _ = _sondar(monkeypatch, tmp_path, _http(200, b"<html>x</html>"))
    ev = salvo["evidencia"]
    assert salvo["motivo"] == "transporte_RespostaInvalida" and ev["status"] == 200
    assert ev["excecao"] == "RespostaInvalida" and "(ausente)" in ev["mensagem"] and "content_type" not in ev
    assert (leitura.estado, leitura.motivo) == (BARREIRA, "content_type_ausente")


def test_200_com_mime_fora_da_lista_registra_o_content_type_recebido(monkeypatch, tmp_path):
    reg, salvo, gravado, leitura, _ = _sondar(monkeypatch, tmp_path, _http(200, b"\x89PNG....", "image/png"))
    ev = salvo["evidencia"]
    assert ev["content_type"] == "image/png" and ev["excecao"] == "RespostaInvalida" and "image/png" in ev["mensagem"]
    assert (leitura.estado, leitura.motivo) == (BARREIRA, "resposta_200_recusada") and gravado is None


def test_conteudo_acima_do_limite_registra_a_subclasse(monkeypatch, tmp_path):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)

    def estoura(url, **kw):
        raise TooLarge("Corpo declarado acima do limite", http=HTTPMetadata(200, (("content-type", "text/plain"),)))

    monkeypatch.setattr(httputil, "transport_fetch", estoura)
    reg = captura.capturar(None, url=ROBOTS, destino=tmp_path, sonda=True, chave="r", fonte_sonda="tst")
    assert reg.evidencia["excecao"] == "TooLarge" and reg.evidencia["content_type"] == "text/plain"


@pytest.mark.parametrize("erro,excecao,motivo", [
    (Timeout("Prazo de captura esgotado"), "Timeout", "timeout"),
    (TransportError("conexão recusada"), "TransportError", "erro_transporte"),
])
def test_timeout_e_erro_de_transporte_sao_barreira_e_registram_a_subclasse(monkeypatch, tmp_path, erro, excecao, motivo):
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)
    chamadas = []

    def falha(url, **kw):
        chamadas.append(url)
        raise erro

    monkeypatch.setattr(httputil, "transport_fetch", falha)
    captura.capturar(None, url=ROBOTS, destino=tmp_path, sonda=True, chave="r", fonte_sonda="tst")
    salvo = json.loads((tmp_path / "r.captura.json").read_text(encoding="utf-8"))
    assert salvo["evidencia"]["excecao"] == excecao and salvo["evidencia"]["mensagem"]
    assert (ler_do_registro(salvo).estado, ler_do_registro(salvo).motivo) == (BARREIRA, motivo)
    assert chamadas == [ROBOTS]


def test_servidor_que_fecha_sem_responder_e_barreira_de_transporte(monkeypatch, tmp_path):
    reg, salvo, gravado, leitura, server = _sondar(monkeypatch, tmp_path, b"")
    assert leitura.estado == BARREIRA and salvo["unavailable"] and server.percursos == ["/robots.txt"]
    assert salvo["evidencia"]["excecao"] in {"TransportError", "RespostaInvalida", "Timeout"}


def test_desafio_no_corpo_200_e_barreira_sem_gravar_o_corpo(monkeypatch, tmp_path):
    html = b"<html><body><h1>Verifique</h1><div class='g-recaptcha'></div> captcha</body></html>"
    reg, salvo, gravado, leitura, _ = _sondar(monkeypatch, tmp_path, _http(200, html, "text/html"))
    assert salvo["unavailable"] and salvo["motivo"] == "desafio_captcha" and salvo["categoria"] == "ambiental_desafio"
    assert gravado is None and salvo["evidencia"]["sha256"] == _sha(html) and salvo["evidencia"]["content_type"] == "text/html"
    assert (leitura.estado, leitura.motivo) == (BARREIRA, "desafio_captcha")
    assert salvo["sha256"] is None and salvo["status"] is None and salvo["arquivo"] is None


def test_robots_com_captcha_no_disallow_nao_e_desafio(monkeypatch, tmp_path):
    corpo = b"User-agent: *\nDisallow: /captcha/\n"
    reg, salvo, gravado, leitura, _ = _sondar(monkeypatch, tmp_path, _http(200, corpo, "text/plain"))
    assert not reg.unavailable and gravado == corpo and leitura.decidir(HOST + "/captcha/x").acao == VEDADO


def test_desafio_de_borda_em_403_continua_barreira(monkeypatch, tmp_path):
    resposta = _http(403, b"negado", "text/html", "cf-mitigated: challenge\r\n")
    reg, salvo, gravado, leitura, _ = _sondar(monkeypatch, tmp_path, resposta)
    assert leitura.estado == BARREIRA and leitura.motivo.startswith("desafio_")


# --- evidência sem cabeçalhos sensíveis --------------------------------------------------------------------------


@pytest.mark.parametrize("resposta", [
    _http(403, b"x", "text/plain", "Set-Cookie: sessao=SEGREDO123; HttpOnly\r\nAuthorization: Bearer SEGREDO123\r\n"
          "Cookie: a=SEGREDO123\r\n"),
    _http(200, b"y", "image/png", "Set-Cookie: sessao=SEGREDO123\r\n"),
    _http(200, b"y", None, "Set-Cookie: sessao=SEGREDO123\r\n"),
    _http(302, b"", None, "Location: /admin\r\nSet-Cookie: sessao=SEGREDO123\r\n"),
])
def test_nada_de_cookie_ou_cabecalho_sensivel_na_evidencia(monkeypatch, tmp_path, resposta):
    reg, salvo, gravado, leitura, _ = _sondar(monkeypatch, tmp_path, resposta)
    bruto = (tmp_path / "r.captura.json").read_text(encoding="utf-8").lower()
    assert "segredo123" not in bruto and "set-cookie" not in bruto and "authorization" not in bruto
    assert "cookie" not in bruto.replace('"cabecalhos"', "")


def test_mensagem_da_excecao_e_aparada_e_sem_nome_de_cabecalho_sensivel():
    longo = "Set-Cookie: abc\x00\x07 Authorization: x " + "a" * 500
    curta = captura._mensagem_curta(longo)
    assert len(curta) <= 160 and "cookie" not in curta.lower() and "authorization" not in curta.lower()
    assert "\x00" not in curta and "\x07" not in curta


def test_recusa_do_transporte_comum_tambem_registra_subclasse_e_content_type(monkeypatch, tmp_path):
    """Vale para toda recusa de transporte, não só para o robots.txt (rodada 1, achado 4)."""
    monkeypatch.setattr(captura, "_raiz_repo", lambda: None)

    def recusa(url, **kw):
        raise RespostaInvalida("MIME não permitido: image/png", http=HTTPMetadata(200, (("content-type", "image/png"),)))

    monkeypatch.setattr(httputil, "transport_fetch", recusa)
    reg = captura.capturar(None, url="https://jurisprudencia.tst.jus.br/config.json", destino=tmp_path, sonda=True,
                           chave="c", fonte_sonda="tst")
    assert reg.motivo == "transporte_RespostaInvalida"
    assert reg.evidencia["excecao"] == "RespostaInvalida" and reg.evidencia["content_type"] == "image/png"
    assert "image/png" in reg.evidencia["mensagem"]


# --- o corpo do robots nunca vira fixture --------------------------------------------------------------------------


def test_robots_so_se_captura_como_sonda(monkeypatch, tmp_path):
    chamadas = []
    monkeypatch.setattr(httputil, "transport_fetch", lambda url, **kw: chamadas.append(url))
    with pytest.raises(ValueError, match="só se captura como sonda"):
        captura.capturar("tjsp", url="https://esaj.tjsp.jus.br/robots.txt", destino=tmp_path, sonda=False, chave="r")
    assert chamadas == []


def test_registrar_fixture_recusa_robots(monkeypatch, tmp_path):
    reg, *_ = _sondar(monkeypatch, tmp_path, _http(200, SIMPLES, "text/plain"))
    with pytest.raises(ValueError, match="robots.txt é evidência de sonda"):
        captura.registrar_fixture(reg, "robots_x", tmp_path / "fx")


def test_lista_de_mimes_do_robots_valida_para_o_transporte():
    import re

    assert {"text/plain", "text/html", "application/octet-stream"} <= MIMES_ROBOTS
    assert all(re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", m) for m in MIMES_ROBOTS)
