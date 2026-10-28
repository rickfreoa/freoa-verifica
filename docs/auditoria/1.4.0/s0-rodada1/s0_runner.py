"""Executa o roteiro docs/S0-SONDAS.md SÓ pelo instrumento, aplicando a tabela de parada por host.

Não faz rede: cada pedido é um `python scripts/capturar_fixture.py ...` do roteiro, sem alteração.
Uso (na raiz do checkout feat/sondas-s0): python s0_runner.py docs/S0-SONDAS.md C:/dev/fv14-sondas/relatorio.json
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit

UA_TOKEN = "freoa-verifica"
BARREIRA_ANTERIOR = {  # host: registro da barreira já recebida pelo produto (sem nova tentativa)
    "esaj.tjsp.jus.br": "C:/dev/fv14-sondas/s0_tjsp_volume.captura.json (27/10/2026, ambiental_desafio:desafio_captcha)",
}
URL_DA_CONSULTA = {"tjsp": "https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do",
                   "tjdft": "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"}


def comandos(md: str):
    for bloco in re.findall(r"```powershell\n(.*?)```", md, re.S):  # só blocos liberados
        for linha in bloco.splitlines():
            linha = linha.strip()
            if linha.startswith("python scripts/capturar_fixture.py"):
                yield linha


def args_de(linha: str) -> list[str]:
    return shlex.split(linha, posix=True)[1:]


def opt(a: list[str], nome: str) -> str:
    return a[a.index(nome) + 1]


def main(roteiro: str, saida_rel: str) -> int:
    md = Path(roteiro).read_text(encoding="utf-8")
    por_host: dict[str, list[list[str]]] = {}
    for linha in comandos(md):
        a = args_de(linha)
        url = opt(a, "--url") if "--url" in a else URL_DA_CONSULTA[opt(a, "--conector")]
        por_host.setdefault(urlsplit(url).hostname, []).append(a)
    rel = {"hosts": {}}
    for host, cmds in por_host.items():
        h = rel["hosts"][host] = {"comandos": [], "parada": None}
        robots_ok = None
        if host in BARREIRA_ANTERIOR:
            h["parada"] = f"barreira anterior registrada: {BARREIRA_ANTERIOR[host]}"
        for a in cmds:
            url = opt(a, "--url") if "--url" in a else URL_DA_CONSULTA[opt(a, "--conector")]
            chave, saida = opt(a, "--chave"), Path(opt(a, "--saida"))
            caminho = urlsplit(url).path
            eh_robots = caminho == "/robots.txt"
            if h["parada"]:
                h["comandos"].append({"chave": chave, "url": url, "executado": False, "razao": "host parado"})
                continue
            if eh_robots and any(c.get("executado") and urlsplit(c["url"]).path == "/robots.txt" for c in h["comandos"]):
                h["comandos"].append({"chave": chave, "url": url, "executado": False,
                                      "razao": "robots.txt já lido neste host; sem segundo pedido"})
                continue
            if not eh_robots and robots_ok is None:
                h["parada"] = "robots.txt não foi o primeiro comando do host"
                h["comandos"].append({"chave": chave, "url": url, "executado": False, "razao": h["parada"]})
                continue
            if not eh_robots and not robots_ok.can_fetch(UA_TOKEN, url):
                h["comandos"].append({"chave": chave, "url": url, "executado": False, "razao": "Disallow aplicável"})
                continue
            p = subprocess.run([sys.executable, *a], capture_output=True, text=True, encoding="utf-8")
            reg_path = saida / f"{chave}.captura.json"
            reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {}
            item = {"chave": chave, "url": url, "executado": True, "rc": p.returncode,
                    "stdout": p.stdout.strip()[-300:], "stderr": p.stderr.strip()[-300:],
                    **{k: reg.get(k) for k in ("unavailable", "motivo", "categoria", "status", "content_type",
                                                "bytes", "sha256", "arquivo", "url_final")}}
            h["comandos"].append(item)
            if p.returncode != 0 or reg.get("unavailable") or not reg:
                h["parada"] = f"indisponível ou erro em {chave}: {reg.get('motivo') or p.stderr.strip()[-120:]}"
                continue
            if eh_robots:
                ct = (reg.get("content_type") or "").lower()
                corpo = (saida / reg["arquivo"]) if reg.get("arquivo") else None
                if reg.get("status") != 200 or not ct.startswith("text/plain") or not corpo or not corpo.exists():
                    h["parada"] = f"robots indeterminado ({reg.get('status')}, {ct})"
                    continue
                texto = corpo.read_text(encoding="utf-8", errors="strict")
                if "<html" in texto[:500].lower():
                    h["parada"] = "robots com HTML"
                    continue
                robots_ok = urllib.robotparser.RobotFileParser()
                robots_ok.parse(texto.splitlines())
    Path(saida_rel).write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({h: (v["parada"] or "ok", sum(c["executado"] for c in v["comandos"]), len(v["comandos"]))
                      for h, v in rel["hosts"].items()}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
