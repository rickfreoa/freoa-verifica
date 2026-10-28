"""Manifesto de aceite do plano 1.4.0 (I1.5): validação e registro offline, só stdlib.

O manifesto (release/acceptance_manifest.json) guarda, por incremento, os itens, as
oito etapas do critério de conclusão (seção 5 do plano), as reduções de escopo e as
exceções. `validar` e `fechar` impõem os invariantes a a e; cada escrita valida o
manifesto inteiro antes de gravar e grava de forma atômica.

Uso:
    python scripts/manifesto_aceite.py validar
    python scripts/manifesto_aceite.py registrar --incremento I1 --etapa 4_incorporacao \
        --tipo parecer --ref docs/auditoria/1.4.0/x.md [--sha256 X] [--estado concluida] [--nota ...]
    python scripts/manifesto_aceite.py item --incremento I1 --id I1.2 --estado reduzido [--nota ...]
    python scripts/manifesto_aceite.py reducao --incremento I1 --item I1.2 --registro <caminho> \
        --decisao ... --motivo ...
    python scripts/manifesto_aceite.py rotulo --incremento I1 --texto ...
    python scripts/manifesto_aceite.py fechar --incremento I1

Opção global `--manifesto <caminho>` (padrão release/acceptance_manifest.json), para os testes.
Código de saída: 0 ok; 1 manifesto inválido, invariante violado ou erro de leitura; 2 uso.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from contextlib import suppress
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MANIFESTO_PADRAO = RAIZ / "release" / "acceptance_manifest.json"

ETAPAS = (
    "1_desenvolvimento", "2_teste", "3_commit", "4_incorporacao",
    "5_publicacao", "6_distribuicao", "7_instalacao", "8_execucao",
)
ESTADOS_INCREMENTO = ("aberto", "concluido", "adiado")
ESTADOS_ITEM = ("pendente", "concluido", "reduzido", "adiado")
ESTADOS_ETAPA = ("pendente", "concluida", "nao_aplicavel")
TIPOS_EVIDENCIA = (
    "commit", "run_ci", "parecer", "tag", "release", "pypi", "snapshot",
    "instalacao", "doctor", "bateria_live", "bench", "outro",
)
TIPOS_EXCECAO = ("tribunal", "funcao")
ESTADOS_EXCECAO = ("bloqueio_externo_documentado", "excluida_pelo_titular")

# Evidências exigidas por etapa concluída (invariante c). A de pypi pode ser dispensada pela nota.
EXIGIDAS = {
    "5_publicacao": ("tag", "release", "pypi"),
    "7_instalacao": ("instalacao",),
    "8_execucao": ("doctor", "bateria_live"),
}
SEM_BLOQUEADOR = "SEM BLOQUEADOR"

CHAVES_RAIZ = ("plano", "atualizado_em", "incrementos", "excecoes")
CHAVES_INCREMENTO = ("id", "versao", "estado", "rotulo", "itens", "etapas", "reducoes_de_escopo")
CHAVES_ITEM = ("id", "estado", "nota")
CHAVES_ETAPA = ("estado", "evidencias", "nota")
CHAVES_EVIDENCIA = ("tipo", "ref", "sha256", "data")
CHAVES_REDUCAO = ("item", "data", "decisao", "registro", "motivo")
CHAVES_EXCECAO = ("alvo", "tipo", "estado", "revisar_em", "registro")

DATA = re.compile(r"\d{4}-\d{2}-\d{2}")
DATAHORA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?")
SHA256 = re.compile(r"[0-9a-f]{64}")
URL = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://")


class ErroAceite(ValueError):
    """Manifesto inválido, invariante violado ou erro de leitura. A mensagem pode ter várias linhas."""


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
    try:
        ok = isinstance(valor, str) and DATA.fullmatch(valor) is not None
        if ok:
            dt.date.fromisoformat(valor)
    except ValueError:
        ok = False
    if not ok:
        erros.append(f"{cam}: data ISO inválida (AAAA-MM-DD): {valor!r}")


def _datahora(valor: object, cam: str, erros: list[str]) -> None:
    try:
        ok = isinstance(valor, str) and DATAHORA.fullmatch(valor) is not None
        if ok:
            dt.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        ok = False
    if not ok:
        erros.append(f"{cam}: data-hora ISO inválida: {valor!r}")


def _sha(valor: object, cam: str, erros: list[str]) -> None:
    """sha256 é 64 hex minúsculos, ou null quando a evidência não o exige."""
    if valor is not None and not (isinstance(valor, str) and SHA256.fullmatch(valor)):
        erros.append(f"{cam}: sha256 deve ter 64 hex minúsculos ou null")


def _erros_evidencia(ev: object, cam: str, erros: list[str]) -> None:
    if not _chaves(ev, CHAVES_EVIDENCIA, cam, erros):
        return
    _enum(ev["tipo"], TIPOS_EVIDENCIA, f"{cam}.tipo", erros)
    _texto(ev["ref"], f"{cam}.ref", erros)
    _sha(ev["sha256"], f"{cam}.sha256", erros)
    _datahora(ev["data"], f"{cam}.data", erros)


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
    if exc["revisar_em"] is not None:
        _data(exc["revisar_em"], f"{cam}.revisar_em", erros)
    _texto(exc["registro"], f"{cam}.registro", erros)


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


def _normaliza(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


def _pypi_dispensado(etapa: dict) -> bool:
    """A etapa 5 dispensa pypi quando a própria nota declara que ele não se aplica."""
    nota = _normaliza(etapa["nota"])
    return "pypi" in nota and "nao aplicavel" in nota


def _motivo_parecer_reprovado(ev: dict) -> str | None:
    """None quando o parecer aprova: arquivo local com SEM BLOQUEADOR na última linha não vazia,
    ou referência URL/inexistente com sha256. O teto de rodadas não aprova."""
    ref = ev["ref"]
    if URL.match(ref):
        caminho = None
    else:
        caminho = Path(ref) if Path(ref).is_absolute() else RAIZ / ref
        if not caminho.is_file():
            caminho = None
    if caminho is None:
        if ev["sha256"] is None:
            return "referência URL ou inexistente exige sha256"
        return None
    try:
        linhas = [ln for ln in caminho.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (OSError, ValueError):
        return "não foi possível ler o arquivo do parecer"
    if not linhas or linhas[-1].strip() != SEM_BLOQUEADOR:
        return f"a última linha não vazia do parecer não é '{SEM_BLOQUEADOR}'"
    return None


def _erros_etapa_concluida(inc_id: str, nome: str, etapa: dict, erros: list[str]) -> None:
    cam = f"incrementos[{inc_id}].etapas.{nome}"
    evs = etapa["evidencias"]
    if etapa["estado"] == "nao_aplicavel":
        if not etapa["nota"].strip():
            erros.append(f"{cam}: etapa nao_aplicavel exige nota")
        return
    if etapa["estado"] != "concluida":
        return
    if not evs:
        erros.append(f"{cam}: etapa concluida exige ao menos uma evidência")
        return
    tipos = {ev["tipo"] for ev in evs}
    if nome == "4_incorporacao":
        pareceres = [ev for ev in evs if ev["tipo"] == "parecer"]
        if not pareceres:
            erros.append(f"{cam}: etapa concluida exige evidência 'parecer'")
        for ev in pareceres:
            motivo = _motivo_parecer_reprovado(ev)
            if motivo:
                erros.append(f"{cam}: parecer '{ev['ref']}': {motivo}")
    if nome == "6_distribuicao" and not any(ev["tipo"] == "snapshot" and ev["sha256"] for ev in evs):
        erros.append(f"{cam}: etapa concluida exige evidência 'snapshot' com sha256")
    for tipo in EXIGIDAS.get(nome, ()):
        if tipo == "pypi" and _pypi_dispensado(etapa):
            continue
        if tipo not in tipos:
            erros.append(f"{cam}: etapa concluida exige evidência '{tipo}'")


def erros_de_regra(m: dict) -> list[str]:
    """Invariantes a a e, sobre um manifesto de estrutura válida."""
    erros: list[str] = []
    ids = [inc["id"] for inc in m["incrementos"]]
    for dup in sorted(k for k, n in Counter(ids).items() if n > 1):
        erros.append(f"manifesto: id de incremento repetido '{dup}'")
    for inc in m["incrementos"]:
        iid = inc["id"]
        cam = f"incrementos[{iid}]"
        itens = {it["id"]: it for it in inc["itens"]}
        if len(itens) != len(inc["itens"]):
            erros.append(f"{cam}: id de item repetido")
        reduzidos = {red["item"] for red in inc["reducoes_de_escopo"]}
        for red in inc["reducoes_de_escopo"]:
            if red["item"] not in itens:
                erros.append(f"{cam}: redução de '{red['item']}', item inexistente no incremento")
        for it in inc["itens"]:
            if it["estado"] in ("reduzido", "adiado"):
                if it["id"] not in reduzidos:
                    erros.append(f"{cam}: item {it['id']} {it['estado']} exige entrada em reducoes_de_escopo")
                if inc["rotulo"] is None:
                    erros.append(f"{cam}: item {it['id']} {it['estado']} exige rotulo não nulo")
        for nome in ETAPAS:
            _erros_etapa_concluida(iid, nome, inc["etapas"][nome], erros)
        if inc["estado"] == "concluido":
            for nome in ETAPAS:
                if inc["etapas"][nome]["estado"] == "pendente":
                    erros.append(f"{cam}: incremento concluido com etapa {nome} pendente")
            for it in inc["itens"]:
                if it["estado"] == "pendente":
                    erros.append(f"{cam}: incremento concluido com item {it['id']} pendente")
    return erros


def erros_do_manifesto(m: object) -> list[str]:
    erros = erros_de_estrutura(m)
    if erros:
        return erros
    return erros_de_regra(m)  # type: ignore[arg-type]


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


def _alterar(caminho: Path, mutacao) -> None:
    """Carrega, aplica a mutação em memória, valida o manifesto inteiro e só então grava."""
    m = carregar(caminho)
    mutacao(m)
    m["atualizado_em"] = agora()
    erros = erros_do_manifesto(m)
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


# ---------------------------------------------------------------- comandos


def cmd_validar(args: argparse.Namespace, caminho: Path) -> int:
    m = carregar(caminho)
    erros = erros_do_manifesto(m)
    if erros:
        raise ErroAceite("\n".join(erros))
    print(f"manifesto válido: {len(m['incrementos'])} incrementos, {len(m['excecoes'])} exceções")
    return 0


def cmd_registrar(args: argparse.Namespace, caminho: Path) -> int:
    def mutar(m: dict) -> None:
        etapa = _incremento(m, args.incremento)["etapas"][args.etapa]
        etapa["evidencias"].append(
            {"tipo": args.tipo, "ref": args.ref, "sha256": args.sha256, "data": agora()}
        )
        if args.estado is not None:
            etapa["estado"] = args.estado
        if args.nota is not None:
            etapa["nota"] = args.nota

    _alterar(caminho, mutar)
    print(f"evidência registrada: {args.incremento} {args.etapa} ({args.tipo})")
    return 0


def cmd_item(args: argparse.Namespace, caminho: Path) -> int:
    def mutar(m: dict) -> None:
        it = _item(_incremento(m, args.incremento), args.id)
        it["estado"] = args.estado
        if args.nota is not None:
            it["nota"] = args.nota

    _alterar(caminho, mutar)
    print(f"item {args.id}: {args.estado}")
    return 0


def cmd_reducao(args: argparse.Namespace, caminho: Path) -> int:
    def mutar(m: dict) -> None:
        _item(_incremento(m, args.incremento), args.item)
        _incremento(m, args.incremento)["reducoes_de_escopo"].append({
            "item": args.item,
            "data": dt.datetime.now(dt.timezone.utc).date().isoformat(),
            "decisao": args.decisao,
            "registro": args.registro,
            "motivo": args.motivo,
        })

    _alterar(caminho, mutar)
    print(f"redução de escopo registrada: {args.item}")
    return 0


def cmd_rotulo(args: argparse.Namespace, caminho: Path) -> int:
    if not args.texto.strip():
        raise ErroAceite("rótulo vazio")

    def mutar(m: dict) -> None:
        _incremento(m, args.incremento)["rotulo"] = args.texto

    _alterar(caminho, mutar)
    print(f"rótulo de {args.incremento}: {args.texto}")
    return 0


def cmd_fechar(args: argparse.Namespace, caminho: Path) -> int:
    m = carregar(caminho)
    inc = _incremento(m, args.incremento)
    if inc["estado"] == "concluido":
        print(f"{args.incremento} já está concluído")
        return 0
    if inc["estado"] != "aberto":
        raise ErroAceite(f"{args.incremento} está '{inc['estado']}', não pode ser fechado")

    def mutar(mm: dict) -> None:
        _incremento(mm, args.incremento)["estado"] = "concluido"

    _alterar(caminho, mutar)
    print(f"{args.incremento} concluído")
    return 0


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Manifesto de aceite do plano 1.4.0 (offline).")
    ap.add_argument("--manifesto", type=Path, default=MANIFESTO_PADRAO, help="caminho do manifesto")
    sub = ap.add_subparsers(dest="comando", required=True)

    sub.add_parser("validar", help="valida o manifesto inteiro").set_defaults(func=cmd_validar)

    r = sub.add_parser("registrar", help="acrescenta evidência a uma etapa")
    r.add_argument("--incremento", required=True)
    r.add_argument("--etapa", required=True, choices=ETAPAS)
    r.add_argument("--tipo", required=True, choices=TIPOS_EVIDENCIA)
    r.add_argument("--ref", required=True, help="caminho no repositório ou URL")
    r.add_argument("--sha256")
    r.add_argument("--estado", choices=ESTADOS_ETAPA)
    r.add_argument("--nota")
    r.set_defaults(func=cmd_registrar)

    i = sub.add_parser("item", help="define o estado de um item")
    i.add_argument("--incremento", required=True)
    i.add_argument("--id", required=True)
    i.add_argument("--estado", required=True, choices=ESTADOS_ITEM)
    i.add_argument("--nota")
    i.set_defaults(func=cmd_item)

    d = sub.add_parser("reducao", help="registra redução de escopo de um item")
    d.add_argument("--incremento", required=True)
    d.add_argument("--item", required=True)
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.func(args, args.manifesto)
    except ErroAceite as exc:
        for linha in str(exc).splitlines():
            print(f"manifesto_aceite: {linha}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
