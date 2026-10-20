#!/usr/bin/env python3
"""Mantém a issue viva `saude-das-fontes` a partir de `saude-fontes.json` (decisão 0054).

Códigos de saída: 0 tudo ok ou só indisponibilidade ambiental; 1 há `regressao` ou `recusa_identificado`;
2 erro do próprio script (inclui falha da API); 3 execução incompleta (JSON ausente, truncado ou
`completa` falso, JUnit pedido e ausente, ou contradição entre `completa`, fontes e testes; a issue não é
tocada nem a API chamada).

A API do GitHub é usada por `gh api`; o token vem do ambiente (`GH_TOKEN`), nunca do código.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROTULO = "saude-das-fontes"
TITULO = "Saúde das fontes oficiais"
_MARCADOR = re.compile(r"<!-- estado: (\{.*?\}) -->", re.S)
_EXECUCAO = re.compile(r"<!-- execucao: (\{.*?\}) -->", re.S)
_ESTADOS = {"ok", "unavailable", "regressao", "not_run"}
_PRIORIDADE = ("regressao", "unavailable", "not_run", "ok")  # igual à de tests/live/conftest.py

EXIT_OK, EXIT_REGRESSAO, EXIT_ERRO, EXIT_INCOMPLETA = 0, 1, 2, 3


class Incompleta(Exception):
    """Relatório ausente, ilegível ou de execução incompleta."""


class GhErro(Exception):
    """Falha da API do GitHub."""


def gh_api(metodo: str, caminho: str, corpo: dict | None = None):
    cmd = ["gh", "api", "-X", metodo, caminho] + (["--input", "-"] if corpo is not None else [])
    try:
        r = subprocess.run(cmd, input=json.dumps(corpo) if corpo is not None else None,
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhErro(str(exc)) from exc
    if r.returncode:
        raise GhErro(r.stderr.strip()[:300] or f"gh saiu com {r.returncode}")
    try:
        return json.loads(r.stdout) if r.stdout.strip() else None
    except json.JSONDecodeError as exc:
        raise GhErro("resposta da API não é JSON") from exc


def _sem_contradicao(fontes: dict) -> None:
    """`completa: true` não convive com fonte ou teste `not_run`, nem com estado de fonte que ignora seus testes."""
    for nome, f in fontes.items():
        testes = f.get("testes") or []
        estados = [t.get("estado") if isinstance(t, dict) else None for t in testes]
        if f["estado"] == "not_run" or "not_run" in estados:
            raise Incompleta(f"completa=true com {nome} not_run")
        if any(e not in _ESTADOS for e in estados):
            raise Incompleta(f"teste de {nome} sem estado final")
        if estados and min(estados, key=_PRIORIDADE.index) != f["estado"]:
            raise Incompleta(f"estado de {nome} contradiz seus testes")


def carregar(caminho: Path, junit: Path | None) -> dict:
    try:
        rel = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Incompleta(f"relatório ausente ou ilegível: {exc.__class__.__name__}") from exc
    fontes = rel.get("fontes") if isinstance(rel, dict) else None
    if (not isinstance(fontes, dict) or not fontes or rel.get("completa") is not True
            or any(not isinstance(f, dict) or f.get("estado") not in _ESTADOS for f in fontes.values())):
        raise Incompleta("relatório inválido ou com completa != true")
    _sem_contradicao(fontes)
    if junit is not None:
        if not junit.exists():  # XML pedido e ausente: o runner não terminou o que devia registrar
            raise Incompleta("JUnit solicitado e ausente")
        try:
            raiz = ET.parse(junit).getroot()
        except ET.ParseError as exc:
            raise Incompleta("JUnit truncado") from exc
        falhas = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in
                     ([raiz] if raiz.tag == "testsuite" else raiz.iter("testsuite")))
        if falhas and not any(f["estado"] == "regressao" for f in fontes.values()):
            raise Incompleta("JUnit registra falhas que o JSON não registra")
    return rel


def conjunto(rel: dict) -> dict:
    """O que decide comentário: (fonte, estado, categoria); motivo e hora não entram."""
    return {n: [f["estado"], f.get("categoria")] for n, f in sorted(rel["fontes"].items())}


def saida(rel: dict) -> int:
    bad = any(f["estado"] == "regressao" or f.get("categoria") == "recusa_identificado"
              for f in rel["fontes"].values())
    return EXIT_REGRESSAO if bad else EXIT_OK


def _celula(v) -> str:
    return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")[:200]


def corpo(rel: dict, atual: dict) -> str:
    linhas = ["| Fonte | Estado | Categoria | Motivo |", "|---|---|---|---|"]
    for n, f in sorted(rel["fontes"].items()):
        linhas.append(f"| {_celula(n)} | {f['estado']} | {_celula(f.get('categoria'))} | {_celula(f.get('motivo'))} |")
    return "\n".join([
        f"Commit: `{rel.get('commit')}` · Execução: {rel.get('fim')}", "", *linhas, "",
        f"<!-- estado: {json.dumps(atual, sort_keys=True, ensure_ascii=False)} -->",
        f"<!-- execucao: {json.dumps({'run_id': rel.get('run_id'), 'inicio': rel.get('inicio')}, sort_keys=True)} -->",
    ])


def _execucao(texto: str | None) -> dict:
    m = _EXECUCAO.search(texto or "")
    try:
        return json.loads(m.group(1)) if m else {}
    except json.JSONDecodeError:
        return {}


def _posterior(gravado, nosso) -> bool:
    """O `inicio` gravado é posterior ao nosso? Sem `inicio` gravado (corpo antigo), nunca."""
    if not gravado:
        return False
    try:
        return datetime.fromisoformat(gravado) > datetime.fromisoformat(nosso)
    except (TypeError, ValueError):
        return str(gravado) > str(nosso)


def _anterior(texto: str | None) -> dict | None:
    m = _MARCADOR.search(texto or "")
    try:
        return json.loads(m.group(1)) if m else None
    except json.JSONDecodeError:
        return None


def _mudancas(antes: dict | None, depois: dict) -> str:
    antes = antes or {}
    return "\n".join(
        f"- `{n}`: {antes.get(n, 'sem registro')} → {depois.get(n, 'removida')}"
        for n in sorted(set(antes) | set(depois)) if antes.get(n) != depois.get(n)
    ) or "- estado anterior ilegível"


def _issue_aberta(gh, repo: str) -> dict | None:
    achadas = gh("GET", f"repos/{repo}/issues?labels={ROTULO}&state=open&per_page=10") or []
    achadas = [i for i in achadas if "pull_request" not in i]
    return min(achadas, key=lambda i: i["number"]) if achadas else None


def atualizar_issue(gh, repo: str, rel: dict) -> str:
    atual = conjunto(rel)
    texto = corpo(rel, atual)
    issue = _issue_aberta(gh, repo)
    if issue is None:
        gh("POST", f"repos/{repo}/issues", {"title": TITULO, "body": texto, "labels": [ROTULO]})
        return "issue criada"
    # Outra execução pode ter escrito desde a primeira leitura: relê imediatamente antes de decidir e escrever.
    issue = gh("GET", f"repos/{repo}/issues/{issue['number']}") or issue
    if _posterior(_execucao(issue.get("body")).get("inicio"), rel.get("inicio")):
        # Execução mais nova já gravou: escrever o nosso resultado antigo apagaria o dela (B2-08).
        return "issue não escrita: o estado gravado é de execução posterior"
    antes = _anterior(issue.get("body"))
    comentou = antes != atual
    # Comentário antes do corpo: se o PATCH falhar, o estado antigo permanece e a próxima execução repete.
    if comentou:
        gh("POST", f"repos/{repo}/issues/{issue['number']}/comments",
           {"body": f"Mudança no estado das fontes (commit `{rel.get('commit')}`):\n\n{_mudancas(antes, atual)}"})
    gh("PATCH", f"repos/{repo}/issues/{issue['number']}", {"body": texto})
    return "issue atualizada, com comentário" if comentou else "issue atualizada, sem comentário"


def main(argv: list[str] | None = None, gh=gh_api) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", type=Path, default=Path("saude-fontes.json"))
    ap.add_argument("--junit", type=Path, default=None)
    ap.add_argument("--issue", action="store_true", help="atualiza a issue viva via `gh api`")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    args = ap.parse_args(argv)
    try:
        rel = carregar(args.json, args.junit)
    except Incompleta as exc:
        print(f"execução incompleta: {exc}; issue intocada", file=sys.stderr)
        return EXIT_INCOMPLETA
    try:
        for n, f in sorted(rel["fontes"].items()):
            print(f"{n}: {f['estado']} {f.get('categoria') or ''} {f.get('motivo') or ''}".rstrip())
        if args.issue:
            if not args.repo:
                raise GhErro("repositório não informado (--repo ou GITHUB_REPOSITORY)")
            print(atualizar_issue(gh, args.repo, rel))
        return saida(rel)
    except (GhErro, KeyError, TypeError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return EXIT_ERRO


if __name__ == "__main__":
    sys.exit(main())
