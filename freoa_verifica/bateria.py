"""Bateria do snapshot (decisão 0057): confere um acervo antes de exportar e depois de instalar.

Somente leitura: o banco abre com `mode=ro` e nada aqui escreve no home. Não usa `Verifica`
(que aplica migrações e grava registro).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from freoa_verifica import derivados

BANCO = "verifica.sqlite3"
VERSAO_MANIFESTO = 1
_AMOSTRA = 20
_SEM = "(sem valor)"
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
# Estados de sync_state que encerram o item (semente.SyncState.done e metadados de cache).
_CONCLUIDOS = ("capturado", "parseado", "ambiguo", "metadados", "concluido")


def abrir_somente_leitura(home: Path | str) -> sqlite3.Connection:
    banco = Path(home) / BANCO
    if not banco.is_file():
        raise FileNotFoundError(f"banco ausente: {banco}")
    conn = sqlite3.connect(f"{banco.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _contagem(conn: sqlite3.Connection, sql: str) -> dict[str, int]:
    return {str(r[0] if r[0] not in (None, "") else _SEM): r[1] for r in conn.execute(sql).fetchall()}


def _fontes(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    fontes: dict[str, dict[str, int]] = {}
    consultas = {
        "capturas": "SELECT source_id, COUNT(*) FROM capture GROUP BY 1",
        "parseados": "SELECT c.source_id, COUNT(*) FROM parsed_document p JOIN capture c ON c.id=p.capture_id GROUP BY 1",
    }
    for campo, sql in consultas.items():
        for fonte, n in _contagem(conn, sql).items():
            fontes.setdefault(fonte, {"capturas": 0, "documentos": 0, "parseados": 0})[campo] = n
    # Documento = decisão com texto capturado da fonte + obra com captura parseada da fonte.
    docs = (
        "SELECT source_id, SUM(n) FROM ("
        " SELECT c.source_id AS source_id, COUNT(DISTINCT dd.decision_id) AS n"
        " FROM decision_document dd JOIN capture c ON c.id=dd.capture_id GROUP BY 1"
        " UNION ALL"
        " SELECT c.source_id, COUNT(DISTINCT p.work_id)"
        " FROM parsed_document p JOIN capture c ON c.id=p.capture_id WHERE p.work_id IS NOT NULL GROUP BY 1"
        ") GROUP BY 1"
    )
    for fonte, n in _contagem(conn, docs).items():
        fontes.setdefault(fonte, {"capturas": 0, "documentos": 0, "parseados": 0})["documentos"] = n
    return fontes


def _stj(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    base = "SELECT {c}, COUNT(*) FROM decision WHERE court='STJ' GROUP BY 1"
    return {
        "por_orgao": _contagem(conn, base.format(c="organ")),
        "por_mes_publicacao": _contagem(conn, base.format(c="substr(publication_date,1,7)")),
        "por_mes_julgamento": _contagem(conn, base.format(c="substr(judgment_date,1,7)")),
    }


def _recursos_ckan(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT chave, payload_json FROM sync_state WHERE fonte='stj_resource' AND status='capturado' "
                          "ORDER BY chave"):
        try:
            p = json.loads(r["payload_json"] or "{}")
        except ValueError:
            p = {}
        # checkpoint = "resource:<id>:<max_itens>"
        partes = r["chave"].split(":")
        out.append({"id": partes[1] if len(partes) > 2 and partes[0] == "resource" else r["chave"],
                    "nome": p.get("nome") or p.get("mes"), "last_modified": (p.get("meta") or {}).get("last_modified"),
                    "sha256": p.get("sha256"), "n": p.get("n")})
    return out


def _pendencias(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    marcas = ",".join("?" * len(_CONCLUIDOS))
    rows = conn.execute(f"SELECT fonte, chave, status, motivo FROM sync_state WHERE status NOT IN ({marcas}) "
                        "ORDER BY fonte, chave", _CONCLUIDOS).fetchall()
    return [dict(r) for r in rows]


def _fora_do_recorte(conn: sqlite3.Connection, recorte: dict[str, str | None]) -> list[dict[str, Any]]:
    desde, ate = recorte.get("desde"), recorte.get("ate")
    achados = []
    for r in conn.execute("SELECT id, court, judgment_date, publication_date FROM decision ORDER BY id"):
        for campo in ("judgment_date", "publication_date"):
            v = r[campo]
            if not v:
                continue
            d = v[:10]
            if not _ISO.match(d) or (desde and d < desde) or (ate and d > ate):
                achados.append({"id": r["id"], "tribunal": r["court"], "campo": campo, "valor": v})
    return achados


def _blobs(conn: sqlite3.Connection, home: Path) -> dict[str, Any]:
    """Existência, tamanho e sha256 dos blobs referenciados por captura. Somente leitura:
    o caminho é montado aqui porque `store.blobs.blob_path` cria diretórios."""
    problemas: dict[str, list[str]] = {"ausentes": [], "tamanho_divergente": [], "hash_divergente": []}
    vistos = conn.execute("SELECT sha256, MIN(size) AS menor, MAX(size) AS maior FROM capture GROUP BY sha256").fetchall()
    for r in vistos:
        digest = str(r["sha256"]).lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            problemas["hash_divergente"].append(f"{r['sha256']} (sha256 inválido)")
            continue
        arq = home / "blobs" / digest[:2] / digest[2:4] / digest
        try:
            tamanho = arq.stat().st_size
        except OSError:
            problemas["ausentes"].append(digest)
            continue
        if r["menor"] != r["maior"] or tamanho != r["maior"]:
            problemas["tamanho_divergente"].append(digest)
            continue
        h = hashlib.sha256()
        try:
            with arq.open("rb") as f:
                for bloco in iter(lambda: f.read(1 << 20), b""):
                    h.update(bloco)
        except OSError:
            problemas["ausentes"].append(digest)
            continue
        if h.hexdigest() != digest:
            problemas["hash_divergente"].append(digest)
    return {"verificados": len(vistos),
            **{k: {"n": len(v), "amostra": v[:_AMOSTRA]} for k, v in problemas.items()}}


def coletar(conn: sqlite3.Connection, recorte: dict[str, str | None] | None = None,
            home: Path | str | None = None) -> dict[str, Any]:
    """Contagens (comparáveis com um manifesto) e defeitos do acervo. Com `home`, confere também os blobs."""
    recorte = {k: v for k, v in (recorte or {}).items() if v} or None
    duplicatas = [dict(r) for r in conn.execute(
        "SELECT court AS tribunal, official_id, group_concat(id) AS ids FROM decision "
        "WHERE official_id IS NOT NULL GROUP BY court, official_id HAVING COUNT(*)>1 ORDER BY 1, 2")]
    sem_captura = [r[0] for r in conn.execute(
        "SELECT d.id FROM decision d WHERE NOT EXISTS (SELECT 1 FROM decision_document dd "
        "JOIN capture c ON c.id=dd.capture_id WHERE dd.decision_id=d.id) ORDER BY d.id")]
    versao = derivados.versao(conn)
    return {
        "manifesto_versao": VERSAO_MANIFESTO,
        "recorte": recorte,
        "contagens": {
            "obras": conn.execute("SELECT COUNT(*) FROM work").fetchone()[0],
            "decisoes": conn.execute("SELECT COUNT(*) FROM decision").fetchone()[0],
            "fontes": _fontes(conn),
            "stj": _stj(conn),
            "recursos_ckan": _recursos_ckan(conn),
            "derived_version": versao,
        },
        "pendencias": _pendencias(conn),
        "sync_state": {"linhas": conn.execute("SELECT COUNT(*) FROM sync_state").fetchone()[0],
                       "stj_resource": conn.execute("SELECT COUNT(*) FROM sync_state WHERE fonte='stj_resource'").fetchone()[0]},
        "defeitos": {
            "duplicatas": duplicatas,
            "decisoes_sem_captura": {"n": len(sem_captura), "amostra": sem_captura[:_AMOSTRA]},
            "datas_fora_do_recorte": _fora_do_recorte(conn, recorte) if recorte else [],
            "blobs": _blobs(conn, Path(home)) if home is not None else None,
            "derivados_desatualizados": None if derivados.compativel(conn) else
            {"encontrada": versao, "esperada": derivados.DERIVED_VERSION},
        },
    }


def _achatar(valor: Any, prefixo: str = "") -> dict[str, Any]:
    if isinstance(valor, dict):
        out: dict[str, Any] = {}
        for k, v in valor.items():
            out.update(_achatar(v, f"{prefixo}.{k}" if prefixo else str(k)))
        return out
    if isinstance(valor, list):
        # Recursos CKAN: lista ordenada por id; compara item a item, por id.
        out = {}
        for i, v in enumerate(valor):
            chave = v.get("id") if isinstance(v, dict) and v.get("id") else i
            out.update(_achatar(v, f"{prefixo}[{chave}]"))
        return out or {prefixo: []}
    return {prefixo: valor}


# Contagens que vêm do estado de sincronização do produtor e não viajam no snapshot (decisão 0057, emenda).
_ORIGEM = ("recursos_ckan",)
ORIGEM_NAO_APLICAVEL = "nao_aplicavel_pos_instalacao"


def _secoes(contagens: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(conteudo, origem) de um bloco de contagens; `origem` só com as chaves presentes."""
    return ({k: v for k, v in contagens.items() if k not in _ORIGEM},
            {k: contagens[k] for k in _ORIGEM if k in contagens})


def _secoes_do_manifesto(manifesto: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if "conteudo" in manifesto:
        return manifesto["conteudo"], manifesto.get("origem") or {}
    return _secoes(manifesto.get("contagens", {}))  # manifesto antigo, sem seções


def origem_aplicavel(dados: dict[str, Any], *, pos_instalacao: bool = False) -> bool:
    """A `origem` só se confere em acervo com `sync_state` da fonte (nunca em instalado de snapshot)."""
    return not pos_instalacao and dados["sync_state"]["stj_resource"] > 0


def conferir(dados: dict[str, Any], manifesto: dict[str, Any] | None = None, *, estrito: bool = False,
             pos_instalacao: bool = False) -> list[dict[str, Any]]:
    """Lista de falhas (vazia = passa). Cada falha tem `codigo` e `mensagem` específicos."""
    falhas: list[dict[str, Any]] = []
    if pos_instalacao and dados["sync_state"]["linhas"]:
        falhas.append({"codigo": "sync_state_presente",
                       "mensagem": f"--pos-instalacao exige acervo sem sync_state (instalado de snapshot); "
                                   f"há {dados['sync_state']['linhas']} linha(s)"})
    d = dados["defeitos"]
    for dup in d["duplicatas"]:
        falhas.append({"codigo": "duplicata", "mensagem": f"{dup['tribunal']} {dup['official_id']}: ids internos {dup['ids']}"})
    if d["decisoes_sem_captura"]["n"]:
        falhas.append({"codigo": "decisao_sem_captura",
                       "mensagem": f"{d['decisoes_sem_captura']['n']} decisão(ões) sem captura correspondente "
                                   f"(ex.: {', '.join(d['decisoes_sem_captura']['amostra'][:3])})"})
    for f in d["datas_fora_do_recorte"]:
        falhas.append({"codigo": "data_fora_do_recorte",
                       "mensagem": f"decisão {f['id']} ({f['tribunal']}): {f['campo']}={f['valor']!r} fora do recorte"})
    codigos = {"ausentes": "blob_ausente", "tamanho_divergente": "blob_tamanho", "hash_divergente": "blob_hash"}
    for campo, codigo in codigos.items():
        grupo = (d.get("blobs") or {}).get(campo)
        if grupo and grupo["n"]:
            falhas.append({"codigo": codigo, "mensagem": f"{grupo['n']} blob(s) de captura: {campo.replace('_', ' ')} "
                                                         f"(ex.: {', '.join(grupo['amostra'][:3])})"})
    if d["derivados_desatualizados"]:
        v = d["derivados_desatualizados"]
        falhas.append({"codigo": "derivado_desatualizado",
                       "mensagem": f"derived_version {v['encontrada']} (esperada {v['esperada']}); execute `fv acervo reconstruir`"})
    if manifesto is not None:
        (cont_m, orig_m), (cont_a, orig_a) = _secoes_do_manifesto(manifesto), _secoes(dados["contagens"])
        if origem_aplicavel(dados, pos_instalacao=pos_instalacao):
            # Pendências são origem, mas só se comparam no estrito (regra 5); manifesto antigo não as tem.
            if not estrito or "pendencias" not in orig_m:
                orig_m = {k: v for k, v in orig_m.items() if k != "pendencias"}
            else:
                orig_a = {**orig_a, "pendencias": dados["pendencias"]}
            cont_m, cont_a = {**cont_m, **orig_m}, {**cont_a, **orig_a}
        esperado, obtido = _achatar(cont_m), _achatar(cont_a)
        for caminho in sorted(set(esperado) | set(obtido)):
            if esperado.get(caminho, "<ausente>") != obtido.get(caminho, "<ausente>"):
                falhas.append({"codigo": "contagem_divergente",
                               "mensagem": f"{caminho}: manifesto={esperado.get(caminho, '<ausente>')!r} "
                                           f"acervo={obtido.get(caminho, '<ausente>')!r}"})
    if estrito:
        for p in dados["pendencias"]:
            falhas.append({"codigo": "pendencia", "mensagem": f"{p['fonte']}/{p['chave']}: {p['status']} {p.get('motivo') or ''}".rstrip()})
    return falhas


def manifesto_canonico(dados: dict[str, Any]) -> str:
    """Manifesto congelado: versão, recorte, `conteudo` (o que o snapshot carrega) e `origem` (sync_state do produtor)."""
    conteudo, origem = _secoes(dados["contagens"])
    origem["pendencias"] = dados["pendencias"]
    corpo = {"manifesto_versao": dados["manifesto_versao"], "recorte": dados["recorte"],
             "conteudo": conteudo, "origem": origem}
    return json.dumps(corpo, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _destino_proibido(home: Path | str, gravar: Path | str) -> str | None:
    """Motivo da recusa se `gravar` cai no home auditado (qualquer arquivo dele) ou é alias de um arquivo seu."""
    raiz = Path(os.path.realpath(home))
    destino = Path(os.path.realpath(gravar))
    if destino == raiz or raiz in destino.parents:
        return f"destino dentro do acervo auditado: {destino}"
    try:
        st = destino.stat()
    except OSError:
        return None  # ainda não existe: não há alias
    if st.st_nlink > 1:  # hardlink: mesmo (dispositivo, inode) de algum arquivo do home
        for pasta, _, nomes in os.walk(raiz):
            for nome in nomes:
                try:
                    o = os.stat(os.path.join(pasta, nome))
                except OSError:
                    continue
                if (o.st_dev, o.st_ino) == (st.st_dev, st.st_ino):
                    return f"destino é alias (hardlink) de {os.path.join(pasta, nome)}"
    return None


def executar(home: Path | str, *, manifesto: Path | str | None = None, gravar: Path | str | None = None,
             estrito: bool = False, recorte: dict[str, str | None] | None = None,
             sem_blobs: bool = False, pos_instalacao: bool = False) -> dict[str, Any]:
    """Resultado completo (`status` ok/parcial/falha/erro). Nunca escreve no home; só em `gravar`.

    `sem_blobs` pula a conferência dos bytes das capturas; sem falhas, o resultado é `parcial`, nunca `ok`.
    """
    ref = None
    recorte = {k: v for k, v in (recorte or {}).items() if v} or None  # sem datas: herda o manifesto
    if gravar and (motivo := _destino_proibido(home, gravar)):
        return {"status": "erro", "motivo": f"ValueError: {motivo}", "falhas": []}
    try:
        if manifesto:
            ref = json.loads(Path(manifesto).read_text(encoding="utf-8"))
            if not isinstance(ref, dict) or not ({"contagens", "conteudo"} & ref.keys()):
                raise ValueError("manifesto sem 'conteudo' nem 'contagens'")
            recorte = recorte or ref.get("recorte")
        conn = abrir_somente_leitura(home)
        try:
            dados = coletar(conn, recorte, None if sem_blobs else home)
        finally:
            conn.close()
    except (OSError, ValueError, sqlite3.Error) as exc:
        return {"status": "erro", "motivo": f"{type(exc).__name__}: {exc}", "falhas": []}
    falhas = conferir(dados, ref, estrito=estrito, pos_instalacao=pos_instalacao)
    status = "falha" if falhas else ("parcial" if sem_blobs else "ok")
    resultado = {"status": status, "falhas": falhas, **dados}
    if ref is not None:  # a omissão da origem é dita, nunca silenciosa
        resultado["origem"] = "conferida" if origem_aplicavel(dados, pos_instalacao=pos_instalacao) else ORIGEM_NAO_APLICAVEL
    if gravar:
        if status != "ok":  # nem falha nem verificação parcial congelam um manifesto
            resultado["manifesto_gravado"] = False
        else:
            Path(gravar).write_text(manifesto_canonico(dados), encoding="utf-8")
            resultado["manifesto_gravado"] = str(gravar)
    return resultado
