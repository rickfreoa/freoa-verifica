"""Instrumento da rota Câmara (decisão 0080; correções da 0081): ativação, reabertura, estado e inventário por normas.

Comandos de `fv camara ...`. Sessão do instrumento = uma execução: um `Portao` próprio, teto de 200 requisições,
trava de arquivo compartilhada com o produto quando o home é o mesmo.

D6 (0080 §8.3): em `--reserva` o processo NÃO comunica predicado operacional algum pelos canais que o supervisor ou o
codificador alcançam: stdout e stderr ficam vazios, o código de saída é sempre 0 e falhas inesperadas são contidas. O
resultado integral (ok/falha, classe, contagens, estado) vai somente ao arquivo privado do guardião
(`--saida-privada`), que fica sob a guarda separada. Fora da reserva a saída é a diagnóstica comum.
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
from freoa_verifica.connectors.camara_estado import Estado, Relogio, _escrever, iso
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.connectors.camara_policy import HOSTS
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.connectors.guarda import da_chamada

CHAVE_HMAC_MINIMA = 32  # bytes (256 bits)
_PARAR_A_SESSAO = {"teto_de_sessao", "persistencia_local_falhou", "interpretacao_local_falhou"}


def _portao(home, transporte, relogio, *, exigir_ativacao: bool = False) -> Portao:
    if transporte is None:
        from freoa_verifica.connectors.httputil import connector_fetch as transporte
    estado = Estado(home)
    return Portao(transporte, estado=estado, relogio=relogio, instrumento=True,
                  ativacao=(lambda: ativ.ativacao(estado)) if exigir_ativacao else None)


def _saida(dados: dict, *, falha: Unavailable | None = None) -> dict:
    if falha:
        return {"resultado": "falha", "motivo": falha.reason, "categoria": falha.categoria,
                "evidencia": falha.evidencia}
    return {"resultado": "ok", **dados}


def _falha_local(exc: Exception) -> dict:
    return _saida({}, falha=Unavailable("persistencia_local_falhou", None, {"causa": type(exc).__name__}))


def ativar(home, *, etapa: str, revisao: Path | str | None = None, transporte=None, relogio=None) -> dict:
    relogio = relogio or Relogio()
    estado = Estado(home)
    try:
        if etapa == "capturar":
            pre = ativ.capturar(_portao(home, transporte, relogio), estado, relogio)
            return _saida({"termo_sha256": pre["termo_sha256"], "robots_sha256": pre["robots_sha256"],
                           "proximo_passo": "revisao do auditor e `fv camara ativar --registrar`"})
        if etapa == "registrar":
            if revisao is None:
                raise ativ.AtivacaoRecusada("revisao_do_auditor_ausente_ou_ilegivel")
            return _saida({"ativacao": ativ.registrar(estado, revisao, relogio)})
    except Unavailable as exc:
        return _saida({}, falha=exc)
    except OSError as exc:  # EstadoIndisponivel e falhas de disco: indisponibilidade controlada, nunca o caminho
        return _falha_local(exc)
    raise ValueError("etapa de ativação inválida")


def reabrir(home, *, host: str | None = None, decisao: str | None = None, url: str | None = None,
            revisao: str | None = None, relogio=None) -> dict:
    """Reabertura registrada (§6): host só por decisão; recurso só por revisão. Nova leitura de robots segue."""
    relogio = relogio or Relogio()
    estado = Estado(home)
    if (host is None) == (url is None):
        raise ValueError("informe --host (com --decisao) ou --url (com --revisao)")
    try:
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
    except OSError as exc:
        return _falha_local(exc)


def situacao(home, relogio=None) -> dict:
    relogio = relogio or Relogio()
    estado = Estado(home)
    agora = relogio.agora()
    try:
        return {"ativacao": ativ.ativacao(estado) is not None,
                "hosts": {h: {"bloqueio": estado.bloqueio_do_host(h, agora), "revalidacao": estado.revalidacao(h),
                              "politica": (estado.politica_valida(h, agora) or {}).get("sha256")}
                          for h in sorted(HOSTS)},
                "agora": iso(agora)}
    except OSError as exc:
        return _falha_local(exc)


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


def _json(valor) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


def _recursos_da_unidade(con, falha: dict | None) -> list[dict]:
    """Todo recurso publicado pelas páginas da unidade: obtido, recusado (fora da admissão) ou não obtido, com motivo."""
    obtidos = {url for url in con.paginas if "/robots.txt" not in url}
    recursos = []
    for pagina, inventario in con.inventarios.items():
        for r in inventario["recursos"]:
            if r["url"] in obtidos:
                motivo = "obtido"
            elif not r["admitido"]:
                motivo = r["motivo"]
            elif falha and falha.get("url") == r["url"]:
                motivo = falha["motivo"]
            else:
                motivo = "nao_obtido"
            recursos.append({"pagina_de_origem": pagina, "url": r["url"], "href": r["href"], "rotulo": r["rotulo"],
                             "recurso": r["recurso"], "admitido": r["admitido"], "obtido": r["url"] in obtidos,
                             "motivo": motivo, "origem_sha256": r["origem"]["sha256"]})
    return recursos


def _gravar_unidade(pasta: Path, con, portao, norma: dict, falha: dict | None) -> list[str]:
    """Grava o material da unidade, inclusive o parcial de uma unidade que falhou, e o inventário durável dela.
    Devolve os hashes das páginas gravadas. Falha de gravação levanta `EstadoIndisponivel` (controlada)."""
    hashes = []
    paginas = []
    for url, resp in list(con.paginas.items()):
        if "/robots.txt" in url:
            continue
        origem = con.links.get(url)
        nome = hashlib.sha256(url.encode()).hexdigest()[:16]
        _escrever(pasta / f"{nome}.corpo", resp.body)
        recibo = {"url": url, "sha256": resp.sha256, "fetched_at": resp.fetched_at, "status": resp.status,
                  "mime": resp.mime, "politica_robots_sha256": portao.politica_de.get(url),
                  "origem": None if origem is None else {"href": origem[1], "rotulo": origem[2],
                                                         "url": origem[0].final_url, "sha256": origem[0].sha256}}
        _escrever(pasta / f"{nome}.recibo.json", _json(recibo))
        paginas.append({"url": url, "sha256": resp.sha256, "arquivo": f"{nome}.corpo"})
        hashes.append(resp.sha256)
    _escrever(pasta / "inventario.json", _json({"norma": norma, "resultado": "falha" if falha else "obtida",
                                                "falha": falha, "paginas": paginas,
                                                "recursos": _recursos_da_unidade(con, falha)}))
    return hashes


def _zerar(con) -> None:
    """Acumuladores do conector zerados por norma: nada de uma unidade vaza para a seguinte."""
    con.paginas.clear()
    con.links.clear()
    con.inventarios.clear()
    con.politicas.clear()


def inventariar(home, normas_arquivo, destino, *, transporte=None, relogio=None,
                chave_hmac: Path | str | None = None) -> dict:
    """Obtém as normas do inventário pela cadeia de descoberta (busca → página → links publicados)."""
    relogio = relogio or Relogio()
    estado = Estado(home)
    if ativ.ativacao(estado) is None:
        return _saida({}, falha=Unavailable("ativacao_ao_vivo_pendente"))
    try:
        normas = [_norma(i) for i in json.loads(Path(normas_arquivo).read_text("utf-8"))]
        chave = None if chave_hmac is None else Path(chave_hmac).read_bytes()
        if chave is not None and len(chave) < CHAVE_HMAC_MINIMA:
            raise ValueError("chave_hmac_menor_que_256_bits")
    except (OSError, ValueError, TypeError) as exc:
        return _saida({}, falha=Unavailable(f"inventario_invalido:{type(exc).__name__}"))
    portao = _portao(home, transporte, relogio, exigir_ativacao=True)
    con = CamaraLeginConnector(portao=portao, home=home)
    destino = Path(destino)
    hashes: list[str] = []
    obtidas = 0
    falhas: list[dict] = []
    with da_chamada():  # a sessão do instrumento é uma guarda só: host que recusou não é consultado de novo
        for norma in normas:
            _zerar(con)
            falha = None
            try:
                cand = con.resolve(norma)
                con.fetch(cand)
                if any(r["recurso"] == "original" and r["admitido"] for r in con.inventarios[cand.url]["recursos"]):
                    con.fetch(type(cand)(cand.source_id, cand.key, cand.title, cand.url,
                                         metadata={"versao": "publicacao_original"}))
            except Unavailable as exc:
                falha = {"motivo": exc.reason, "categoria": exc.categoria, "bloqueio": exc.evidencia.get("bloqueio"),
                         "url": exc.evidencia.get("url")}
            except Exception as exc:  # noqa: BLE001  AmbiguousCandidates e afins: não obtido, nunca silencioso
                falha = {"motivo": f"inventario_norma_nao_obtida:{type(exc).__name__}", "categoria": None,
                         "bloqueio": None, "url": None}
            try:  # o material parcial e o inventário da unidade são gravados também quando ela falhou
                hashes += _gravar_unidade(destino / f"{norma['kind']}-{norma['number']}-{norma['year']}",
                                          con, portao, norma, falha)
            except OSError:
                falhas.append({"motivo": "persistencia_local_falhou", "categoria": None, "bloqueio": None})
                break
            if falha is None:
                obtidas += 1
                continue
            falhas.append(falha)
            if falha["motivo"] in _PARAR_A_SESSAO or falha["bloqueio"] == "host_persistente":
                break
    if chave is not None:
        try:
            _escrever(destino / "compromisso.json", json.dumps(
                {"hmac_sha256": compromisso_hmac(chave, sorted(set(hashes))), "n": len(set(hashes))}).encode("utf-8"))
        except OSError:
            falhas.append({"motivo": "persistencia_local_falhou", "categoria": None, "bloqueio": None})
    nao_obtidas = len(normas) - obtidas
    return {"resultado": "ok" if not nao_obtidas and not falhas else "parcial", "obtidas": obtidas,
            "nao_obtidas": nao_obtidas, "falhas": [{"motivo": f["motivo"], "categoria": f["categoria"]} for f in falhas]}


def _despachar(args, transporte, relogio) -> dict:
    from freoa_verifica.store.db import data_home
    home = Path(args.home) if getattr(args, "home", None) else data_home()
    if args.camara_cmd == "ativar":
        return ativar(home, etapa="registrar" if args.registrar else "capturar", revisao=args.revisao,
                      transporte=transporte, relogio=relogio)
    if args.camara_cmd == "reabrir":
        return reabrir(home, host=args.host, decisao=args.decisao, url=args.url, revisao=args.revisao_recurso,
                       relogio=relogio)
    if args.camara_cmd == "inventariar":
        return inventariar(home, args.normas, args.destino, transporte=transporte, relogio=relogio,
                           chave_hmac=args.chave_hmac)
    return situacao(home, relogio)


def _executar_reserva(args, transporte, relogio) -> int:
    """Reserva (D6): nada operacional em stdout, stderr ou código de saída; o resultado vai ao arquivo do guardião."""
    try:
        dados = _despachar(args, transporte, relogio)
    except Exception as exc:  # noqa: BLE001  inclusive erros de uso e falhas inesperadas: contidos, sem caminho nem causa
        dados = {"resultado": "falha", "motivo": "erro_inesperado", "tipo": type(exc).__name__}
    destino = getattr(args, "saida_privada", None)
    if destino:
        try:
            Path(destino).parent.mkdir(parents=True, exist_ok=True)
            Path(destino).write_bytes(_json(dados) + b"\n")
        except OSError:
            pass  # sem canal privado não há o que comunicar, e nada é dito pelos canais públicos
    return 0


def executar(args, *, transporte=None, relogio=None, out=None) -> int:
    """Despacho de `fv camara`. Devolve o código de saída (0 ok, 1 indisponível, 2 uso). Em `--reserva`, sempre 0."""
    if getattr(args, "reserva", False):
        return _executar_reserva(args, transporte, relogio)
    out = out or sys.stdout
    try:
        dados = _despachar(args, transporte, relogio)
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(dados, ensure_ascii=False, sort_keys=True, indent=1), file=out)
    return 0 if dados.get("resultado", "ok") == "ok" else 1
