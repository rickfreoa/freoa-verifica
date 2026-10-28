"""S0b: orquestrador oficial (`scripts/s0_orquestrar.py`), com instrumento falso (nada de rede)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.repositorio

RAIZ = Path(__file__).resolve().parents[1]


def _carregar():
    spec = importlib.util.spec_from_file_location("s0_orquestrar", RAIZ / "scripts" / "s0_orquestrar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


orq = _carregar()


def _cmd(fonte, chave, url, pasta=None):
    return (f'python scripts/capturar_fixture.py --fonte-sonda {fonte} --sonda --saida C:/dev/fv14-sondas/{pasta or fonte} '
            f'--chave {chave} --url "{url}"')


ROTEIRO = "\n".join([
    "# roteiro", "```powershell",
    _cmd("a", "a_robots", "https://a.jus.br/robots.txt"),
    _cmd("a", "a_pesquisa", "https://a.jus.br/pesquisa/"),
    _cmd("a", "a_admin", "https://a.jus.br/admin/x"),
    _cmd("b", "b_robots", "https://b.jus.br/robots.txt"),
    _cmd("b", "b_rota", "https://b.jus.br/rota"),
    _cmd("c", "c_robots", "https://c.jus.br/robots.txt"),
    _cmd("c", "c_rota", "https://c.jus.br/rota"),
    _cmd("d", "d_robots", "https://d.jus.br/robots.txt"),
    _cmd("d", "d_rota", "https://d.jus.br/rota"),
    _cmd("e", "e_robots", "https://e.jus.br/robots.txt"),
    _cmd("e", "e_robots_de_novo", "https://e.jus.br/robots.txt", "e2"),
    _cmd("e", "e_rota", "https://e.jus.br/rota"),
    "```", "```powershell-bloqueado",
    _cmd("x", "x_robots", "https://x.jus.br/robots.txt"),
    "```", ""])

REGRAS = b"User-agent: *\nDisallow: /admin/\n"


class Falso:
    """Instrumento falso: grava `.captura.json` (e corpo) como o real e conta os pedidos por URL."""

    def __init__(self, respostas):
        self.respostas = respostas  # host -> dict(robots=..., rota=...)
        self.chamadas = []

    def __call__(self, args):
        self.chamadas.append(list(args))
        url, chave = args[args.index("--url") + 1], args[args.index("--chave") + 1]
        pasta = Path(args[args.index("--saida") + 1])
        pasta.mkdir(parents=True, exist_ok=True)
        host, caminho = urlsplit(url).hostname, urlsplit(url).path
        r = self.respostas[host]["robots" if caminho == "/robots.txt" else "rota"]
        reg = {"url": url, "unavailable": True, "motivo": None, "categoria": None, "evidencia": {}, "status": None,
               "content_type": None, "cabecalhos": {}, "sha256": None, "bytes": None, "arquivo": None,
               "url_final": None}
        if r[0] == 200:
            corpo, ct = r[1], r[2]
            reg.update(unavailable=False, status=200, content_type=ct, sha256=hashlib.sha256(corpo).hexdigest(),
                       bytes=len(corpo), arquivo=f"{chave}.bin", url_final=url, cabecalhos={"content-type": ct})
            (pasta / f"{chave}.bin").write_bytes(corpo)
        else:
            reg.update(motivo=r[1], evidencia=r[2] if len(r) > 2 else {})
        (pasta / f"{chave}.captura.json").write_text(json.dumps(reg), encoding="utf-8")
        return SimpleNamespace(returncode=1 if reg["unavailable"] else 0, stdout="", stderr=f"em {pasta}")


def _rodar(tmp_path, respostas, **kw):
    falso = Falso(respostas)
    rel = orq.orquestrar(ROTEIRO, tmp_path, executor=falso, **kw)
    return rel, falso


OK = {"robots": (200, REGRAS, "text/plain"), "rota": (200, b"{}", "application/json")}
HOSTS = {
    "a.jus.br": OK,
    "b.jus.br": {"robots": (404, "http_404", {"status": 404}), "rota": (200, b"{}", "application/json")},
    "c.jus.br": {"robots": (403, "http_403", {"status": 403}), "rota": (200, b"{}", "application/json")},
    "d.jus.br": {"robots": (200, b"<html>spa</html>", "text/html"), "rota": (200, b"{}", "application/json")},
    "e.jus.br": OK,
}


def _urls(falso):
    return [a[a.index("--url") + 1] for a in falso.chamadas]


def test_cada_url_e_pedida_no_maximo_uma_vez_e_robots_uma_vez_por_host(tmp_path):
    rel, falso = _rodar(tmp_path, HOSTS)
    urls = _urls(falso)
    assert len(urls) == len(set(urls))
    assert sum(u.endswith("/robots.txt") for u in urls if "e.jus.br" in u) == 1
    ignorado = next(c for c in rel["hosts"]["e.jus.br"]["comandos"] if c["chave"] == "e_robots_de_novo")
    assert not ignorado["executado"]


def test_regra_por_host(tmp_path):
    rel, falso = _rodar(tmp_path, HOSTS)
    h = rel["hosts"]
    assert h["a.jus.br"]["parada"] is None
    cmd = {c["chave"]: c for c in h["a.jus.br"]["comandos"]}
    assert cmd["a_pesquisa"]["executado"] and not cmd["a_admin"]["executado"]
    assert "Disallow" in cmd["a_admin"]["razao"]
    assert h["b.jus.br"]["parada"] is None and h["b.jus.br"]["robots"]["motivo"] == "ausente_404"  # 404: sem restrições
    assert [c["executado"] for c in h["b.jus.br"]["comandos"]] == [True, True]
    assert h["c.jus.br"]["parada"].startswith("barreira no robots.txt: http_403")
    assert [c["executado"] for c in h["c.jus.br"]["comandos"]] == [True, False]
    assert h["d.jus.br"]["robots"]["motivo"] == "200_sem_regras_interpretaveis"  # HTML 200: sem restrições
    assert h["d.jus.br"]["robots"]["content_type"] == "text/html" and h["d.jus.br"]["robots"]["sha256"]
    assert [c["executado"] for c in h["d.jus.br"]["comandos"]] == [True, True]
    assert "x.jus.br" not in h  # bloco `powershell-bloqueado` não roda


def test_nenhum_pedido_a_host_com_barreira_anterior_vinda_de_arquivo(tmp_path):
    arquivo = tmp_path / "barreiras.json"
    arquivo.write_text(json.dumps({"c.jus.br": "registro da rodada 1: CAPTCHA", "a.jus.br": "outra barreira"}),
                       encoding="utf-8")
    barreiras = json.loads(arquivo.read_text(encoding="utf-8"))
    rel, falso = _rodar(tmp_path, HOSTS, barreiras=barreiras)
    assert not any("c.jus.br" in u or "a.jus.br" in u for u in _urls(falso))
    assert rel["hosts"]["a.jus.br"]["parada"].startswith("barreira anterior registrada: outra barreira")
    assert all(not c["executado"] and c["razao"] == "host parado" for c in rel["hosts"]["c.jus.br"]["comandos"])


def test_barreira_nao_esta_embutida_no_codigo():
    fonte = (RAIZ / "scripts" / "s0_orquestrar.py").read_text(encoding="utf-8")
    assert "BARREIRA_ANTERIOR" not in fonte and "captura.json (" not in fonte
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", fonte) and "/home/" not in fonte  # sem caminho de máquina


def test_barreira_no_robots_nao_tem_nova_tentativa_nem_pedido_ao_resto_do_host(tmp_path):
    rel, falso = _rodar(tmp_path, {**HOSTS, "e.jus.br": {"robots": (0, "transporte_Timeout", {"excecao": "Timeout"}),
                                                          "rota": OK["rota"]}})
    chamadas_e = [u for u in _urls(falso) if "e.jus.br" in u]
    assert chamadas_e == ["https://e.jus.br/robots.txt"]
    assert rel["hosts"]["e.jus.br"]["robots"]["motivo"] == "timeout"


def test_rota_indisponivel_para_o_host_sem_repetir(tmp_path):
    respostas = {**HOSTS, "a.jus.br": {"robots": OK["robots"], "rota": (503, "http_503", {"status": 503})}}
    rel, falso = _rodar(tmp_path, respostas)
    h = rel["hosts"]["a.jus.br"]
    assert h["parada"].startswith("indisponível ou erro em a_pesquisa")
    assert [u for u in _urls(falso) if "a.jus.br" in u] == ["https://a.jus.br/robots.txt", "https://a.jus.br/pesquisa/"]
    assert not h["comandos"][2]["executado"] and h["comandos"][2]["razao"] == "host parado"


def test_somente_robots_e_filtro_de_hosts(tmp_path):
    rel, falso = _rodar(tmp_path, HOSTS, somente_robots=True, hosts={"b.jus.br", "d.jus.br"})
    assert sorted(_urls(falso)) == ["https://b.jus.br/robots.txt", "https://d.jus.br/robots.txt"]
    assert sorted(rel["hosts"]) == ["b.jus.br", "d.jus.br"]
    assert sorted(rel["fora_da_rodada"]) == ["a.jus.br", "c.jus.br", "e.jus.br"]
    assert all(c["razao"] == "rodada só de robots.txt" for c in rel["hosts"]["b.jus.br"]["comandos"] if not c["executado"])


def test_saida_do_roteiro_e_trocada_e_o_relatorio_nao_tem_caminho_de_maquina(tmp_path):
    rel, falso = _rodar(tmp_path / "saida", HOSTS)
    for args in falso.chamadas:
        assert Path(args[args.index("--saida") + 1]).parent == tmp_path / "saida"
        assert "C:/dev" not in " ".join(args)
    texto = json.dumps(rel, ensure_ascii=False)
    assert str(tmp_path) not in texto and "C:/dev" not in texto and "<saida>" in texto


def test_instrumento_sem_registro_para_o_host(tmp_path):
    def mudo(args):
        return SimpleNamespace(returncode=2, stdout="", stderr="erro: destino dentro do repositório")

    rel = orq.orquestrar(ROTEIRO, tmp_path, executor=mudo, hosts={"a.jus.br"})
    assert rel["hosts"]["a.jus.br"]["parada"].startswith("instrumento sem registro")


def test_o_executor_padrao_chama_so_o_instrumento_sem_shell(monkeypatch):
    vistos = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: vistos.append((cmd, kw)) or SimpleNamespace(
        returncode=0, stdout="", stderr=""))
    orq.executar_instrumento(["--fonte-sonda", "a"])
    cmd, kw = vistos[0]
    assert cmd[1] == str(RAIZ / "scripts" / "capturar_fixture.py") and cmd[2:] == ["--fonte-sonda", "a"]
    assert kw.get("shell") is not True


def test_o_orquestrador_le_o_roteiro_oficial_e_o_robots_e_o_primeiro_de_cada_host():
    md = (RAIZ / "docs" / "S0-SONDAS.md").read_text(encoding="utf-8")
    por_host = {}
    for args in orq.comandos(md):
        por_host.setdefault(urlsplit(orq._url(args)).hostname, []).append(urlsplit(orq._url(args)).path)
    assert len(por_host) >= 15 and all(p[0] == "/robots.txt" for p in por_host.values())


def test_main_escreve_relatorio_e_aceita_arquivos_de_entrada(tmp_path, monkeypatch, capsys):
    roteiro = tmp_path / "roteiro.md"
    roteiro.write_text(ROTEIRO, encoding="utf-8")
    (tmp_path / "barreiras.json").write_text(json.dumps({"a.jus.br": "barreira de teste"}), encoding="utf-8")
    (tmp_path / "hosts.json").write_text(json.dumps(["a.jus.br", "b.jus.br"]), encoding="utf-8")
    falso = Falso(HOSTS)
    original = orq.orquestrar

    def com_falso(*a, **kw):
        kw.setdefault("executor", falso)
        return original(*a, **kw)

    monkeypatch.setattr(orq, "orquestrar", com_falso)
    rc = orq.main(["--roteiro", str(roteiro), "--saida", str(tmp_path / "s"), "--barreiras",
                   str(tmp_path / "barreiras.json"), "--hosts-arquivo", str(tmp_path / "hosts.json"),
                   "--relatorio", str(tmp_path / "rel.json")])
    rel = json.loads((tmp_path / "rel.json").read_text(encoding="utf-8"))
    assert rc == 0 and sorted(rel["hosts"]) == ["a.jus.br", "b.jus.br"]
    assert rel["hosts"]["a.jus.br"]["parada"].startswith("barreira anterior") and rel["hosts"]["b.jus.br"]["parada"] is None
    assert not any("a.jus.br" in u for u in _urls(falso))


def test_segunda_execucao_na_mesma_saida_reaproveita_a_evidencia_e_nunca_repete_pedido(tmp_path):
    rel1, falso1 = _rodar(tmp_path, HOSTS, somente_robots=True, hosts={"a.jus.br", "c.jus.br"})
    assert sorted(_urls(falso1)) == ["https://a.jus.br/robots.txt", "https://c.jus.br/robots.txt"]
    rel2, falso2 = _rodar(tmp_path, HOSTS, hosts={"a.jus.br", "c.jus.br"})
    assert _urls(falso2) == ["https://a.jus.br/pesquisa/"]  # robots reaproveitado; c segue parado pela barreira dele
    h = rel2["hosts"]
    robots_a = h["a.jus.br"]["comandos"][0]
    assert robots_a["reaproveitado"] and not robots_a["executado"] and robots_a["robots"]["estado"] == "regras"
    assert h["c.jus.br"]["parada"].startswith("barreira no robots.txt: http_403")
    todas = _urls(falso1) + _urls(falso2)
    assert len(todas) == len(set(todas))


def test_rodada_2_so_pede_o_robots_dos_nove_hosts_e_nenhum_com_barreira(tmp_path):
    entradas = RAIZ / "docs" / "auditoria" / "1.4.0" / "s0b-rodada2"
    hosts = set(json.loads((entradas / "hosts.json").read_text(encoding="utf-8")))
    barreiras = json.loads((entradas / "barreiras.json").read_text(encoding="utf-8"))
    assert len(hosts) == 9 and not hosts & set(barreiras)
    assert set(barreiras) == {"www10.trf2.jus.br", "web.trf3.jus.br", "jurisprudencia.trf2.jus.br", "esaj.tjsp.jus.br"}
    roteiro = (RAIZ / "docs" / "S0-SONDAS.md").read_text(encoding="utf-8")
    conhecidos = {urlsplit(orq._url(a)).hostname for a in orq.comandos(roteiro)}
    assert hosts | set(barreiras) <= conhecidos

    class Qualquer(dict):
        def __missing__(self, host):
            return {"robots": (200, b"User-agent: *\nDisallow:\n", "text/plain"), "rota": (200, b"{}", "application/json")}

    falso = Falso(Qualquer())
    rel = orq.orquestrar(roteiro, tmp_path, barreiras=barreiras, hosts=hosts, somente_robots=True, executor=falso)
    pedidas = _urls(falso)
    assert sorted(urlsplit(u).hostname for u in pedidas) == sorted(hosts)
    assert all(urlsplit(u).path == "/robots.txt" for u in pedidas) and len(pedidas) == len(set(pedidas))
    assert sorted(rel["hosts"]) == sorted(hosts)
