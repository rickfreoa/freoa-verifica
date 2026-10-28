"""Captura reproduzível de respostas oficiais para fixtures e sondas.

A requisição é montada exclusivamente pelo `build_*` do conector (ou é um GET simples a uma URL da allowlist
do conector) e enviada pelo transporte (mesma allowlist, limites e UA do conector). Sondas a fontes ainda sem
conector (`fonte_sonda`, catálogo `freoa_verifica.sondas`) seguem o mesmo caminho, só por GET e com UA identificado.
Nada de rede aqui fora de `freoa_verifica.transport`.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from freoa_verifica import __version__
from freoa_verifica.connectors import tjdft, tjsp
from freoa_verifica.connectors.base import Unavailable, registry, sob_guarda
from freoa_verifica.connectors.challenge import map_transport_error
from freoa_verifica.connectors.httputil import connector_fetch, form_body, ua_header
from freoa_verifica.identidade_http import MODO_IDENTIFICADO, USER_AGENT_IDENTIFICADO
from freoa_verifica.sondas import FONTES_BARRADAS, FONTES_SONDA, prefixos_por_host
from freoa_verifica.transport import BlockedHost, HTTPStatusError, Session, validate_reference

UA_IDENTIFICADO = USER_AGENT_IDENTIFICADO
UA_MODOS = ("identificado", "conector")
CHAVE = re.compile(r"[a-z0-9_]+")
ORIGEM_METADADOS = "captura_instrumento"
_TJSP_FILTROS = frozenset(
    {"pagina", "sinonimos", "origem", "tipo_decisao", "numero_processo", "desde", "ate", "dt_inicio", "dt_fim"}
)
_EXTENSOES = {
    "application/json": ".json", "text/html": ".html", "application/xhtml+xml": ".html",
    "text/xml": ".xml", "application/xml": ".xml", "application/pdf": ".pdf", "text/csv": ".csv",
    "text/plain": ".txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


@dataclass
class RegistroCaptura:
    conector: str | None
    versao: str
    url: str
    metodo: str
    parametros: dict[str, Any] | None
    user_agent: str
    capturado_em: str
    sonda: bool = False
    fonte_sonda: str | None = None
    confirmacao_host: str | None = None  # nível (A/B) do host da fonte-sonda; None fora de fonte-sonda
    confirmado_por_titular: bool = False  # sonda em host B liberada por confirmação explícita do titular
    unavailable: bool = False
    motivo: str | None = None
    categoria: str | None = None
    evidencia: dict[str, Any] = field(default_factory=dict)
    url_final: str | None = None
    status: int | None = None
    content_type: str | None = None
    cabecalhos: dict[str, str] = field(default_factory=dict)
    sha256: str | None = None
    bytes: int | None = None
    arquivo: str | None = None
    corpo: bytes | None = field(default=None, repr=False)

    def meta(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("corpo")
        return d


def _raiz_repo() -> Path | None:
    """Raiz do checkout (onde ficam `pyproject.toml` e `tests/`); None em instalação por wheel."""
    raiz = Path(__file__).resolve().parents[1]
    return raiz if (raiz / "pyproject.toml").is_file() else None


def recusar_destino_no_repositorio(destino: Path) -> None:
    raiz = _raiz_repo()
    if raiz is None:
        return
    alvo = Path(destino).resolve()
    if alvo == raiz or raiz in alvo.parents:
        raise ValueError("destino da sonda deve ficar fora do repositório")


# --- planejamento da requisição ---------------------------------------------------------------------


def _plano_tjdft(consulta: dict[str, Any]) -> dict[str, Any]:
    payload = tjdft.build_search_payload(
        consulta["query"],
        pagina=int(consulta.get("pagina", 0)),
        tamanho=int(consulta.get("tamanho", 10)),
        extras=consulta.get("extras"),
    )
    cab = {"Content-Type": "application/json", "Accept": "application/json"}
    corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return {
        "url": tjdft.SEARCH_URL, "metodo": "POST", "parametros": payload,
        "etapas": [{"url": tjdft.SEARCH_URL, "metodo": "POST", "body": corpo, "headers": cab}],
    }


def _plano_tjsp(consulta: dict[str, Any]) -> dict[str, Any]:
    termo = consulta.get("termo")
    if not isinstance(termo, str) or not termo.strip():
        raise ValueError("consulta tjsp exige 'termo'")
    filtros = {k: v for k, v in consulta.items() if k != "termo"}
    if set(filtros) - _TJSP_FILTROS:
        raise ValueError(f"filtros desconhecidos: {sorted(set(filtros) - _TJSP_FILTROS)}")
    req = tjsp.build_cjsg_request(termo, **filtros)
    if not 1 <= req.pagina <= tjsp.MAX_PAGINA:
        raise ValueError("pagina fora do intervalo")
    previa = {
        "url": req.post_url, "metodo": "POST", "body": form_body(req.fields), "exige_cookie": "JSESSIONID",
        "headers": {"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html"},
    }
    return {
        "url": req.page_url, "metodo": "GET", "sessao": True,
        "parametros": {
            "consulta": consulta, "formulario": req.fields,
            "etapa_previa": {"url": req.post_url, "metodo": "POST"},
        },
        "etapas": [previa, {"url": req.page_url, "metodo": "GET", "body": None, "headers": {}}],
    }


_CONSULTAS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {"tjdft": _plano_tjdft, "tjsp": _plano_tjsp}


def _plano_get(
    alvo_id: str, hosts, prefixos, mimes, url: str, *, rotulo: str = "do conector",
    exatas: dict[str, tuple[str, ...]] | None = None, consultas: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    """GET simples; a URL tem de estar na allowlist (conector ou fonte-sonda); recusa antes da rede.

    `prefixos` é o mapa host -> prefixos do transporte (ou None sem escopo de caminho).

    `exatas` (fonte-sonda): host -> caminhos exatos. Com ele, o caminho do pedido tem de ser IGUAL a uma rota do host
    (sem prefixo, sem sufixo, sem segmento extra) e só leva consulta nas rotas de `consultas`; a recusa vem antes do
    transporte, que fica como segunda barreira (`prefixos`), e a sonda não segue redirecionamento.

    `/robots.txt` é exceção declarada ao escopo de caminhos, mas só ele: o percurso inteiro roda com o prefixo
    exato `/robots.txt` em todos os hosts da allowlist, MIME só `text/plain` e NENHUM redirecionamento
    (`max_redirects=0`). Um 302 de `/robots.txt` para outra rota do mesmo host não é seguido: vira
    `unavailable` classificado (permissão indeterminada), sem pedido ao destino.
    """
    try:
        _, alvo = validate_reference(url, hosts)  # host e sintaxe; o caminho vem a seguir
        robots = alvo == "/robots.txt"
        if not robots:
            if alvo.split("?", 1)[0].lower().startswith("/robots.txt"):  # variante (query, caixa, sufixo) não é a exceção
                raise BlockedHost("robots.txt só na forma exata, sem parâmetros")
            host, _ = validate_reference(url, hosts, allowed_path_prefixes=prefixos)
            if exatas is not None:
                caminho, tem_consulta, _ = alvo.partition("?")
                if caminho not in exatas.get(host, ()) or (tem_consulta and caminho not in (consultas or {}).get(host, ())):
                    raise BlockedHost("caminho fora das rotas exatas da fonte-sonda")
    except BlockedHost as exc:
        raise ValueError(f"url fora da allowlist {rotulo} {alvo_id}: {exc}") from exc
    plano = {
        "url": url, "metodo": "GET", "parametros": None,
        "etapas": [{"url": url, "metodo": "GET", "body": None, "headers": {}}],
    }
    if exatas is not None:
        plano["max_redirects"] = 0  # sonda: um pedido; o destino de um 3xx não é pedido
    if robots:
        plano.update(
            path_prefixes={h: ("/robots.txt",) for h in sorted(hosts)}, mimes=frozenset({"text/plain"}),
            max_redirects=0,
        )
    return plano


def _planejar(conector: str, consulta: dict[str, Any] | None, url: str | None) -> dict[str, Any]:
    classes = registry()
    if conector not in classes:
        raise ValueError(f"conector sem captura: {conector}")
    if (consulta is None) == (url is None):
        raise ValueError("informe exatamente uma de: consulta, url")
    classe = classes[conector]
    if url is not None:
        plano = _plano_get(classe.id, classe.hosts, classe.path_prefixes, classe.mimes, url)
    elif conector in _CONSULTAS:
        plano = _CONSULTAS[conector](consulta)
    else:
        raise ValueError(f"conector {conector} só captura por url")
    plano.setdefault("path_prefixes", classe.path_prefixes)
    plano.setdefault("mimes", classe.mimes)
    plano.update(hosts=classe.hosts, user_agent=classe.user_agent)
    return plano


def _planejar_sonda(
    fonte_sonda: str, consulta: dict[str, Any] | None, url: str | None, *, confirmado_por_titular: bool = False
) -> dict[str, Any]:
    """Plano de uma sonda a fonte sem conector: GET numa URL da allowlist da fonte-sonda, UA identificado.

    Host de nível B (indexado, não lido em página oficial) só com `confirmado_por_titular`; sem ele, recusa
    antes da rede, inclusive para o robots.txt.
    """
    if fonte_sonda in FONTES_BARRADAS:
        raise ValueError(f"fonte-sonda {fonte_sonda} barrada, sem sonda: {FONTES_BARRADAS[fonte_sonda]}")
    fonte = FONTES_SONDA.get(fonte_sonda)
    if fonte is None:
        raise ValueError(f"fonte-sonda desconhecida: {fonte_sonda}")
    if consulta is not None or url is None:
        raise ValueError("fonte-sonda só captura por url")
    prefixos = prefixos_por_host(fonte)
    plano = _plano_get(
        fonte.id, fonte.hosts, prefixos, fonte.mimes, url, rotulo="da fonte-sonda",
        exatas=dict(fonte.rotas), consultas=dict(fonte.consultas),
    )
    host, _ = validate_reference(url, fonte.hosts)  # host canônico, já validado acima
    nivel = "B" if host in fonte.hosts_b else "A"
    if nivel == "B" and not confirmado_por_titular:
        raise ValueError(
            f"host {host} da fonte-sonda {fonte.id} é nível B (confirmação documental pendente): sonda bloqueada; "
            "só com --confirmado-por-titular"
        )
    plano.setdefault("path_prefixes", prefixos)
    plano.setdefault("mimes", fonte.mimes)
    plano.update(hosts=fonte.hosts, user_agent=MODO_IDENTIFICADO, confirmacao_host=nivel)
    return plano


@sob_guarda  # etapas da mesma captura: identidade efetiva e bloqueio por host (garantia estrutural 1, FIX18)
def _buscar(plano: dict[str, Any], ua_modo: str):
    sessao = Session() if plano.get("sessao") else None
    kw: dict[str, Any] = {
        "hosts": plano["hosts"], "path_prefixes": plano["path_prefixes"], "mimes": plano["mimes"],
        "user_agent": plano["user_agent"], "timeout": 60.0,
        "repeticao": 0,  # a captura faz exatamente um pedido por etapa: o transporte não repete 502/503/504
    }
    if "max_redirects" in plano:
        kw["max_redirects"] = plano["max_redirects"]
    if sessao is not None:
        kw["session"] = sessao
    resp = None
    for etapa in plano["etapas"]:
        headers = dict(etapa["headers"])
        if ua_modo == "identificado":
            headers["User-Agent"] = UA_IDENTIFICADO
        resp = connector_fetch(
            etapa["url"], method=etapa["metodo"], body=etapa["body"], headers=headers or None, **kw
        )
        if etapa.get("exige_cookie") and not sessao.has_cookie(etapa["exige_cookie"]):
            raise Unavailable("sessao_ausente")
    return resp


# --- escrita ----------------------------------------------------------------------------------------

_TMP = re.compile(r"\.[0-9a-f]{12}\.tmp$")


def _nome_tmp(path: Path) -> Path:
    return path.with_name(f"{path.name}.{uuid.uuid4().hex[:12]}.tmp")


def _atomico(path: Path, data: bytes, *, exclusivo: bool = False) -> None:
    """Grava por arquivo temporário. `exclusivo`: nunca substitui arquivo existente (FileExistsError)."""
    tmp = _nome_tmp(path)
    try:
        tmp.write_bytes(data)
        if exclusivo:
            try:
                os.link(tmp, path)  # falha se `path` existe; no Windows (NTFS) também
            except FileExistsError:
                raise
            except OSError:  # sistema de arquivos sem link físico: criação exclusiva direta
                with open(path, "xb") as f:
                    f.write(data)
            tmp.unlink(missing_ok=True)
        else:
            os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _recusar_sobrescrita(destino: Path, chave: str, corpo: Path | None = None) -> None:
    """Evidência gravada não se sobrescreve: recusa se o registro (ou o corpo) já existe no destino."""
    for alvo in (_confinado(destino, f"{chave}.captura.json"), corpo):
        if alvo is not None and (alvo.exists() or alvo.is_symlink()):
            raise ValueError(f"já existe {alvo.name} em {destino}: evidência não se sobrescreve; use outra --chave")


def _confinado(destino: Path, nome: str) -> Path:
    """Caminho final de `nome` dentro de `destino`, já resolvido; recusa fuga, link simbólico e subpasta."""
    base = destino.resolve()
    final = (base / nome)
    # Separadores de qualquer sistema são recusados: "..\\x" é fuga no Windows mesmo que o POSIX o aceite.
    if "/" in nome or "\\" in nome or final.parent.resolve() != base or final.resolve().parent != base or final.is_symlink():
        raise ValueError(f"caminho fora do destino: {nome}")
    return final


def _extensao(mime: str | None) -> str:
    return _EXTENSOES.get((mime or "").lower(), ".bin")


def capturar(
    conector: str | None,
    consulta: dict[str, Any] | None = None,
    *,
    url: str | None = None,
    destino: Path,
    sonda: bool,
    user_agent: str = "conector",
    chave: str | None = None,
    fonte_sonda: str | None = None,
    confirmado_por_titular: bool = False,
) -> RegistroCaptura:
    """Captura uma consulta (tjdft, tjsp) ou um GET na allowlist do conector e grava corpo + `<chave>.captura.json`.

    Com `fonte_sonda` (em lugar de `conector`), o alvo é uma fonte do catálogo `freoa_verifica.sondas`, ainda sem
    conector: só com `sonda`, só por `url`, pelo transporte comum e com UA identificado. O registro leva
    `fonte_sonda: <id>` e `conector: null`.

    Host de fonte-sonda em nível B (ver `freoa_verifica.sondas`) só com `confirmado_por_titular=True`, que fica
    registrado no `.captura.json`.

    Nunca sobrescreve evidência: se `<chave>.captura.json` (ou o corpo) já existe no destino, recusa; com `chave`
    explícita a recusa vem antes da rede.

    Tudo é validado antes da rede: conector ou fonte-sonda, modo de UA, `chave`, URL e destino. Com `sonda`, o
    destino não pode ser o repositório nem ficar dentro dele.
    """
    if (conector is None) == (fonte_sonda is None):
        raise ValueError("informe exatamente um de: conector, fonte_sonda")
    if fonte_sonda is not None and not sonda:
        raise ValueError("fonte-sonda exige sonda")
    if confirmado_por_titular and fonte_sonda is None:
        raise ValueError("confirmado_por_titular só vale com fonte-sonda")
    if user_agent not in UA_MODOS:
        raise ValueError(f"user_agent inválido: {user_agent}")
    if chave is not None and not CHAVE.fullmatch(chave):
        raise ValueError(f"chave inválida: {chave!r}")
    destino = Path(destino)
    if sonda:
        recusar_destino_no_repositorio(destino)
    if fonte_sonda is not None:
        plano = _planejar_sonda(fonte_sonda, consulta, url, confirmado_por_titular=confirmado_por_titular)
        ua = UA_IDENTIFICADO if user_agent == "identificado" else ua_header(plano["user_agent"])["User-Agent"]
        rotulo = fonte_sonda
    else:
        plano = _planejar(conector, consulta, url)
        classe = registry()[conector]
        ua = UA_IDENTIFICADO if user_agent == "identificado" else ua_header(classe.user_agent)["User-Agent"]
        rotulo = conector
    if chave is not None:  # antes da rede: não gasta pedido à fonte para depois recusar a gravação
        _recusar_sobrescrita(destino, chave)
    agora = datetime.now(timezone.utc)
    reg = RegistroCaptura(
        conector=conector, versao=__version__, url=plano["url"], metodo=plano["metodo"],
        parametros=plano["parametros"], user_agent=ua, capturado_em=agora.isoformat(), sonda=sonda,
        fonte_sonda=fonte_sonda, confirmacao_host=plano.get("confirmacao_host"),
        confirmado_por_titular=confirmado_por_titular,
    )
    try:
        resp = _buscar(plano, user_agent)
    except Unavailable as exc:
        reg.unavailable, reg.motivo, reg.categoria, reg.evidencia = True, exc.reason, exc.categoria, exc.evidencia
    else:
        reg.url_final, reg.status, reg.content_type = resp.final_url, resp.status, resp.mime
        reg.cabecalhos = dict(resp.headers)
        reg.sha256, reg.bytes, reg.corpo = resp.sha256, len(resp.body), resp.body
        if resp.status != 200:
            exc = map_transport_error(HTTPStatusError(resp.status), resp.final_url)
            reg.unavailable, reg.motivo, reg.categoria, reg.evidencia = True, exc.reason, exc.categoria, exc.evidencia
    chave = chave or f"{rotulo}_{(reg.sha256 or agora.strftime('%Y%m%d%H%M%S%f'))[:12]}"
    registro = _confinado(destino, f"{chave}.captura.json")
    corpo = None
    if not reg.unavailable and reg.corpo is not None:
        reg.arquivo = f"{chave}{_extensao(reg.content_type)}"
        corpo = _confinado(destino, reg.arquivo)
    _recusar_sobrescrita(destino, chave, corpo)  # chave derivada do hash só se conhece agora
    destino.mkdir(parents=True, exist_ok=True)
    if corpo is not None:
        _atomico(corpo, reg.corpo, exclusivo=True)
    _atomico(registro, json.dumps(reg.meta(), ensure_ascii=False, indent=1).encode("utf-8"), exclusivo=True)
    return reg


# --- fixture: transação recuperável -----------------------------------------------------------------


def _etapa(nome: str) -> None:
    """Ponto de interrupção dos testes de queda entre as etapas da publicação."""


@contextlib.contextmanager
def _bloqueio(fixtures: Path, espera: float = 10.0, velho: float = 120.0):
    """Exclusão mútua do manifesto: arquivo criado com O_EXCL, espera limitada, trava velha de queda é retomada."""
    trava = fixtures / "FIXTURES.json.lock"
    limite = time.monotonic() + espera
    while True:
        try:
            fd = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            with contextlib.suppress(OSError):
                if time.time() - trava.stat().st_mtime > velho:
                    trava.unlink()
                    continue
            if time.monotonic() >= limite:
                raise TimeoutError(f"manifesto em uso: {trava}") from None
            time.sleep(0.02)
    try:
        os.write(fd, f"{os.getpid()} {time.time()}".encode())
    finally:
        os.close(fd)
    try:
        yield
    finally:
        trava.unlink(missing_ok=True)


def _ler_manifesto(manifesto: Path) -> tuple[dict[str, Any], str]:
    bruto = manifesto.read_bytes()
    return json.loads(bruto.decode("utf-8")), ("\r\n" if b"\r\n" in bruto else "\n")  # preserva o fim de linha


def _recuperar(fixtures: Path) -> None:
    """Conclui ou desfaz a publicação interrompida e remove temporários órfãos. Exige o bloqueio."""
    diario = fixtures / "FIXTURES.json.pendente"
    if diario.is_file():
        d = json.loads(diario.read_text(encoding="utf-8"))
        publicada = d["chave"] in _ler_manifesto(fixtures / "FIXTURES.json")[0]
        for tmp, final in d["pares"]:
            tmp, final = fixtures / tmp, fixtures / final
            if publicada and tmp.is_file():
                os.replace(tmp, final)  # manifesto já publicado: conclui
            else:
                tmp.unlink(missing_ok=True)
        diario.unlink()
    for p in fixtures.rglob("*.tmp"):
        if _TMP.search(p.name):
            p.unlink(missing_ok=True)


def recuperar_pendentes(fixtures: Path) -> None:
    """Na abertura seguinte a uma queda: retoma ou desfaz a publicação pendente e remove temporários órfãos."""
    fixtures = Path(fixtures)
    with _bloqueio(fixtures):
        _recuperar(fixtures)


def registrar_fixture(reg: RegistroCaptura, chave: str, fixtures: Path) -> None:
    """Publica corpo e registro completo em `fixtures/<conector>/` e inventaria ambos em FIXTURES.json.

    Corpo e registro entram com nomes temporários únicos; um diário lista os renomeios, o manifesto é trocado
    atomicamente (ponto de confirmação) e só então os arquivos recebem o nome final. Uma queda em qualquer ponto
    é resolvida por `recuperar_pendentes`.
    """
    if reg.unavailable or reg.arquivo is None or reg.corpo is None:
        raise ValueError("captura indisponível não vira fixture")
    if not CHAVE.fullmatch(chave):
        raise ValueError(f"chave inválida: {chave}")
    fixtures = Path(fixtures)
    manifesto = fixtures / "FIXTURES.json"
    pasta = fixtures / reg.conector
    with _bloqueio(fixtures):
        _recuperar(fixtures)
        dados, nl = _ler_manifesto(manifesto)
        chave_reg = f"{chave}__captura"
        if chave in dados or chave_reg in dados:
            raise ValueError(f"chave já existe no manifesto: {chave}")
        pasta.mkdir(parents=True, exist_ok=True)
        nome_corpo = f"{chave}{Path(reg.arquivo).suffix}"
        corpo, registro = pasta / nome_corpo, pasta / f"{chave}.captura.json"
        if corpo.exists() or registro.exists():
            raise ValueError(f"arquivo já existe sem registro: {chave}")
        registro_bytes = json.dumps(reg.meta(), ensure_ascii=False, indent=1).encode("utf-8")
        entrada_corpo = {
            "bytes": reg.bytes, "capturado_em": reg.capturado_em, "categoria": "captura_real",
            "content_type": reg.content_type, "file": f"{reg.conector}/{nome_corpo}",
            "origem_metadados": ORIGEM_METADADOS, "sha256": reg.sha256, "status": reg.status,
            "url": reg.url, "url_final": reg.url_final,
        }
        entrada_registro = {
            "bytes": len(registro_bytes), "categoria": "metadados_captura", "descreve": chave,
            "file": f"{reg.conector}/{registro.name}", "sha256": hashlib.sha256(registro_bytes).hexdigest(),
        }
        pares = [(_nome_tmp(corpo), corpo), (_nome_tmp(registro), registro)]
        diario = fixtures / "FIXTURES.json.pendente"
        try:
            pares[0][0].write_bytes(reg.corpo)
            pares[1][0].write_bytes(registro_bytes)
            _etapa("temporarios")
            _atomico(diario, json.dumps({
                "chave": chave, "pares": [[t.relative_to(fixtures).as_posix(), f.relative_to(fixtures).as_posix()]
                                          for t, f in pares],
            }).encode("utf-8"))
            _etapa("diario")
            dados[chave], dados[chave_reg] = entrada_corpo, entrada_registro
            texto = json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True).replace("\n", nl) + nl
            _atomico(manifesto, texto.encode("utf-8"))
            _etapa("manifesto")
            os.replace(*pares[0])
            _etapa("corpo_publicado")
            os.replace(*pares[1])
            diario.unlink()
        except Exception:
            _recuperar(fixtures)
            raise
