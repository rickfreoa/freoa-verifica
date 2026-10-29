"""Orquestrador oficial da S0: executa o roteiro `docs/S0-SONDAS.md` SÓ pelo instrumento e aplica a regra do robots.txt.

A regra é a da decisão 0071 (RFC 9309), implementada em `freoa_verifica.robots_s0`: o `robots.txt` de cada host é o
primeiro comando dele e é pedido UMA vez por host; a leitura decide se o host segue (regras obedecidas ou sem
restrições) ou para (barreira). Um pedido por URL; nenhuma repetição, nem após barreira, nem após erro do
instrumento. O orquestrador não faz rede: cada pedido é um `scripts/capturar_fixture.py` do roteiro, com os mesmos
argumentos, trocando só a pasta de saída (`--saida` do roteiro vira `<saida>/<última pasta>`).

Antes de cada pedido o orquestrador adquire a URL, com criação exclusiva, no registro de tentativas por URL
(`FV_S0_TENTATIVAS` ou `~/.freoa-verifica/s0-tentativas`, fora de qualquer pasta de saída). URL já adquirida nunca
recebe outro pedido: se a captura dela existe (nesta ou em outra saída), é reaproveitada; se não existe (falha de
gravação, queda), o host para. Trocar a saída ou a chave não reabre a URL. O limite é o do registro: outro usuário,
outra máquina ou outro `FV_S0_TENTATIVAS` não o enxergam.

Uso:
    python scripts/s0_orquestrar.py --roteiro docs/S0-SONDAS.md --saida <pasta fora do repositório> \\
        [--barreiras barreiras.json] [--hosts h1,h2 | --hosts-arquivo hosts.json] [--somente-robots] \\
        [--relatorio relatorio.json]

`--barreiras`: JSON `{"<host>": "<descrição e onde está o registro>"}` com os hosts que já deram barreira ao produto:
não recebem nenhum pedido. `--hosts`/`--hosts-arquivo`: restringe a rodada a esses hosts (a rodada 2 da S0b refaz só
os hosts cuja parada da rodada 1 decorreu da regra antiga). `--somente-robots`: só o `robots.txt` de cada host.
Caminhos no relatório: a pasta de saída aparece como `<saida>`, o checkout como `<repo>`, o interpretador como
`<python>`, a casa do usuário como `<home>`. Do traceback do instrumento entram só os quadros (caminho por
marcador, linha, função) e a última linha (a exceção); código-fonte e texto intermediário não entram.
Limitação declarada: na última linha e na saída sem traceback, a troca é por padrão textual; ficam caminho de um só componente
(`/x`, igual a caminho de URL), caminho não citado que contenha espaço (o trecho depois do espaço) e caminho entre
aspas simples com apóstrofo (o trecho depois do apóstrofo).
"""

from __future__ import annotations

import argparse
import hashlib
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
    """Troca textual de caminhos por marcadores, usada só na última linha e na saída sem traceback (`_relato`).
    Citado entre aspas duplas sai inteiro como `<caminho>`; a pasta de saída vira `<saida>`; o checkout, o
    interpretador e a casa do usuário, `<repo>`, `<python>`, `<home>`; outro caminho absoluto, `<caminho>`. Limites no
    docstring do módulo.
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


def _dir_tentativas() -> Path:
    """Registro de tentativas por URL, fora de qualquer pasta de saída: `FV_S0_TENTATIVAS` ou `~/.freoa-verifica/s0-tentativas`."""
    return Path(os.environ.get("FV_S0_TENTATIVAS") or Path.home() / ".freoa-verifica" / "s0-tentativas")


def _adquirir_tentativa(registro: Path, url: str, caminho: Path) -> tuple[Path | None, str | None]:
    """(captura a reaproveitar, None) | (None, razão de parada) | (None, None) = tentativa adquirida, pode pedir.

    Criação exclusiva (`O_CREAT | O_EXCL`): duas execuções concorrentes não adquirem a mesma URL. Entrada existente
    aponta para a captura que a URL produziu; se ela não existe, houve pedido sem registro e o host para.
    """
    if caminho.exists():
        return caminho, None
    entrada = registro / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json")
    try:
        registro.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # inclusive FileExistsError de um arquivo no caminho do registro
        return None, f"tentativa não adquirida ({type(exc).__name__})"
    try:
        fd = os.open(entrada, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            anterior = Path(json.loads(entrada.read_text(encoding="utf-8"))["captura"])
        except (OSError, ValueError, KeyError, TypeError):
            return None, "tentativa anterior com registro ilegível"
        if anterior.exists():
            return anterior, None
        return None, "tentativa anterior sem registro"
    except OSError as exc:
        return None, f"tentativa não adquirida ({type(exc).__name__})"
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"url": url, "captura": str(caminho), "inicio": datetime.now(timezone.utc).isoformat()}, f)
    return None, None


_QUADRO = re.compile(r'^(\s*)File "(.+)", line (\d+)(?:, in (.+))?$')


def _caminho_estrutural(caminho: str, base: Path) -> str:
    """Caminho de quadro de traceback: só marcadores; sob a saída ou o checkout fica o trecho relativo."""
    normal = caminho.replace("\\", "/")
    for raiz, marcador in [(str(base).replace("\\", "/"), "<saida>"), (str(_RAIZ_DO_REPO).replace("\\", "/"), "<repo>")]:
        if normal.startswith(raiz + "/"):
            return marcador + normal[len(raiz):]
    for raiz, marcador in _raizes():
        if normal.startswith(raiz.replace("\\", "/") + "/") and marcador in ("<python>",):
            return marcador + "/..."
    return "<caminho>"


def _relato(texto: str, base: Path) -> str:
    """O que vai ao relatório: a estrutura do traceback (quadros com caminho por marcador, linha e função) e a última
    linha (a exceção), saneada por `_limpo`. Linhas de código-fonte e texto livre intermediário não entram.

    I2.7 r2 (parecer PR #20 r1, I1; registro do adiamento do PR #18): sanitização por estrutura. Sem traceback,
    entram só as três últimas linhas, saneadas (limitação declarada no docstring do módulo).
    """
    linhas = [ln for ln in texto.strip().splitlines() if ln.strip()]
    quadros = [(i, _QUADRO.match(ln)) for i, ln in enumerate(linhas)]
    if not any(m for _, m in quadros):
        return _limpo("\n".join(linhas[-3:]), base)[-600:]
    saida = ["Traceback (most recent call last):"]
    for _, m in quadros:
        if m:
            funcao = f", in {m.group(4)}" if m.group(4) else ""
            saida.append(f'{m.group(1)}File "{_caminho_estrutural(m.group(2), base)}", line {m.group(3)}{funcao}')
    saida.append(_limpo(linhas[-1], base))
    return "\n".join(saida)[-600:]


def _resumo(leitura) -> dict[str, Any]:
    resumo = {"estado": leitura.estado, "motivo": leitura.motivo, "detalhe": leitura.detalhe,
              "status": leitura.status, "content_type": leitura.content_type, "sha256": leitura.sha256}
    if leitura.charset_legado_em_comentario:
        resumo["charset_legado_em_comentario"] = True
    return resumo


def orquestrar(
    roteiro: str, saida: Path, *, barreiras: Mapping[str, str] | None = None, hosts: set[str] | None = None,
    somente_robots: bool = False, executor: Executor = executar_instrumento, tentativas: Path | None = None,
) -> dict[str, Any]:
    registro_tentativas = tentativas or _dir_tentativas()
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
                # I2.7 r2 (parecer PR #20 r1, B2): a tentativa é adquirida por URL, com criação exclusiva, num registro
                # fora da pasta de saída, ANTES do pedido. Trocar saída ou chave não abre novo pedido à mesma URL.
                origem, razao = _adquirir_tentativa(registro_tentativas, url, caminho)
                if razao:
                    h["parada"] = f"{razao} em {chave}: sem pedido (regra invariável 3)"
                    h["comandos"].append({"chave": chave, "url": url, "executado": False, "razao": h["parada"]})
                    continue
                reaproveitado = origem is not None
                p = SimpleNamespace(returncode=None, stdout="", stderr="") if reaproveitado else executor(novos)
                fonte_reg = origem or caminho
                pasta_reg = fonte_reg.parent
                reg = json.loads(fonte_reg.read_text(encoding="utf-8")) if fonte_reg.exists() else {}
                item = {"chave": chave, "url": url, "executado": not reaproveitado, "reaproveitado": reaproveitado,
                        "rc": p.returncode,
                        "stdout": _relato(p.stdout or "", saida), "stderr": _relato(p.stderr or "", saida),
                        **{k: reg.get(k) for k in CAMPOS_DO_REGISTRO}}
                h["comandos"].append(item)
                if eh_robots:
                    if not reg:
                        leitura = None
                        h["parada"] = f"instrumento sem registro em {chave} (rc={p.returncode}): {item['stderr'][-120:]}"
                        continue
                    corpo = (pasta_reg / reg["arquivo"]).read_bytes() if reg.get("arquivo") else None
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
    ap.add_argument("--tentativas", type=Path, help="registro de tentativas por URL (padrão: FV_S0_TENTATIVAS ou ~/.freoa-verifica/s0-tentativas)")
    args = ap.parse_args(argv)
    barreiras = json.loads(args.barreiras.read_text(encoding="utf-8")) if args.barreiras else {}
    hosts = None
    if args.hosts:
        hosts = {h.strip() for h in args.hosts.split(",") if h.strip()}
    elif args.hosts_arquivo:
        hosts = set(json.loads(args.hosts_arquivo.read_text(encoding="utf-8")))
    args.saida.mkdir(parents=True, exist_ok=True)
    rel = orquestrar(args.roteiro.read_text(encoding="utf-8"), args.saida.resolve(), barreiras=barreiras,
                     hosts=hosts, somente_robots=args.somente_robots, tentativas=args.tentativas)
    destino = args.relatorio or args.saida / "relatorio-s0.json"
    destino.write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({h: (v["parada"] or "ok", sum(c["executado"] for c in v["comandos"]), len(v["comandos"]))
                      for h, v in rel["hosts"].items()}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
