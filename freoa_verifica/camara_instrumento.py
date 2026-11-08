"""Instrumento da rota Câmara (decisão 0080): ativação, reabertura, estado e inventário por normas.

Comandos de `fv camara ...`. Sessão do instrumento = uma execução: um `Portao` próprio, teto de 200 requisições,
trava de arquivo compartilhada com o produto quando o home é o mesmo. Em `--reserva` (D6) nenhuma saída traz URL,
identificação de norma ou hash individual: só `ok`/`falha` e uma classe geral.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import Estado, Relogio, iso
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.connectors.camara_policy import HOSTS
from freoa_verifica.connectors.camara_portao import Portao

CHAVE_HMAC_MINIMA = 32  # bytes (256 bits)
_CLASSES_GERAIS = (("robots", "robots"), ("teto", "teto"), ("persistencia", "persistencia"),
                   ("ativacao", "ativacao"), ("http_", "barreira"), ("desafio", "barreira"), ("transporte", "barreira"))


def _portao(home, transporte, relogio) -> Portao:
    if transporte is None:
        from freoa_verifica.connectors.httputil import connector_fetch as transporte
    return Portao(transporte, estado=Estado(home), relogio=relogio, instrumento=True)


def classe_geral(motivo: str) -> str:
    """Rótulo grosso, sem URL nem hash, para a saída do modo reserva."""
    return next((rotulo for prefixo, rotulo in _CLASSES_GERAIS if prefixo in motivo), "outra")


def _saida(dados: dict, *, reserva: bool, falha: Unavailable | None = None) -> dict:
    if reserva:
        return {"resultado": "falha", "classe": classe_geral(falha.reason)} if falha else {"resultado": "ok"}
    if falha:
        return {"resultado": "falha", "motivo": falha.reason, "categoria": falha.categoria,
                "evidencia": falha.evidencia}
    return {"resultado": "ok", **dados}


def ativar(home, *, etapa: str, revisao: Path | str | None = None, transporte=None, relogio=None,
           reserva: bool = False) -> dict:
    relogio = relogio or Relogio()
    estado = Estado(home)
    try:
        if etapa == "capturar":
            pre = ativ.capturar(_portao(home, transporte, relogio), estado, relogio)
            return _saida({"termo_sha256": pre["termo_sha256"], "robots_sha256": pre["robots_sha256"],
                           "proximo_passo": "revisao do auditor e `fv camara ativar --registrar`"}, reserva=reserva)
        if etapa == "registrar":
            if revisao is None:
                raise ativ.AtivacaoRecusada("revisao_do_auditor_ausente_ou_ilegivel")
            registro = ativ.registrar(estado, revisao, relogio)
            return _saida({"ativacao": registro}, reserva=reserva)
    except Unavailable as exc:
        return _saida({}, reserva=reserva, falha=exc)
    raise ValueError("etapa de ativação inválida")


def reabrir(home, *, host: str | None = None, decisao: str | None = None, url: str | None = None,
            revisao: str | None = None, relogio=None) -> dict:
    """Reabertura registrada (§6): host só por decisão; recurso só por revisão. Nova leitura de robots segue."""
    relogio = relogio or Relogio()
    estado = Estado(home)
    if (host is None) == (url is None):
        raise ValueError("informe --host (com --decisao) ou --url (com --revisao)")
    if host is not None:
        if host not in HOSTS or not decisao or not decisao.strip():
            raise ValueError("reabertura de host exige host admitido e identificador da decisão")
        with estado.trava_do_host(host):
            return {"escopo": "host", "host": host, "reaberto": estado.liberar_host(host, decisao, relogio.agora())}
    from urllib.parse import urlsplit
    if not revisao or not revisao.strip():
        raise ValueError("reabertura de recurso exige identificador da revisão")
    alvo = urlsplit(url).netloc
    if alvo not in HOSTS:
        raise ValueError("host nao_admitido")
    with estado.trava_do_host(alvo):
        return {"escopo": "recurso", "url": url, "reaberto": estado.liberar_recurso(alvo, url, revisao, relogio.agora())}


def situacao(home, relogio=None, *, reserva: bool = False) -> dict:
    relogio = relogio or Relogio()
    estado = Estado(home)
    agora = relogio.agora()
    if reserva:
        return {"ativacao": ativ.ativacao(estado) is not None,
                "bloqueado": any(estado.bloqueio_do_host(h, agora) is not None for h in sorted(HOSTS))}
    return {"ativacao": ativ.ativacao(estado) is not None,
            "hosts": {h: {"bloqueio": estado.bloqueio_do_host(h, agora), "revalidacao": estado.revalidacao(h),
                          "politica": (estado.politica_valida(h, agora) or {}).get("sha256")} for h in sorted(HOSTS)},
            "agora": iso(agora)}


def _norma(item) -> dict:
    """Inventário é de normas (espécie, número, ano), nunca de URLs."""
    if (not isinstance(item, dict) or set(item) != {"kind", "number", "year"} or item["kind"] not in {"lei", "lei_complementar"}
            or not re.fullmatch(r"[1-9]\d{0,5}", str(item["number"])) or not isinstance(item["year"], int)
            or not 1900 <= item["year"] <= 2100):
        raise ValueError("inventario_so_aceita_especie_numero_ano")
    return {"kind": item["kind"], "number": str(item["number"]), "year": item["year"]}


def compromisso_hmac(chave: bytes, hashes: list[str]) -> str:
    """HMAC-SHA-256 sobre a serialização canônica (JSON ordenado) dos hashes individuais."""
    if len(chave) < CHAVE_HMAC_MINIMA:
        raise ValueError("chave_hmac_menor_que_256_bits")
    canonico = json.dumps(sorted(hashes), separators=(",", ":")).encode()
    return hmac.new(chave, canonico, hashlib.sha256).hexdigest()


def inventariar(home, normas_arquivo, destino, *, transporte=None, relogio=None, reserva: bool = False,
                chave_hmac: Path | str | None = None) -> dict:
    """Obtém as normas do inventário pela cadeia de descoberta (busca → página → links publicados)."""
    relogio = relogio or Relogio()
    estado = Estado(home)
    if ativ.ativacao(estado) is None:
        return _saida({}, reserva=reserva, falha=Unavailable("ativacao_ao_vivo_pendente"))
    try:
        normas = [_norma(i) for i in json.loads(Path(normas_arquivo).read_text("utf-8"))]
        chave = None if chave_hmac is None else Path(chave_hmac).read_bytes()
        if chave is not None and len(chave) < CHAVE_HMAC_MINIMA:
            raise ValueError("chave_hmac_menor_que_256_bits")
    except (OSError, ValueError, TypeError) as exc:
        return _saida({}, reserva=reserva, falha=Unavailable(f"inventario_invalido:{type(exc).__name__}"))
    portao = _portao(home, transporte, relogio)
    con = CamaraLeginConnector(portao=portao, home=home)
    destino = Path(destino)
    hashes: list[str] = []
    obtidas = 0
    falhas: list[Unavailable] = []
    for norma in normas:
        try:
            cand = con.resolve(norma)
            con.fetch(cand)
            inv = con.inventarios[cand.url]
            for versao in ("publicacao_original",):
                if any(r["recurso"] == "original" and r["admitido"] for r in inv["recursos"]):
                    con.fetch(type(cand)(cand.source_id, cand.key, cand.title, cand.url, metadata={"versao": versao}))
        except Unavailable as exc:
            falhas.append(exc)
            if exc.reason in {"teto_de_sessao"} or exc.evidencia.get("bloqueio") in {"host_persistente"}:
                break
            continue
        except Exception as exc:  # noqa: BLE001  AmbiguousCandidates e afins: não obtido, nunca silencioso
            falhas.append(Unavailable(f"inventario_norma_nao_obtida:{type(exc).__name__}"))
            continue
        for url, resp in list(con.paginas.items()):
            if "/robots.txt" in url:
                continue
            origem = con.links.get(url)
            pasta = destino / f"{norma['kind']}-{norma['number']}-{norma['year']}"
            pasta.mkdir(parents=True, exist_ok=True)
            nome = hashlib.sha256(url.encode()).hexdigest()[:16]
            (pasta / f"{nome}.corpo").write_bytes(resp.body)
            recibo = {"url": url, "sha256": resp.sha256, "fetched_at": resp.fetched_at, "status": resp.status,
                      "mime": resp.mime, "politica_robots_sha256": portao.politica_de.get(url),
                      "origem": None if origem is None else {"href": origem[1], "rotulo": origem[2],
                                                             "url": origem[0].final_url, "sha256": origem[0].sha256}}
            (pasta / f"{nome}.recibo.json").write_text(json.dumps(recibo, ensure_ascii=False, sort_keys=True, indent=1),
                                                        encoding="utf-8")
            hashes.append(resp.sha256)
        obtidas += 1
        con.paginas.clear()
    if chave is not None:
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "compromisso.json").write_text(
            json.dumps({"hmac_sha256": compromisso_hmac(chave, sorted(set(hashes))), "n": len(set(hashes))}), encoding="utf-8")
    nao_obtidas = len(normas) - obtidas
    if reserva:
        return {"resultado": "ok" if not nao_obtidas else "falha", **({"classe": classe_geral(falhas[0].reason)}
                                                                      if nao_obtidas and falhas else {})}
    return {"resultado": "ok" if not nao_obtidas else "parcial", "obtidas": obtidas, "nao_obtidas": nao_obtidas,
            "falhas": [{"motivo": f.reason, "categoria": f.categoria} for f in falhas]}


def executar(args, *, transporte=None, relogio=None, out=None) -> int:
    """Despacho de `fv camara`. Devolve o código de saída (0 ok, 1 indisponível, 2 uso)."""
    out = out or sys.stdout
    from freoa_verifica.store.db import data_home
    home = Path(args.home) if getattr(args, "home", None) else data_home()
    try:
        if args.camara_cmd == "ativar":
            etapa = "registrar" if args.registrar else "capturar"
            dados = ativar(home, etapa=etapa, revisao=args.revisao, transporte=transporte, relogio=relogio,
                           reserva=args.reserva)
        elif args.camara_cmd == "reabrir":
            dados = reabrir(home, host=args.host, decisao=args.decisao, url=args.url, revisao=args.revisao_recurso,
                            relogio=relogio)
        elif args.camara_cmd == "inventariar":
            dados = inventariar(home, args.normas, args.destino, transporte=transporte, relogio=relogio,
                                reserva=args.reserva, chave_hmac=args.chave_hmac)
        else:
            dados = situacao(home, relogio, reserva=args.reserva)
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(dados, ensure_ascii=False, sort_keys=True, indent=1), file=out)
    return 0 if dados.get("resultado", "ok") == "ok" else 1
