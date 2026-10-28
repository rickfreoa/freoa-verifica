"""Manifesto de aceite do plano 1.4.0 (I1.5): validação e registro offline, só stdlib.

O manifesto (release/acceptance_manifest.json) guarda, por incremento, os itens, as
oito etapas do critério de conclusão (seção 5 do plano), as reduções de escopo e as
exceções. `validar` e `fechar` impõem os invariantes a a e; cada escrita valida o
manifesto inteiro antes de gravar e grava de forma atômica.

Limite deliberado: o manifesto registra recibos tipados e confere a coerência entre eles
(formatos, igualdades de commit, merge, hashes e digest, arquivos do repositório). Ele não
consulta o GitHub nem a PyPI: a conferência material de run, release, attestation e pacote
publicado é do auditor.

Uso:
    python scripts/manifesto_aceite.py validar
    python scripts/manifesto_aceite.py registrar --incremento I1 --etapa 2_teste --tipo run_ci \
        --campo url=https://github.com/rickfreoa/freoa-verifica/actions/runs/1 \
        --campo commit=<40 hex> --campo conclusao=success [--estado concluida] [--nota ...]
    python scripts/manifesto_aceite.py registrar --incremento I1 --etapa 4_incorporacao --tipo parecer \
        --campo parecer=docs/auditoria/1.4.0/x.md --campo commit_auditado=<40 hex>
    python scripts/manifesto_aceite.py item --incremento I1 --id I1.3 --estado concluido [--nota ...]
    python scripts/manifesto_aceite.py reducao --incremento I1 --item I1.2 --estado reduzido \
        --rotulo ... --registro <caminho> --decisao ... --motivo ...
    python scripts/manifesto_aceite.py rotulo --incremento I1 --texto ...
    python scripts/manifesto_aceite.py fechar --incremento I1

Cada `--campo chave=valor` é repetível; true e false viram booleano; `alertas` é lista (uma
ocorrência por alerta, `alertas=` sozinho é lista vazia). No parecer o sha256 é calculado pelo
`registrar`.

`--manifesto` (padrão release/acceptance_manifest.json) e todo caminho de evidência são relativos
à raiz do repositório (pai de scripts/) e confinados nela: absoluto, `..` que escape, UNC e nomes
de dispositivo do Windows são recusados antes de qualquer acesso ao sistema de arquivos.
Código de saída: 0 ok; 1 manifesto inválido, invariante violado ou erro de leitura; 2 uso.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from contextlib import suppress
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MANIFESTO_PADRAO = "release/acceptance_manifest.json"

REPO_URL = "https://github.com/rickfreoa/freoa-verifica"

ETAPAS = (
    "1_desenvolvimento", "2_teste", "3_commit", "4_incorporacao",
    "5_publicacao", "6_distribuicao", "7_instalacao", "8_execucao",
)
ESTADOS_INCREMENTO = ("aberto", "concluido", "adiado")
ESTADOS_ITEM = ("pendente", "concluido", "reduzido", "adiado")
ESTADOS_ETAPA = ("pendente", "concluida")
TIPOS_EXCECAO = ("tribunal", "funcao")
ESTADOS_EXCECAO = ("bloqueio_externo_documentado", "excluida_pelo_titular")

# Categorias de indisponibilidade aceitas num alerta do doctor (as de
# freoa_verifica.connectors.base.CATEGORIAS_INDISPONIBILIDADE, menos "regressao": regressão não é
# indisponibilidade classificada). Um teste confere a inclusão.
CATEGORIAS_ALERTA = ("ambiental_desafio", "fonte_fora", "recusa_identificado", "resposta_inesperada")

# Recibo por tipo de evidência: campos obrigatórios, nesta ordem, com o tipo de cada um.
CAMPOS_POR_TIPO: dict[str, dict[str, str]] = {
    "especificacao": {"especificacao": "caminho", "ramo": "texto"},
    "run_ci": {"url": "url_run", "commit": "commit", "conclusao": "sucesso"},
    "bateria_live": {"relatorio": "caminho", "commit": "commit"},
    "commit": {"commit": "commit"},
    "parecer": {"parecer": "caminho", "sha256": "sha", "commit_auditado": "commit"},
    "merge": {"commit": "commit"},
    "tag": {"tag": "tag", "commit": "commit"},
    "release": {"url": "url_release", "attestation_verificada": "verdadeiro",
                "sha256_wheel": "sha", "sha256_sdist": "sha"},
    "pypi": {"versao": "versao", "sha256_wheel": "sha", "sha256_sdist": "sha"},
    "snapshot": {"sha256": "sha", "bateria_s4": "aprovada", "lista_embutida_commit": "commit"},
    "instalacao": {"concluida": "verdadeiro", "commit": "commit", "attestation_verificada": "verdadeiro",
                   "digest_snapshot": "sha"},
    "doctor": {"ok": "verdadeiro", "alertas": "alertas"},
}
TIPOS_EVIDENCIA = tuple(CAMPOS_POR_TIPO)

# Tipos de evidência de cada etapa; a etapa concluída exige exatamente um de cada.
TIPOS_DA_ETAPA = {
    "1_desenvolvimento": ("especificacao",),
    "2_teste": ("run_ci", "bateria_live"),
    "3_commit": ("commit",),
    "4_incorporacao": ("parecer", "merge"),
    "5_publicacao": ("tag", "release", "pypi"),
    "6_distribuicao": ("snapshot",),
    "7_instalacao": ("instalacao",),
    "8_execucao": ("doctor", "bateria_live"),
}
SEM_BLOQUEADOR = "SEM BLOQUEADOR"

CHAVES_RAIZ = ("plano", "atualizado_em", "incrementos", "excecoes")
CHAVES_INCREMENTO = ("id", "versao", "estado", "rotulo", "itens", "etapas", "reducoes_de_escopo")
CHAVES_ITEM = ("id", "estado", "nota")
CHAVES_ETAPA = ("estado", "evidencias", "nota")
CHAVES_EVIDENCIA = ("tipo", "campos", "data")
CHAVES_REDUCAO = ("item", "data", "decisao", "registro", "motivo")
CHAVES_EXCECAO = ("alvo", "tipo", "estado", "revisar_em", "registro", "nota")

_A = re.ASCII
DATA = re.compile(r"\d{4}-\d{2}-\d{2}", _A)
DATAHORA = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", _A
)
SHA256 = re.compile(r"[0-9a-f]{64}", _A)
COMMIT = re.compile(r"[0-9a-f]{40}", _A)
TAG = re.compile(r"v\d+\.\d+\.\d+(?:a\d+)?", _A)
VERSAO = re.compile(r"\d+\.\d+\.\d+(?:a\d+)?", _A)
URL_RUN = re.compile(re.escape(REPO_URL) + r"/actions/runs/\d+", _A)
URL_RELEASE = re.compile(re.escape(REPO_URL) + r"/releases/tag/(v\d+\.\d+\.\d+(?:a\d+)?)", _A)
DISPOSITIVO_WINDOWS = re.compile(
    r"(?:con|prn|aux|nul|conin\$|conout\$|clock\$|com[0-9\u00b9\u00b2\u00b3]|lpt[0-9\u00b9\u00b2\u00b3])(?:\..*)?",
    re.IGNORECASE,
)


class ErroAceite(ValueError):
    """Manifesto inválido, invariante violado ou erro de leitura. A mensagem pode ter várias linhas."""



# ---------------------------------------------------------------- caminhos confinados


def confinar(ref: object, raiz: Path) -> Path:
    """Resolve `ref` dentro de `raiz` ou levanta ErroAceite.

    As recusas léxicas (vazio, absoluto, UNC, unidade ou fluxo alternativo, `..` que escape, nome de
    dispositivo do Windows) ocorrem ANTES de qualquer acesso ao sistema de arquivos; só depois o
    caminho é resolvido para recusar symlink que saia da raiz. O arquivo pode não existir."""
    if not isinstance(ref, str) or not ref.strip():
        raise ErroAceite("caminho vazio ou não textual")
    if any(ord(c) < 32 for c in ref):
        raise ErroAceite(f"caminho com caractere de controle: {ref!r}")
    if ref.startswith(("\\\\", "//")):
        raise ErroAceite(f"caminho UNC recusado: {ref!r}")
    if ref.startswith(("/", "\\")):
        raise ErroAceite(f"caminho absoluto recusado: {ref!r}")
    if ":" in ref:
        raise ErroAceite(f"caminho com unidade ou fluxo alternativo ('{ref}'): recusado")
    pilha: list[str] = []
    for parte in ref.replace("\\", "/").split("/"):
        if parte in ("", "."):
            continue
        if parte == "..":
            if not pilha:
                raise ErroAceite(f"caminho escapa da raiz do repositório: {ref!r}")
            pilha.pop()
            continue
        if parte != parte.rstrip(" ."):
            raise ErroAceite(f"componente de caminho terminado em ponto ou espaço: {ref!r}")
        if DISPOSITIVO_WINDOWS.fullmatch(parte):
            raise ErroAceite(f"nome de dispositivo do Windows recusado: {ref!r}")
        pilha.append(parte)
    if not pilha:
        raise ErroAceite(f"caminho aponta para a própria raiz: {ref!r}")
    base = raiz.resolve()
    destino = (base / "/".join(pilha)).resolve()
    try:
        destino.relative_to(base)
    except ValueError as exc:
        raise ErroAceite(f"caminho sai da raiz do repositório por link: {ref!r}") from exc
    return destino


def arquivo_do_repositorio(ref: object, raiz: Path) -> Path:
    destino = confinar(ref, raiz)
    if not destino.is_file():
        raise ErroAceite(f"arquivo inexistente no repositório: {ref!r}")
    return destino


# ---------------------------------------------------------------- estrutura


def _chaves(obj: object, esperadas: tuple[str, ...], cam: str, erros: list[str]) -> bool:
    """Exige exatamente as chaves esperadas num objeto."""
    if not isinstance(obj, dict):
        erros.append(f"{cam}: deve ser um objeto")
        return False
    faltam = [k for k in esperadas if k not in obj]
    sobram = [k for k in obj if k not in esperadas]
    erros.extend(f"{cam}: falta o campo '{k}'" for k in faltam)
    erros.extend(f"{cam}: campo não previsto '{k}'" for k in sobram)
    return not faltam and not sobram


def _lista(valor: object, cam: str, erros: list[str]) -> bool:
    if not isinstance(valor, list):
        erros.append(f"{cam}: deve ser uma lista")
        return False
    return True


def _texto(valor: object, cam: str, erros: list[str], *, vazio_ok: bool = False) -> None:
    if not isinstance(valor, str) or (not vazio_ok and not valor.strip()):
        erros.append(f"{cam}: deve ser texto não vazio")


def _enum(valor: object, opcoes: tuple[str, ...], cam: str, erros: list[str]) -> None:
    if valor not in opcoes:
        erros.append(f"{cam}: '{valor}' não é valor válido ({', '.join(opcoes)})")


def _data(valor: object, cam: str, erros: list[str]) -> None:
    ok = isinstance(valor, str) and DATA.fullmatch(valor) is not None
    if ok:
        try:
            dt.date.fromisoformat(valor)  # type: ignore[arg-type]
        except ValueError:
            ok = False
    if not ok:
        erros.append(f"{cam}: data ISO inválida (AAAA-MM-DD): {valor!r}")


def _datahora(valor: object, cam: str, erros: list[str]) -> None:
    """Instante RFC 3339 completo: segundos e fuso Z ou ±HH:MM (HH até 23, MM até 59)."""
    ok = isinstance(valor, str) and DATAHORA.fullmatch(valor) is not None
    if ok:
        try:
            dt.datetime.fromisoformat(valor.replace("Z", "+00:00"))  # type: ignore[union-attr]
        except ValueError:
            ok = False
    if not ok:
        erros.append(f"{cam}: instante RFC 3339 inválido (AAAA-MM-DDTHH:MM:SS e fuso Z ou ±HH:MM): {valor!r}")


def _erro_de_alerta(alerta: object) -> str | None:
    if not isinstance(alerta, str):
        return "alerta deve ser texto"
    categoria, sep, resto = alerta.partition(":")
    if not sep or categoria not in CATEGORIAS_ALERTA or not resto.strip():
        return f"alerta sem categoria de indisponibilidade ({', '.join(CATEGORIAS_ALERTA)}): {alerta!r}"
    return None


def _erro_de_campo(tipo: str, valor: object) -> str | None:
    """Mensagem de erro quando o valor não tem o formato do tipo de campo; None quando tem."""
    if tipo == "caminho":
        return None if isinstance(valor, str) and valor.strip() else "deve ser texto não vazio (caminho)"
    if tipo == "texto":
        return None if isinstance(valor, str) and valor.strip() else "deve ser texto não vazio"
    padroes = {
        "commit": (COMMIT, "deve ter 40 hex minúsculos"),
        "sha": (SHA256, "deve ter 64 hex minúsculos"),
        "url_run": (URL_RUN, f"deve ser {REPO_URL}/actions/runs/<n>"),
        "url_release": (URL_RELEASE, f"deve ser {REPO_URL}/releases/tag/<tag>"),
        "tag": (TAG, "deve ter o formato vX.Y.Z ou vX.Y.ZaN"),
        "versao": (VERSAO, "deve ter o formato X.Y.Z ou X.Y.ZaN"),
    }
    if tipo in padroes:
        padrao, msg = padroes[tipo]
        return None if isinstance(valor, str) and padrao.fullmatch(valor) else msg
    if tipo == "sucesso":
        return None if valor == "success" else "deve ser 'success'"
    if tipo == "aprovada":
        return None if valor == "aprovada" else "deve ser 'aprovada'"
    if tipo == "verdadeiro":
        return None if valor is True else "deve ser o booleano true"
    if tipo == "alertas":
        if not isinstance(valor, list):
            return "deve ser uma lista de textos"
        for alerta in valor:
            erro = _erro_de_alerta(alerta)
            if erro:
                return erro
        return None
    raise AssertionError(tipo)


def _erros_evidencia(ev: object, cam: str, erros: list[str]) -> None:
    if not _chaves(ev, CHAVES_EVIDENCIA, cam, erros):
        return
    _datahora(ev["data"], f"{cam}.data", erros)
    tipo = ev["tipo"]
    if tipo not in CAMPOS_POR_TIPO:
        erros.append(f"{cam}.tipo: '{tipo}' não é valor válido ({', '.join(TIPOS_EVIDENCIA)})")
        return
    esperados = CAMPOS_POR_TIPO[tipo]
    if not _chaves(ev["campos"], tuple(esperados), f"{cam}.campos", erros):
        return
    for nome, kind in esperados.items():
        msg = _erro_de_campo(kind, ev["campos"][nome])
        if msg:
            erros.append(f"{cam}.campos.{nome}: {msg}")


def _erros_etapa(etapa: object, cam: str, erros: list[str]) -> None:
    if not _chaves(etapa, CHAVES_ETAPA, cam, erros):
        return
    _enum(etapa["estado"], ESTADOS_ETAPA, f"{cam}.estado", erros)
    if _lista(etapa["evidencias"], f"{cam}.evidencias", erros):
        for j, ev in enumerate(etapa["evidencias"]):
            _erros_evidencia(ev, f"{cam}.evidencias[{j}]", erros)
    _texto(etapa["nota"], f"{cam}.nota", erros, vazio_ok=True)


def _erros_item(item: object, cam: str, erros: list[str]) -> None:
    if not _chaves(item, CHAVES_ITEM, cam, erros):
        return
    _texto(item["id"], f"{cam}.id", erros)
    _enum(item["estado"], ESTADOS_ITEM, f"{cam}.estado", erros)
    _texto(item["nota"], f"{cam}.nota", erros, vazio_ok=True)


def _erros_reducao(red: object, cam: str, erros: list[str]) -> None:
    if not _chaves(red, CHAVES_REDUCAO, cam, erros):
        return
    _texto(red["item"], f"{cam}.item", erros)
    _data(red["data"], f"{cam}.data", erros)
    for campo in ("decisao", "registro", "motivo"):
        _texto(red[campo], f"{cam}.{campo}", erros)


def _erros_incremento(inc: object, cam: str, erros: list[str]) -> None:
    if not _chaves(inc, CHAVES_INCREMENTO, cam, erros):
        return
    _texto(inc["id"], f"{cam}.id", erros)
    _texto(inc["versao"], f"{cam}.versao", erros)
    _enum(inc["estado"], ESTADOS_INCREMENTO, f"{cam}.estado", erros)
    if inc["rotulo"] is not None:
        _texto(inc["rotulo"], f"{cam}.rotulo", erros)
    if _lista(inc["itens"], f"{cam}.itens", erros):
        for j, it in enumerate(inc["itens"]):
            _erros_item(it, f"{cam}.itens[{j}]", erros)
    if _chaves(inc["etapas"], ETAPAS, f"{cam}.etapas", erros):
        for nome in ETAPAS:
            _erros_etapa(inc["etapas"][nome], f"{cam}.etapas.{nome}", erros)
    if _lista(inc["reducoes_de_escopo"], f"{cam}.reducoes_de_escopo", erros):
        for j, red in enumerate(inc["reducoes_de_escopo"]):
            _erros_reducao(red, f"{cam}.reducoes_de_escopo[{j}]", erros)


def _erros_excecao(exc: object, cam: str, erros: list[str]) -> None:
    if not _chaves(exc, CHAVES_EXCECAO, cam, erros):
        return
    _texto(exc["alvo"], f"{cam}.alvo", erros)
    _enum(exc["tipo"], TIPOS_EXCECAO, f"{cam}.tipo", erros)
    _enum(exc["estado"], ESTADOS_EXCECAO, f"{cam}.estado", erros)
    _texto(exc["registro"], f"{cam}.registro", erros)
    _texto(exc["nota"], f"{cam}.nota", erros, vazio_ok=True)
    if exc["revisar_em"] is not None:
        _data(exc["revisar_em"], f"{cam}.revisar_em", erros)
        if isinstance(exc["nota"], str) and not exc["nota"].strip():
            erros.append(f"{cam}.nota: revisar_em exige nota com o fundamento da data")


def erros_de_estrutura(m: object) -> list[str]:
    erros: list[str] = []
    if not _chaves(m, CHAVES_RAIZ, "manifesto", erros):
        return erros
    _texto(m["plano"], "manifesto.plano", erros)
    _datahora(m["atualizado_em"], "manifesto.atualizado_em", erros)
    if _lista(m["incrementos"], "manifesto.incrementos", erros):
        for i, inc in enumerate(m["incrementos"]):
            _erros_incremento(inc, f"manifesto.incrementos[{i}]", erros)
    if _lista(m["excecoes"], "manifesto.excecoes", erros):
        for i, exc in enumerate(m["excecoes"]):
            _erros_excecao(exc, f"manifesto.excecoes[{i}]", erros)
    return erros


# ---------------------------------------------------------------- invariantes


def sha256_de(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _ultima_linha_do_parecer(dados: bytes) -> str | None:
    """Última linha não vazia, após remover o BOM inicial e normalizar CRLF e espaços finais."""
    texto = dados.decode("utf-8")
    if texto.startswith("﻿"):
        texto = texto[1:]
    linhas = [ln.rstrip() for ln in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    linhas = [ln for ln in linhas if ln]
    return linhas[-1] if linhas else None


def _motivo_parecer_reprovado(campos: dict, raiz: Path) -> str | None:
    """None quando o parecer aprova: arquivo existente no repositório, sha256 igual ao dos bytes e
    última linha não vazia exatamente 'SEM BLOQUEADOR'. URL não vale. O teto de rodadas não aprova."""
    try:
        arquivo = arquivo_do_repositorio(campos["parecer"], raiz)
        dados = arquivo.read_bytes()
        ultima = _ultima_linha_do_parecer(dados)
    except ErroAceite as exc:
        return str(exc)
    except (OSError, ValueError):
        return "não foi possível ler o arquivo do parecer como UTF-8"
    if hashlib.sha256(dados).hexdigest() != campos["sha256"]:
        return "sha256 registrado difere do sha256 dos bytes do arquivo"
    if ultima != SEM_BLOQUEADOR:
        return f"a última linha não vazia do parecer não é '{SEM_BLOQUEADOR}'"
    return None


def _conferir_etapa(
    inc_id: str, nome: str, etapa: dict, raiz: Path, erros: list[str]
) -> dict[str, dict]:
    """Confere a etapa e devolve os campos da evidência de cada tipo (a primeira de cada)."""
    cam = f"incrementos[{inc_id}].etapas.{nome}"
    permitidos = TIPOS_DA_ETAPA[nome]
    por_tipo: dict[str, dict] = {}
    for ev in etapa["evidencias"]:
        tipo = ev["tipo"]
        if tipo not in permitidos:
            erros.append(f"{cam}: evidência '{tipo}' não pertence a esta etapa ({', '.join(permitidos)})")
        elif tipo in por_tipo:
            erros.append(f"{cam}: evidência '{tipo}' repetida")
        else:
            por_tipo[tipo] = ev["campos"]
    for tipo, campos in por_tipo.items():
        for chave, kind in CAMPOS_POR_TIPO[tipo].items():
            if kind != "caminho" or tipo == "parecer":
                continue
            try:
                arquivo_do_repositorio(campos[chave], raiz)
            except ErroAceite as exc:
                erros.append(f"{cam}: {tipo}.{chave}: {exc}")
    if "parecer" in por_tipo:
        motivo = _motivo_parecer_reprovado(por_tipo["parecer"], raiz)
        if motivo:
            erros.append(f"{cam}: parecer '{por_tipo['parecer']['parecer']}': {motivo}")
    if etapa["estado"] == "concluida":
        for tipo in permitidos:
            if tipo not in por_tipo:
                erros.append(f"{cam}: etapa concluida exige evidência '{tipo}'")
    return por_tipo


def _igual(erros: list[str], cam: str, a: dict | None, ka: str, na: str, b: dict | None, kb: str, nb: str) -> None:
    """Exige a[ka] == b[kb] quando as duas evidências existem."""
    if a is not None and b is not None and a[ka] != b[kb]:
        erros.append(f"{cam}: {na} ({a[ka]}) difere de {nb} ({b[kb]})")


def _erros_de_coerencia(inc: dict, rec: dict[str, dict[str, dict]], erros: list[str]) -> None:
    """Igualdades entre as etapas de um incremento, sobre as evidências presentes."""
    cam = f"incrementos[{inc['id']}]"

    def g(etapa: str, tipo: str) -> dict | None:
        return rec[etapa].get(tipo)

    run, bat2 = g("2_teste", "run_ci"), g("2_teste", "bateria_live")
    com3 = g("3_commit", "commit")
    par, mrg = g("4_incorporacao", "parecer"), g("4_incorporacao", "merge")
    tag, rel, pyp = g("5_publicacao", "tag"), g("5_publicacao", "release"), g("5_publicacao", "pypi")
    snap, ins = g("6_distribuicao", "snapshot"), g("7_instalacao", "instalacao")
    bat8 = g("8_execucao", "bateria_live")

    _igual(erros, cam, bat2, "commit", "2_teste bateria_live.commit", run, "commit", "2_teste run_ci.commit")
    _igual(erros, cam, com3, "commit", "3_commit commit", run, "commit", "2_teste run_ci.commit")
    _igual(erros, cam, par, "commit_auditado", "4_incorporacao parecer.commit_auditado",
           com3, "commit", "3_commit commit")
    _igual(erros, cam, tag, "commit", "5_publicacao tag.commit", mrg, "commit", "4_incorporacao merge.commit")
    if tag is not None and tag["tag"] != f"v{inc['versao']}":
        erros.append(f"{cam}: tag ({tag['tag']}) difere da versão do incremento (v{inc['versao']})")
    if tag is not None and rel is not None:
        achado = URL_RELEASE.fullmatch(rel["url"])
        if achado is None or achado.group(1) != tag["tag"]:
            erros.append(f"{cam}: release.url ({rel['url']}) não é a da tag ({tag['tag']})")
    if tag is not None and pyp is not None and pyp["versao"] != tag["tag"][1:]:
        erros.append(f"{cam}: pypi.versao ({pyp['versao']}) difere da versão da tag ({tag['tag']})")
    for chave in ("sha256_wheel", "sha256_sdist"):
        _igual(erros, cam, pyp, chave, f"pypi.{chave}", rel, chave, f"release.{chave}")
    _igual(erros, cam, ins, "commit", "7_instalacao instalacao.commit", mrg, "commit", "4_incorporacao merge.commit")
    _igual(erros, cam, ins, "digest_snapshot", "instalacao.digest_snapshot", snap, "sha256", "snapshot.sha256")
    _igual(erros, cam, bat8, "commit", "8_execucao bateria_live.commit", mrg, "commit", "4_incorporacao merge.commit")


def _erros_de_reducao(inc: dict, raiz: Path, erros: list[str]) -> None:
    cam = f"incrementos[{inc['id']}]"
    itens = {it["id"]: it for it in inc["itens"]}
    com_reducao = Counter(red["item"] for red in inc["reducoes_de_escopo"])
    for item, n in sorted(com_reducao.items()):
        if n > 1:
            erros.append(f"{cam}: redução repetida para o item '{item}'")
    for red in inc["reducoes_de_escopo"]:
        item = itens.get(red["item"])
        if item is None:
            erros.append(f"{cam}: redução de '{red['item']}', item inexistente no incremento")
        elif item["estado"] not in ("reduzido", "adiado"):
            erros.append(f"{cam}: redução de '{red['item']}', mas o item está '{item['estado']}'")
        try:
            arquivo_do_repositorio(red["registro"], raiz)
        except ErroAceite as exc:
            erros.append(f"{cam}: redução de '{red['item']}': registro: {exc}")
        if inc["rotulo"] is None:
            erros.append(f"{cam}: redução de '{red['item']}' exige rotulo do incremento não nulo")
    for it in inc["itens"]:
        if it["estado"] in ("reduzido", "adiado") and it["id"] not in com_reducao:
            erros.append(f"{cam}: item {it['id']} {it['estado']} exige entrada em reducoes_de_escopo")


def erros_de_regra(m: dict, raiz: Path = RAIZ) -> list[str]:
    """Invariantes a a e, sobre um manifesto de estrutura válida."""
    erros: list[str] = []
    ids = [inc["id"] for inc in m["incrementos"]]
    for dup in sorted(k for k, n in Counter(ids).items() if n > 1):
        erros.append(f"manifesto: id de incremento repetido '{dup}'")
    for inc in m["incrementos"]:
        iid = inc["id"]
        cam = f"incrementos[{iid}]"
        if len({it["id"] for it in inc["itens"]}) != len(inc["itens"]):
            erros.append(f"{cam}: id de item repetido")
        _erros_de_reducao(inc, raiz, erros)
        rec = {nome: _conferir_etapa(iid, nome, inc["etapas"][nome], raiz, erros) for nome in ETAPAS}
        _erros_de_coerencia(inc, rec, erros)
        if inc["estado"] == "concluido":
            for nome in ETAPAS:
                if inc["etapas"][nome]["estado"] != "concluida":
                    erros.append(f"{cam}: incremento concluido com etapa {nome} não concluida")
            for it in inc["itens"]:
                if it["estado"] == "pendente":
                    erros.append(f"{cam}: incremento concluido com item {it['id']} pendente")
    return erros


def erros_do_manifesto(m: object, raiz: Path = RAIZ) -> list[str]:
    erros = erros_de_estrutura(m)
    if erros:
        return erros
    return erros_de_regra(m, raiz)  # type: ignore[arg-type]


# ---------------------------------------------------------------- E/S


def agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def carregar(caminho: Path) -> dict:
    try:
        texto = caminho.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ErroAceite(f"manifesto não encontrado: {caminho}") from exc
    try:
        return json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ErroAceite(f"JSON inválido em {caminho}: {exc}") from exc


def gravar(caminho: Path, manifesto: dict) -> None:
    """Escrita atômica: temporário no mesmo diretório, fsync e os.replace. Falha não corrompe o original."""
    texto = json.dumps(manifesto, ensure_ascii=False, indent=1) + "\n"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=caminho.parent, prefix=f".{caminho.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, caminho)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def _alterar(caminho: Path, raiz: Path, mutacao) -> None:
    """Carrega, aplica a mutação em memória, valida o manifesto inteiro e só então grava."""
    m = carregar(caminho)
    mutacao(m)
    m["atualizado_em"] = agora()
    erros = erros_do_manifesto(m, raiz)
    if erros:
        raise ErroAceite("\n".join(erros))
    gravar(caminho, m)


def _incremento(m: dict, inc_id: str) -> dict:
    for inc in m["incrementos"]:
        if inc["id"] == inc_id:
            return inc
    raise ErroAceite(f"incremento '{inc_id}' não existe")


def _item(inc: dict, item_id: str) -> dict:
    for it in inc["itens"]:
        if it["id"] == item_id:
            return it
    raise ErroAceite(f"item '{item_id}' não existe no incremento {inc['id']}")


def _campos_da_linha(pares: list[tuple[str, str]], tipo: str) -> dict:
    """Converte os `--campo chave=valor`: true/false viram bool; `alertas` acumula numa lista."""
    campos: dict = {}
    for chave, valor in pares:
        if chave == "alertas":
            lista = campos.setdefault("alertas", [])
            if valor != "":
                lista.append(valor)
            continue
        if chave in campos:
            raise ErroAceite(f"campo repetido: {chave}")
        campos[chave] = {"true": True, "false": False}.get(valor, valor)
    return _ordenar(campos, tipo)


def _ordenar(campos: dict, tipo: str) -> dict:
    """Campos previstos na ordem do recibo, depois os não previstos (o validador os recusa)."""
    ordem = list(CAMPOS_POR_TIPO[tipo])
    return {**{k: campos[k] for k in ordem if k in campos}, **{k: v for k, v in campos.items() if k not in ordem}}


# ---------------------------------------------------------------- comandos


def cmd_validar(args: argparse.Namespace, caminho: Path, raiz: Path) -> int:
    m = carregar(caminho)
    erros = erros_do_manifesto(m, raiz)
    if erros:
        raise ErroAceite("\n".join(erros))
    print(f"manifesto válido: {len(m['incrementos'])} incrementos, {len(m['excecoes'])} exceções")
    return 0


def cmd_registrar(args: argparse.Namespace, caminho: Path, raiz: Path) -> int:
    campos = _campos_da_linha(args.campo, args.tipo)
    if args.tipo == "parecer":
        if "sha256" in campos:
            raise ErroAceite("o sha256 do parecer é calculado pelo registrar; não o informe")
        if "parecer" not in campos:
            raise ErroAceite("parecer exige --campo parecer=<caminho no repositório>")
        campos = _ordenar({**campos, "sha256": sha256_de(arquivo_do_repositorio(campos["parecer"], raiz))}, "parecer")

    def mutar(m: dict) -> None:
        etapa = _incremento(m, args.incremento)["etapas"][args.etapa]
        nova = {"tipo": args.tipo, "campos": campos, "data": agora()}
        for j, ev in enumerate(etapa["evidencias"]):
            if ev["tipo"] == args.tipo:  # reenvio do mesmo tipo substitui o anterior
                etapa["evidencias"][j] = nova
                break
        else:
            etapa["evidencias"].append(nova)
        if args.estado is not None:
            etapa["estado"] = args.estado
        if args.nota is not None:
            etapa["nota"] = args.nota

    _alterar(caminho, raiz, mutar)
    print(f"evidência registrada: {args.incremento} {args.etapa} ({args.tipo})")
    return 0


def cmd_item(args: argparse.Namespace, caminho: Path, raiz: Path) -> int:
    def mutar(m: dict) -> None:
        it = _item(_incremento(m, args.incremento), args.id)
        it["estado"] = args.estado
        if args.nota is not None:
            it["nota"] = args.nota

    _alterar(caminho, raiz, mutar)
    print(f"item {args.id}: {args.estado}")
    return 0


def cmd_reducao(args: argparse.Namespace, caminho: Path, raiz: Path) -> int:
    """Marca o item reduzido/adiado, registra a redução e define o rótulo numa só escrita."""
    if not args.rotulo.strip():
        raise ErroAceite("rótulo vazio")

    def mutar(m: dict) -> None:
        inc = _incremento(m, args.incremento)
        _item(inc, args.item)["estado"] = args.estado
        inc["rotulo"] = args.rotulo
        nova = {
            "item": args.item,
            "data": dt.datetime.now(dt.timezone.utc).date().isoformat(),
            "decisao": args.decisao,
            "registro": args.registro,
            "motivo": args.motivo,
        }
        inc["reducoes_de_escopo"] = [r for r in inc["reducoes_de_escopo"] if r["item"] != args.item] + [nova]

    _alterar(caminho, raiz, mutar)
    print(f"redução de escopo registrada: {args.item} ({args.estado})")
    return 0


def cmd_rotulo(args: argparse.Namespace, caminho: Path, raiz: Path) -> int:
    if not args.texto.strip():
        raise ErroAceite("rótulo vazio")

    def mutar(m: dict) -> None:
        _incremento(m, args.incremento)["rotulo"] = args.texto

    _alterar(caminho, raiz, mutar)
    print(f"rótulo de {args.incremento}: {args.texto}")
    return 0


def cmd_fechar(args: argparse.Namespace, caminho: Path, raiz: Path) -> int:
    m = carregar(caminho)
    erros = erros_do_manifesto(m, raiz)  # valida sempre, inclusive o incremento já concluído
    if erros:
        raise ErroAceite("\n".join(erros))
    inc = _incremento(m, args.incremento)
    if inc["estado"] == "concluido":
        print(f"{args.incremento} já está concluído e o manifesto é válido")
        return 0
    if inc["estado"] != "aberto":
        raise ErroAceite(f"{args.incremento} está '{inc['estado']}', não pode ser fechado")

    def mutar(mm: dict) -> None:
        _incremento(mm, args.incremento)["estado"] = "concluido"

    _alterar(caminho, raiz, mutar)
    print(f"{args.incremento} concluído")
    return 0


def _par_campo(texto: str) -> tuple[str, str]:
    chave, sep, valor = texto.partition("=")
    if not sep or not chave.strip():
        raise argparse.ArgumentTypeError(f"esperado chave=valor, recebido {texto!r}")
    return chave.strip(), valor


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Manifesto de aceite do plano 1.4.0 (offline).")
    ap.add_argument("--manifesto", default=MANIFESTO_PADRAO,
                    help="caminho do manifesto, relativo à raiz do repositório e confinado nela")
    sub = ap.add_subparsers(dest="comando", required=True)

    sub.add_parser("validar", help="valida o manifesto inteiro").set_defaults(func=cmd_validar)

    r = sub.add_parser("registrar", help="registra o recibo de uma etapa")
    r.add_argument("--incremento", required=True)
    r.add_argument("--etapa", required=True, choices=ETAPAS)
    r.add_argument("--tipo", required=True, choices=TIPOS_EVIDENCIA)
    r.add_argument("--campo", action="append", default=[], type=_par_campo, metavar="CHAVE=VALOR",
                   help="campo do recibo; repetível; true e false viram booleano")
    r.add_argument("--estado", choices=ESTADOS_ETAPA)
    r.add_argument("--nota")
    r.set_defaults(func=cmd_registrar)

    i = sub.add_parser("item", help="define o estado de um item")
    i.add_argument("--incremento", required=True)
    i.add_argument("--id", required=True)
    i.add_argument("--estado", required=True, choices=ESTADOS_ITEM)
    i.add_argument("--nota")
    i.set_defaults(func=cmd_item)

    d = sub.add_parser("reducao", help="reduz ou adia um item: estado, registro e rótulo numa escrita")
    d.add_argument("--incremento", required=True)
    d.add_argument("--item", required=True)
    d.add_argument("--estado", choices=("reduzido", "adiado"), default="reduzido")
    d.add_argument("--rotulo", required=True)
    d.add_argument("--registro", required=True, help="caminho no repositório")
    d.add_argument("--decisao", required=True)
    d.add_argument("--motivo", required=True)
    d.set_defaults(func=cmd_reducao)

    o = sub.add_parser("rotulo", help="define o rótulo do incremento")
    o.add_argument("--incremento", required=True)
    o.add_argument("--texto", required=True)
    o.set_defaults(func=cmd_rotulo)

    f = sub.add_parser("fechar", help="marca o incremento como concluído, se os invariantes valem")
    f.add_argument("--incremento", required=True)
    f.set_defaults(func=cmd_fechar)
    return ap


def main(argv: list[str] | None = None, *, _raiz: Path | None = None) -> int:
    """`_raiz` é interno (testes apontam a raiz para um diretório temporário); a CLI não o expõe."""
    args = _parser().parse_args(argv)
    raiz = RAIZ if _raiz is None else _raiz
    try:
        caminho = confinar(args.manifesto, raiz)
        return args.func(args, caminho, raiz)
    except ErroAceite as exc:
        for linha in str(exc).splitlines():
            print(f"manifesto_aceite: {linha}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
