"""Harness do contrato JSON (P3): casos sintéticos, três adaptadores, normalização e comparação.

Tudo offline: acervo de teste local (fixture Planalto da LSA + decisões sintéticas indexadas pelo mesmo
caminho de produção) e `FV_OFFLINE=1`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from freoa_verifica.connectors.base import Candidate, ParsedDecision
from freoa_verifica.transport import Response

ESPERADO = Path(__file__).parent / "esperado"
COMMIT_1_2_0 = "239bef6"
ADAPTADORES = ("python", "mcp", "rest")

CNJ_VALIDO = "0713166-62.2018.8.07.0000"
CNJ_INVALIDO = "0710920-40.2025.8.07.0000"
TRECHO_LSA = "A alienação, direta ou indireta, do controle de companhia aberta"
CITACAO_LSA = "art. 254-A da Lei 6.404/76"

CITACAO_160 = "art. 2º, XVI da Resolução CVM nº 160/2022"
TRECHO_160_RISCADO = (
    "pessoas vinculadas: controladores, diretos ou indiretos, ou administradores dos participantes do consórcio "
    "de distribuição, do emissor, do ofertante, bem como seus cônjuges ou companheiros, seus ascendentes, descendentes "
    "e colaterais até o 2o grau, e as demais pessoas vinculadas à emissão e à distribuição, conforme definidas "
    "na regulamentação da CVM que dispõe sobre normas e procedimentos a serem observados nas operações realizadas "
    "com valores mobiliários em mercados regulamentados;"
)

# Voláteis documentados em docs/CONTRATO.md (seção "Voláteis"): o valor é trocado por marcador do mesmo
# tipo; só a presença e o tipo contam.
VOLATEIS_CHAVES = frozenset({
    "fetched_at", "captured_at", "created_at", "data_captura", "ultima_atualizacao", "criado_em",  # instantes
    "home", "caminho_arquivo", "db_path", "blob_path",  # caminhos de máquina (`path` é caminho de dispositivo: estável)
    "duracao_ms", "elapsed_ms", "latencia_ms",  # durações
    "run_id",  # identificador de execução
})
# Chaves cujo conteúdo é hash ou saldo de execução, não do dado.
VOLATEIS_HASH_CHAVES = frozenset({"run_hash", "execucao_sha256", "ultimo_health"})
# Chaves que carregam estado enumerado: o conjunto de valores é parte do contrato.
CHAVES_DE_ESTADO = frozenset({
    "status", "motivo", "modo_busca", "relacao", "parte_entregue", "politica",
    "estado", "acao", "capacidade",
})

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


# ----------------------------------------------------------------------------------------------
# Acervo sintético
# ----------------------------------------------------------------------------------------------

def indexar_decisao(svc, court, official, *, text, ementa="ementa oficial", kind="acordao", cls="REsp",
                    organ="Terceira Turma", profile="fixture") -> str:
    text = text or ""
    body = (text or ementa).encode()
    url = f"https://example.org/{court}/{official}"
    resp = Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(), "2026-10-18T00:00:00Z", [], "text/plain")
    parsed = ParsedDecision(profile, kind, court, official, ementa=ementa, text=text, class_name=cls,
                            organ=organ, judgment_date="2025-05-05", rapporteur="Relator",
                            metadata={})
    conn = SimpleNamespace(id=court.lower(), authority=court, hosts={"example.org"},
                           fetch=lambda _, r=resp: r, parse=lambda _, p=parsed: p)
    svc._index_candidate_juris(conn, Candidate(court.lower(), official, "Decisão"))
    return svc.conn.execute("SELECT id FROM decision WHERE court=? AND official_id=?", (court, official)).fetchone()[0]


def semear(svc) -> dict[str, str]:
    """Decisões sintéticas e obras para casos de teste de contrato."""
    from freoa_verifica import situacao
    from freoa_verifica.aliases import WorkKey
    from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
    from tests.fixture_util import load_fixture

    ids = {}
    ids["stj_inteiro"] = indexar_decisao(
        svc, "STJ", "900001", text="Inteiro teor sintético do acórdão. " * 80, ementa="Ementa sintética do acordão.",
        profile="stf_pdf")  # perfil que promove o texto integral a inteiro_teor (ver test_a12)
    ids["stj_ementa"] = indexar_decisao(svc, "STJ", "900002", text=None, ementa="Ementa sintética apenas.")
    indexar_decisao(svc, "STJ", "555", text="texto stj 555 " * 20, ementa="ementa stj 555")
    indexar_decisao(svc, "TCU", "555", text="texto tcu 555 " * 20, ementa="ementa tcu 555",
                    cls="Acórdão", organ="Plenário")

    # Obra com redação riscada em data passada (RCVM 160)
    body_160 = load_fixture("cvm_resol_160_consolid_docx")
    doc_160 = parse_cvm_docx(body_160)
    rw_160 = svc.indexar_obra(
        source_id="cvm_normas",
        work_key=WorkKey("cvm", "resolucao", "160", 2022),
        document=doc_160,
        body=body_160,
        url="https://conteudo.cvm.gov.br/legislacao/resolucoes/resol160.docx",
        fetched_at="2026-10-18T00:00:00Z",
        work_date="2022-07-13",
        label="Resolução CVM nº 160/2022",
    )
    situacao.gravar(
        svc.conn,
        situacao.WorkStatus(
            rw_160.work_id,
            "vigente_declarada",
            captura_id=rw_160.capture_id,
            sha256=rw_160.sha256,
            lido_em="2026-10-18T00:00:00Z",
        ),
    )
    ids["capture_160"] = rw_160.capture_id

    # Execução para caso de obter_registro
    run_res = svc.verificar_citacao(CITACAO_LSA, trecho=TRECHO_LSA)
    ids["run_id_valido"] = run_res["run_id"]

    # Aviso de incidente de exemplo para listar_fontes cobrir os campos
    (Path(svc.home) / "avisos_incidente.json").write_text(
        json.dumps([{
            "id": "AV-000",
            "data": "2026-11-03",
            "versoes_afetadas": ["1.4.0a1"],
            "acao": "correcao",
            "descricao": "Aviso de teste de contrato",
            "referencia": "decisao 0075",
        }]),
        encoding="utf-8",
    )

    return ids


# ----------------------------------------------------------------------------------------------
# Casos: (nome, ferramenta, kwargs). Valores "@x" são resolvidos no ambiente (ids, capture_id).
# ----------------------------------------------------------------------------------------------

CASOS: list[tuple[str, str, dict[str, Any]]] = [
    ("verificar_citacao_verified", "verificar_citacao", {"citacao": CITACAO_LSA, "trecho": TRECHO_LSA, "proposicao": "eco"}),
    ("verificar_citacao_trecho_divergente", "verificar_citacao", {"citacao": CITACAO_LSA, "trecho": "trecho que não consta do artigo"}),
    ("verificar_citacao_obra_inexistente", "verificar_citacao", {"citacao": "Lei inventada 99.999/2099"}),
    ("verificar_texto", "verificar_texto", {"texto": f"Nos termos do {CITACAO_LSA} e da Lei inventada 99.999/2099."}),
    ("resolver_citacao_encontrada", "resolver_citacao", {"citacao": CITACAO_LSA}),
    ("resolver_citacao_inexistente", "resolver_citacao", {"citacao": "art. 1 da Lei 99.999/2099"}),
    ("obter_dispositivo", "obter_dispositivo", {"citacao": CITACAO_LSA}),
    ("historico_dispositivo", "historico_dispositivo", {"citacao": CITACAO_LSA}),
    ("buscar_legislacao_local", "buscar_legislacao", {"q": "alienação", "limite": 5}),
    ("pesquisar_jurisprudencia_textual", "pesquisar_jurisprudencia", {"q": "ementa sintética", "tribunais": ["STJ"]}),
    ("pesquisar_jurisprudencia_cnj_formato_invalido", "pesquisar_jurisprudencia", {"q": CNJ_INVALIDO}),
    ("pesquisar_jurisprudencia_cnj_nao_confirmado", "pesquisar_jurisprudencia", {"q": CNJ_VALIDO}),
    ("pesquisar_jurisprudencia_numero_nao_confirmado", "pesquisar_jurisprudencia", {"q": "REsp 9.999.999"}),
    ("pesquisar_jurisprudencia_numero_encontrado", "pesquisar_jurisprudencia", {"q": "REsp 900.001"}),
    ("obter_decisao_ementa", "obter_decisao", {"id": "@stj_inteiro"}),
    ("obter_decisao_inteiro_teor_paginado", "obter_decisao", {"id": "@stj_inteiro", "parte": "inteiro_teor", "max_chars": 100}),
    ("obter_decisao_parte_indisponivel", "obter_decisao", {"id": "@stj_ementa", "parte": "inteiro_teor"}),
    ("obter_decisao_nao_encontrada", "obter_decisao", {"id": "REsp 8.888.888"}),
    ("obter_decisao_ambigua", "obter_decisao", {"id": "555"}),
    ("obter_decisao_desambiguada", "obter_decisao", {"id": "555", "tribunal": "TCU"}),
    ("buscar_normas_cvm_offline", "buscar_normas_cvm", {"q": "resolução 80"}),
    ("buscar_normas_bcb_offline", "buscar_normas_bcb", {"q": "resolução 4966"}),
    ("obter_evidencia", "obter_evidencia", {"capture_id": "@capture_lsa", "max_chars": 300}),
    ("obter_evidencia_inexistente", "obter_evidencia", {"capture_id": "capture-inexistente"}),
    ("listar_fontes", "listar_fontes", {}),
    ("verificar_citacao_historica_riscada", "verificar_citacao", {
        "citacao": CITACAO_160,
        "trecho": TRECHO_160_RISCADO,
        "data": "2022-08-01",
    }),
    ("obter_registro_encontrada", "obter_registro", {"run_id": "@run_id_valido"}),
    ("obter_registro_inexistente", "obter_registro", {"run_id": "01M6H1Y11Y99K728HPNASE0000"}),
]


def resolver_args(kwargs: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
    return {k: (ctx[v[1:]] if isinstance(v, str) and v.startswith("@") else v) for k, v in kwargs.items()}


# ----------------------------------------------------------------------------------------------
# Adaptadores
# ----------------------------------------------------------------------------------------------

def _payload_mcp(result) -> dict:
    sc = getattr(result, "structured_content", None)
    if isinstance(sc, dict) and sc:
        return sc
    raw = "\n".join(getattr(b, "text", "") or "" for b in getattr(result, "content", []) or []).strip()
    return json.loads(raw) if raw else {}


def chamar_python(svc, ferramenta: str, args: dict[str, Any]) -> dict:
    return getattr(svc, ferramenta)(**args)


def chamar_mcp(mcp, ferramenta: str, args: dict[str, Any]) -> dict:
    from mcp import Client

    async def _run():
        async with Client(mcp) as client:
            r = await client.call_tool(ferramenta, args)
            assert not r.is_error, r
            return _payload_mcp(r)

    return asyncio.run(_run())


def chamar_rest(client, ferramenta: str, args: dict[str, Any]) -> dict:
    a = dict(args)
    if ferramenta == "verificar_citacao":
        r = client.post("/v1/verificacoes", json=a)
    elif ferramenta == "verificar_texto":
        r = client.post("/v1/verificacoes/texto", json=a)
    elif ferramenta == "resolver_citacao":
        r = client.get("/v1/citacoes/resolver", params=a)
    elif ferramenta == "obter_dispositivo":
        r = client.get("/v1/dispositivos", params=a)
    elif ferramenta == "historico_dispositivo":
        r = client.get("/v1/dispositivos/historico", params=a)
    elif ferramenta == "buscar_legislacao":
        r = client.get("/v1/legislacao", params=a)
    elif ferramenta == "pesquisar_jurisprudencia":
        if a.get("tribunais"):
            a["tribunais"] = ",".join(a["tribunais"])
        r = client.get("/v1/jurisprudencia", params=a)
    elif ferramenta == "obter_decisao":
        r = client.get(f"/v1/decisoes/{a.pop('id')}", params=a)
    elif ferramenta == "buscar_normas_cvm":
        r = client.get("/v1/normas/cvm", params=a)
    elif ferramenta == "buscar_normas_bcb":
        r = client.get("/v1/normas/bcb", params=a)
    elif ferramenta == "obter_evidencia":
        r = client.get(f"/v1/evidencias/{a.pop('capture_id')}", params=a)
    elif ferramenta == "listar_fontes":
        r = client.get("/v1/fontes")
    elif ferramenta == "obter_registro":
        run_id = a.pop("run_id")
        if "evidencias" in a or "fundamento_temporal" in a:
            r = client.post(f"/v1/registros/{run_id}/conferencia", json=a)
        else:
            r = client.get(f"/v1/registros/{run_id}", params=a)
    else:  # pragma: no cover
        raise KeyError(ferramenta)
    assert r.status_code == 200, (ferramenta, r.status_code, r.text)
    return r.json()


# ----------------------------------------------------------------------------------------------
# Normalização e comparação
# ----------------------------------------------------------------------------------------------

def normalizar(obj: Any, chave: str | None = None) -> Any:
    """Troca só os voláteis documentados por marcador do mesmo tipo; o resto fica como veio."""
    if isinstance(obj, dict):
        return {k: normalizar(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalizar(v, chave) for v in obj]
    if obj is None:
        return obj
    if chave in VOLATEIS_HASH_CHAVES:
        return "<hash-de-execucao>" if isinstance(obj, str) else obj
    if isinstance(obj, str) and _ULID.match(obj):
        return "<ulid>"  # identificadores gerados (work_id, capture_id, id de decisão, run_id)
    if chave in VOLATEIS_CHAVES:
        if isinstance(obj, str):
            return "<instante>" if _ISO.match(obj) else "<volatil>"
        if isinstance(obj, (int, float)) and not isinstance(obj, bool):
            return 0
    return obj


def _tipo(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def achatar(obj: Any) -> dict[str, set[str]]:
    """caminho -> tipos observados; listas colapsam em `[]`."""
    out: dict[str, set[str]] = {}

    def visita(o: Any, p: str) -> None:
        out.setdefault(p, set()).add(_tipo(o))
        if isinstance(o, dict):
            for k, v in o.items():
                visita(v, f"{p}.{k}" if p else k)
        elif isinstance(o, list):
            for v in o:
                visita(v, f"{p}[]")

    visita(obj, "")
    out.pop("", None)
    return out


def estados(obj: Any) -> dict[str, list[str]]:
    """caminho de campo de estado -> valores (ordenados, sem repetição) presentes na resposta."""
    out: dict[str, set[str]] = {}

    def visita(o: Any, p: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                q = f"{p}.{k}" if p else k
                if k in CHAVES_DE_ESTADO and isinstance(v, str):
                    out.setdefault(q, set()).add(v)
                visita(v, q)
        elif isinstance(o, list):
            for v in o:
                visita(v, f"{p}[]")

    visita(obj, "")
    return {k: sorted(v) for k, v in out.items()}


def _isento(ferramenta: str, caminho: str, isentos: frozenset[str]) -> bool:
    """Caminho isento: igual a uma entrada ou descendente dela (`.`/`[]`); entrada `"<ferramenta>:"` isenta a ferramenta
    inteira (decisão 0073, seção 1). O `:` final casa só a ferramenta de nome idêntico, nunca um prefixo de nome."""
    chave = f"{ferramenta}:{caminho}"
    return any(chave == i or chave.startswith((i + ".", i + "[]")) or (i.endswith(":") and chave.startswith(i))
               for i in isentos)


def _por_elemento(ferramenta: str, c: Any, a: Any, caminho: str, isentos: frozenset[str], em_lista: bool) -> list[str]:
    """Campos de cada elemento de lista da congelada precisam existir no elemento de mesmo índice da atual.

    O achatamento une os caminhos de todos os elementos, e um item que ainda tem o campo encobre a remoção em
    outro (B2-05). Variantes legítimas (itens com campos diferentes) são preservadas porque a comparação é item a
    item, não contra a união. Só índices presentes nas duas listas; o tamanho da lista não é contrato."""
    erros: list[str] = []
    if isinstance(c, dict) and isinstance(a, dict):
        for k, v in c.items():
            p = f"{caminho}.{k}" if caminho else k
            if _isento(ferramenta, p, isentos):
                continue
            if k not in a:
                if em_lista:
                    erros.append(f"campo removido: {p}")
            else:
                tc, ta = _tipo(v), _tipo(a[k])
                if em_lista and tc != "null" and ta != tc:  # tipo e nulidade por elemento (B3-07)
                    erros.append(f"tipo mudou em {p}: {[tc]} -> {[ta]}")
                erros.extend(_por_elemento(ferramenta, v, a[k], p, isentos, em_lista))
    elif isinstance(c, list) and isinstance(a, list):
        for i, (vc, va) in enumerate(zip(c, a)):
            erros.extend(f"{e} (elemento {i})" for e in _por_elemento(ferramenta, vc, va, f"{caminho}[]", isentos, True))
    return erros


def incompatibilidades(ferramenta: str, congelada: Any, atual: Any, isentos: frozenset[str] = frozenset()) -> list[str]:
    """Problemas da resposta atual frente à congelada (lista vazia = compatível).

    Reprova: campo ausente, tipo diferente, `null` onde havia valor, conjunto de estados diferente.
    Campo novo na atual é permitido. Campo `deprecated` ou `experimental` no contrato (`isentos`) pode sumir.
    """
    erros: list[str] = []
    f, a = achatar(congelada), achatar(atual)
    for caminho, tipos in f.items():
        if _isento(ferramenta, caminho, isentos):
            continue
        if caminho not in a:
            erros.append(f"campo removido: {caminho}")
            continue
        if not tipos <= a[caminho] | {"null"} or ("null" not in tipos and a[caminho] == {"null"}):
            erros.append(f"tipo mudou em {caminho}: {sorted(tipos)} -> {sorted(a[caminho])}")
    erros.extend(_por_elemento(ferramenta, congelada, atual, "", isentos, False))
    ef, ea = estados(congelada), estados(atual)
    for caminho, valores in ef.items():
        if _isento(ferramenta, caminho, isentos):
            continue
        if ea.get(caminho) != valores:
            erros.append(f"estados mudaram em {caminho}: {valores} -> {ea.get(caminho)}")
    return erros


def nome_arquivo(adaptador: str, caso: str) -> Path:
    return ESPERADO / f"{adaptador}__{caso}.json"


CASOS_NOVOS_1_4_0 = frozenset({
    "obter_registro_encontrada",
    "obter_registro_inexistente",
    "verificar_citacao_historica_riscada",
})
COMMIT_1_4_0 = "7a3347a"
VERSAO_1_4_0 = "1.4.0a2"


def gravar(adaptador: str, caso: str, ferramenta: str, entrada: dict, resposta: dict) -> None:
    is_novo = caso in CASOS_NOVOS_1_4_0
    doc = {
        "_proveniencia": {
            "commit": COMMIT_1_4_0 if is_novo else COMMIT_1_2_0,
            "versao": VERSAO_1_4_0 if is_novo else "1.2.0",
            "adaptador": adaptador,
            "caso": caso,
            "ferramenta": ferramenta,
            "entrada": entrada,
            "origem": (
                "entrada sintética + acervo de teste local (decisão 0075 / IL.0), FV_OFFLINE=1, sem rede"
                if is_novo
                else "entrada sintética + acervo de teste local, FV_OFFLINE=1, sem rede"
            ),
        },
        "resposta": normalizar(resposta),
    }
    ESPERADO.mkdir(exist_ok=True)
    nome_arquivo(adaptador, caso).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def carregar(adaptador: str, caso: str) -> dict:
    return json.loads(nome_arquivo(adaptador, caso).read_text(encoding="utf-8"))
