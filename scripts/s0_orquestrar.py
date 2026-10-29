"""Orquestrador oficial da S0: executa o roteiro `docs/S0-SONDAS.md` SÓ pelo instrumento e aplica a regra do robots.txt.

A regra é a da decisão 0071 (RFC 9309), implementada em `freoa_verifica.robots_s0`: o `robots.txt` de cada host é o
primeiro comando dele e é pedido UMA vez por host; a leitura decide se o host segue (regras obedecidas ou sem
restrições) ou para (barreira). Um pedido por URL; nenhuma repetição, nem após barreira, nem após erro do
instrumento. O orquestrador não faz rede: cada pedido é um `scripts/capturar_fixture.py` do roteiro, com os mesmos
argumentos, trocando só a pasta de saída (`--saida` do roteiro vira `<saida>/<última pasta>`).

Se `<saida>/<fonte>/<chave>.captura.json` já existe, o orquestrador o lê e não pede de novo: duas execuções sobre a
mesma saída nunca repetem um pedido (a primeira pode ser só `--somente-robots`; a segunda segue com as rotas). Antes de
cada pedido grava `<chave>.tentativa.json`; se numa execução seguinte houver marcador sem `.captura.json` (falha de
gravação ou queda depois do pedido), o host para sem novo pedido.

Uso:
    python scripts/s0_orquestrar.py --roteiro docs/S0-SONDAS.md --saida <pasta fora do repositório> \\
        [--barreiras barreiras.json] [--hosts h1,h2 | --hosts-arquivo hosts.json] [--somente-robots] \\
        [--relatorio relatorio.json]

`--barreiras`: JSON `{"<host>": "<descrição e onde está o registro>"}` com os hosts que já deram barreira ao produto:
não recebem nenhum pedido. `--hosts`/`--hosts-arquivo`: restringe a rodada a esses hosts (a rodada 2 da S0b refaz só
os hosts cuja parada da rodada 1 decorreu da regra antiga). `--somente-robots`: só o `robots.txt` de cada host.
Caminhos no relatório: a pasta de saída aparece como `<saida>`, o checkout como `<repo>`, o interpretador como
`<python>`, a casa do usuário como `<home>`, e caminho absoluto citado entre aspas ou com mais de um componente como
`<caminho>`. Limitação declarada: caminho de um só componente em texto corrido (`/x`) fica, porque é sintaticamente
igual a caminho de URL (`/robots.txt`), ainda que possa conter nome identificador; e caminho entre aspas simples que
contenha apóstrofo pode sair truncado no apóstrofo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
import sys
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from freoa_verifica.robots_s0 import BARREIRA, ler_do_registro

CAPTURAR = Path(__file__).with_name("capturar_fixture.py")
# Comandos `--consulta` do roteiro não levam `--url`: o host e a URL são os do conector.
URL_DA_CONSULTA = {"tjsp": "https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do",
                   "tjdft": "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"}
CAMPOS_DO_REGISTRO = ("unavailable", "motivo", "categoria", "status", "content_type", "bytes", "sha256", "arquivo",
                      "url_final")

Executor = Callable[[list[str]], Any]  # recebe os argumentos do instrumento; devolve algo com returncode/stdout/stderr


def comandos(md: str) -> list[list[str]]:
    """Argumentos (sem o nome do script) de cada comando dos blocos `powershell` liberados do roteiro."""
    saida = []
    for bloco in re.findall(r"```powershell\n(.*?)```", md, re.S):  # blocos `powershell-bloqueado` não rodam
        for linha in bloco.splitlines():
            linha = linha.strip()
            if linha.startswith("python scripts/capturar_fixture.py"):
                saida.append(shlex.split(linha, posix=True)[2:])
    return saida


def _opt(args: list[str], nome: str) -> str:
    return args[args.index(nome) + 1]


def _url(args: list[str]) -> str:
    return _opt(args, "--url") if "--url" in args else URL_DA_CONSULTA[_opt(args, "--conector")]


def _com_saida(args: list[str], base: Path) -> tuple[list[str], Path]:
    """Troca o `--saida` do roteiro (caminho de outra máquina) por `<base>/<última pasta>`."""
    pasta = base / PureWindowsPath(_opt(args, "--saida")).name
    novo = list(args)
    novo[novo.index("--saida") + 1] = str(pasta)
    return novo, pasta


def executar_instrumento(args: list[str]) -> subprocess.CompletedProcess:
    """Único ponto que chama o instrumento (e, por ele, o transporte). Sem shell, sem repetição."""
    return subprocess.run([sys.executable, str(CAPTURAR), *args], capture_output=True, text=True,  # noqa: S603
                          encoding="utf-8")


_RAIZ_DO_REPO = Path(__file__).resolve().parent.parent
_WIN = re.compile(r"(?<![\w])[A-Za-z]:[\\/][^\s\"'<>|,;]*")
_UNC = re.compile(r"(?<![\w/\\:])(?:\\\\|//)[^\s\"'<>|,;\\/]+[\\/][^\s\"'<>|,;]*")
# Caminho absoluto citado entre aspas, inteiro, com espaços (File "/srv/Equipe X/a.py", "\\srv\a b" e unidade com espaços).
_ENTRE_ASPAS_D = re.compile(r'(?<=")(?:/|\\\\|[A-Za-z]:[\\/])[^"\r\n]*(?=")')  # apóstrofo interno não fecha
_ENTRE_ASPAS_S = re.compile(r"(?<=')(?:/|\\\\|[A-Za-z]:[\\/])[^'\r\n]*(?=')")
_POSIX = re.compile(r"(?<![\w/.:<>~-])(?:/[^\s\"'<>|,;:()\[\]/]+){2,}/?|(?<![\w/.:<>~-])~(?:/[^\s\"'<>|,;:()\[\]/]+)+")


def _raizes() -> list[tuple[str, str]]:
    """(caminho, marcador) das raízes conhecidas, das mais longas às mais curtas."""
    brutas = [(_RAIZ_DO_REPO, "<repo>"), (Path(sys.prefix), "<python>"), (Path(sys.base_prefix), "<python>"),
              (Path(sys.executable).parent, "<python>"), (Path.home(), "<home>")]
    vistos: dict[str, str] = {}
    for caminho, marcador in brutas:
        for forma in {str(caminho), str(caminho).replace("\\", "/")}:
            if len(forma) > 1:
                vistos.setdefault(forma, marcador)
    return sorted(vistos.items(), key=lambda par: -len(par[0]))


def _limpo(texto: str, base: Path) -> str:
    """Texto do instrumento com os caminhos de máquina trocados por marcadores (limitação no docstring do módulo):
    citado entre aspas sai inteiro como `<caminho>`; a pasta de saída vira `<saida>`; o checkout, o interpretador e a
    casa do usuário, `<repo>`, `<python>`, `<home>`; outro caminho absoluto (POSIX ou Windows), `<caminho>`.
    O tipo da exceção e a mensagem curta ficam; um traceback inteiro perde só os caminhos."""
    texto = texto.strip()
    # Primeiro o caminho citado, inteiro e com espaços (File "..." dos tracebacks), antes de qualquer raiz conhecida:
    # trocar a raiz antes deixava o resto ("<repo>/Equipe X/a.py"). Passe final PR #18, I1.
    texto = _ENTRE_ASPAS_D.sub("<caminho>", texto)
    texto = _ENTRE_ASPAS_S.sub("<caminho>", texto)
    for forma in sorted({str(base), str(base).replace("\\", "/")}, key=len, reverse=True):
        texto = texto.replace(forma, "<saida>")
    for caminho, marcador in _raizes():
        texto = texto.replace(caminho, marcador)
    texto = _UNC.sub("<caminho>", texto)
    texto = _WIN.sub("<caminho>", texto)
    texto = _POSIX.sub("<caminho>", texto)
    return texto[-300:]


def _gravar_marcador(marcador: Path, url: str) -> None:
    """Grava, ANTES do pedido, que ele vai ocorrer; escrita completa ou nada (arquivo temporário e troca)."""
    marcador.parent.mkdir(parents=True, exist_ok=True)
    tmp = marcador.with_suffix(".tmp")
    tmp.write_text(json.dumps({"url": url, "inicio": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    os.replace(tmp, marcador)


def _resumo(leitura) -> dict[str, Any]:
    resumo = {"estado": leitura.estado, "motivo": leitura.motivo, "detalhe": leitura.detalhe,
              "status": leitura.status, "content_type": leitura.content_type, "sha256": leitura.sha256}
    if leitura.charset_legado_em_comentario:
        resumo["charset_legado_em_comentario"] = True
    return resumo


def orquestrar(
    roteiro: str, saida: Path, *, barreiras: Mapping[str, str] | None = None, hosts: set[str] | None = None,
    somente_robots: bool = False, executor: Executor = executar_instrumento,
) -> dict[str, Any]:
    barreiras = dict(barreiras or {})
    por_host: dict[str, list[list[str]]] = {}
    for args in comandos(roteiro):
        por_host.setdefault(urlsplit(_url(args)).hostname, []).append(args)
    relatorio: dict[str, Any] = {"hosts": {}, "fora_da_rodada": []}
    pedidas: set[str] = set()  # um pedido por URL em toda a execução
    for host, cmds in por_host.items():
        if hosts is not None and host not in hosts:
            relatorio["fora_da_rodada"].append(host)
            continue
        h = relatorio["hosts"][host] = {"comandos": [], "parada": None, "robots": None}
        if host in barreiras:
            h["parada"] = f"barreira anterior registrada: {barreiras[host]}"
        leitura = None
        for args in cmds:
            url, chave = _url(args), _opt(args, "--chave")
            eh_robots = urlsplit(url).path == "/robots.txt"

            def pular(razao: str) -> None:
                h["comandos"].append({"chave": chave, "url": url, "executado": False, "razao": razao})

            if h["parada"]:
                pular("host parado")
            elif url in pedidas:
                pular("URL já pedida; um pedido por URL")
            elif eh_robots and leitura is not None:
                pular("robots.txt já lido neste host; sem segundo pedido")
            elif not eh_robots and leitura is None:
                h["parada"] = "robots.txt não foi o primeiro comando do host"
                pular(h["parada"])
            elif somente_robots and not eh_robots:
                pular("rodada só de robots.txt")
            elif not eh_robots and leitura.decidir(url).acao == "vedado":
                pular("Disallow aplicável: " + leitura.decidir(url).detalhe)
            else:
                pedidas.add(url)
                novos, pasta = _com_saida(args, saida)
                caminho = pasta / f"{chave}.captura.json"
                marcador = pasta / f"{chave}.tentativa.json"
                reaproveitado = caminho.exists()  # evidência já gravada (rodada anterior): nunca um segundo pedido
                if not reaproveitado and marcador.exists():
                    # Passe final PR #18, B2: houve tentativa cujo resultado não foi gravado (falha de escrita, queda);
                    # nunca um segundo pedido automático. O host para.
                    h["parada"] = f"tentativa anterior sem registro em {chave}: sem novo pedido (regra invariável 3)"
                    h["comandos"].append({"chave": chave, "url": url, "executado": False, "razao": h["parada"]})
                    continue
                if not reaproveitado:
                    try:
                        _gravar_marcador(marcador, url)
                    except OSError as exc:
                        h["parada"] = f"marcador de tentativa não gravado em {chave} ({type(exc).__name__}): sem pedido"
                        h["comandos"].append({"chave": chave, "url": url, "executado": False, "razao": h["parada"]})
                        continue
                p = SimpleNamespace(returncode=None, stdout="", stderr="") if reaproveitado else executor(novos)
                reg = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
                item = {"chave": chave, "url": url, "executado": not reaproveitado, "reaproveitado": reaproveitado,
                        "rc": p.returncode,
                        "stdout": _limpo(p.stdout or "", saida), "stderr": _limpo(p.stderr or "", saida),
                        **{k: reg.get(k) for k in CAMPOS_DO_REGISTRO}}
                h["comandos"].append(item)
                if eh_robots:
                    if not reg:
                        leitura = None
                        h["parada"] = f"instrumento sem registro em {chave} (rc={p.returncode}): {item['stderr'][-120:]}"
                        continue
                    corpo = (pasta / reg["arquivo"]).read_bytes() if reg.get("arquivo") else None
                    leitura = ler_do_registro(reg, corpo)
                    h["robots"] = item["robots"] = _resumo(leitura)
                    if leitura.estado == BARREIRA:
                        h["parada"] = f"barreira no robots.txt: {leitura.motivo}"
                elif p.returncode not in (0, None) or reg.get("unavailable") or not reg:
                    h["parada"] = f"indisponível ou erro em {chave}: {reg.get('motivo') or item['stderr'][-120:]}"
    return relatorio


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roteiro", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True, help="pasta fora do repositório (o instrumento recusa dentro)")
    ap.add_argument("--barreiras", type=Path, help='JSON {"<host>": "<descrição>"}: hosts com barreira anterior')
    quais = ap.add_mutually_exclusive_group()
    quais.add_argument("--hosts", help="hosts da rodada, separados por vírgula")
    quais.add_argument("--hosts-arquivo", type=Path, help="JSON com a lista de hosts da rodada")
    ap.add_argument("--somente-robots", action="store_true")
    ap.add_argument("--relatorio", type=Path, help="padrão: <saida>/relatorio-s0.json")
    args = ap.parse_args(argv)
    barreiras = json.loads(args.barreiras.read_text(encoding="utf-8")) if args.barreiras else {}
    hosts = None
    if args.hosts:
        hosts = {h.strip() for h in args.hosts.split(",") if h.strip()}
    elif args.hosts_arquivo:
        hosts = set(json.loads(args.hosts_arquivo.read_text(encoding="utf-8")))
    args.saida.mkdir(parents=True, exist_ok=True)
    rel = orquestrar(args.roteiro.read_text(encoding="utf-8"), args.saida.resolve(), barreiras=barreiras,
                     hosts=hosts, somente_robots=args.somente_robots)
    destino = args.relatorio or args.saida / "relatorio-s0.json"
    destino.write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({h: (v["parada"] or "ok", sum(c["executado"] for c in v["comandos"]), len(v["comandos"]))
                      for h, v in rel["hosts"].items()}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
