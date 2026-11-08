"""Correção r3 da 0080 (parecer do PR #39, rodada 3), R3-1 a R3-6.

R3-1 fechamento semântico da evidência (decisão do caminho recomposta dos bytes, instantes, termo por obtenção);
R3-2 validação da UNIÃO (home + pacote) antes de publicar; R3-3 obra identificada sem `LIMIT 1` por rótulo;
R3-4 falha ao preservar o termo encerra a sessão; R3-5 termo ilegível entra no classificador de barreiras;
R3-6 identidade do conteúdo do termo separada da identidade da obtenção.

Sintético por construção: transporte simulado, relógio controlado, banco SQLite temporário, nenhum socket.
"""
import dataclasses
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors import camara_evidencias as ev
from freoa_verifica.connectors import camara_robots as rb
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_atribuicao import termo_da_captura
from freoa_verifica.connectors.camara_estado import Estado, EstadoIndisponivel, _de_iso, iso, sha256
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.store import repo
from tests._camara_util import (LEI, ROBOTS_WWW, ROBOTS_WWW2, TERMO_HTML, RelogioFalso, obter_vinculado, portao,
                                resposta, robots_resp, selo_do_termo)
from tests.test_camara_0080_atribuicao import TERMO_SHA, ativar_home
from tests.test_camara_0081_atribuicao_inventario_snapshot import _registro, ativar_com, rotas_da_fixture
from tests.test_camara_0081_ativacao_e_robots import BUSCA, rotas_www

WWW, WWW2 = "www.camara.leg.br", "www2.camara.leg.br"
LIVRE = "User-agent: *\nDisallow: /wp-admin*\n"


def _json(dados: bytes):
    return json.loads(dados.decode("utf-8"))


def _bytes(valor) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


def _mais(instante: str, **delta) -> str:
    return iso(_de_iso(instante) + timedelta(**delta))


@pytest.fixture
def home_com_evidencia(tmp_path):
    rotas = rotas_da_fixture()
    home, relogio, _ = ativar_com(tmp_path, rotas)
    obter_vinculado(home, rotas, relogio, LEI)
    return home


def _arquivos(home) -> dict[str, bytes]:
    return dict(ev._arquivos_do_home(Estado(home)))


def _linhas(arquivos) -> list[dict]:
    return [_json(linha) for linha in arquivos["obtencoes.jsonl"].splitlines() if linha]


def _gravar_linhas(arquivos, linhas) -> None:
    arquivos["obtencoes.jsonl"] = b"".join(json.dumps(linha, sort_keys=True).encode() + b"\n" for linha in linhas)


def _da_lei(linhas) -> dict:
    return next(linha for linha in linhas if linha["url"] == LEI)


def _politica(arquivos, host=WWW2) -> tuple[str, dict]:
    nome = next(n for n in arquivos if n.startswith(f"politicas/{host}-"))
    return nome, _json(arquivos[nome])


# --- R3-1: a política apontada tem de ter AUTORIZADO a obtenção declarada --------------------------------------------------
def test_r31_controle_o_conjunto_integro_e_aceito(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    ev._validar(arquivos)
    linha = _da_lei(_linhas(arquivos))
    assert linha["termo_sha256"] == TERMO_SHA and linha["emitida_em"] and "sem_termo" not in linha


def _politica_sintetica(arquivos, texto, host=WWW2) -> dict:
    """Política COERENTE com seus bytes (hash, tamanho, grupos, atraso e decisões recomputados), como o auditor a monta."""
    _, recibo = _politica(arquivos, host)
    corpo = texto.encode()
    grupos = rb.interpretar(texto)
    geral = rb.decidir(grupos, "/")
    novo = {**recibo, "sha256": sha256(corpo), "bytes": len(corpo), "crawl_delay": geral.crawl_delay,
            "grupos_considerados": [list(g) for g in geral.grupos_considerados],
            "decisoes": {c: rb.decidir(grupos, c).estado for c in recibo["decisoes"]}}
    arquivos[f"robots-{host}-{novo['sha256']}.txt"] = corpo
    arquivos[f"politicas/{host}-{novo['sha256']}-{int(_de_iso(novo['obtido_em']).timestamp())}.json"] = _bytes(novo)
    return novo


def test_r31_politica_que_proibe_o_caminho_da_obtencao_e_recusada_mesmo_coerente_com_os_proprios_bytes(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    texto = "User-agent: *\nDisallow: /legin/fed/\n"
    nova = _politica_sintetica(arquivos, texto)
    assert rb.decidir(rb.interpretar(texto), "/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html"
                      ).estado == rb.PROIBIDO  # contraprova independente do validador: os bytes proíbem o caminho
    linhas = _linhas(arquivos)
    _da_lei(linhas)["politica_sha256"] = nova["sha256"]
    _gravar_linhas(arquivos, linhas)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_nao_autorizada_pela_politica"):
        ev._validar(arquivos)


def test_r31_decisao_persistida_contraria_aos_bytes_e_recusada(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    nome, recibo = _politica(arquivos, WWW2)
    recibo["decisoes"][next(iter(recibo["decisoes"]))] = "proibido"  # o recibo mente sobre o que os bytes dizem
    arquivos[nome] = _bytes(recibo)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_evidencia_ilegivel"):
        ev._validar(arquivos)


def test_r31_todas_as_decisoes_por_caminho_removidas_sao_recusadas(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    nome, recibo = _politica(arquivos, WWW2)
    assert recibo["decisoes"]  # o conjunto íntegro as tem
    recibo["decisoes"] = {}
    arquivos[nome] = _bytes(recibo)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_termo_sem_decisao_que_o_permita"):
        ev._validar(arquivos)


def test_r31_decisao_do_caminho_da_obtencao_removida_e_recusada(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    nome, recibo = _politica(arquivos, WWW2)
    caminho = LEI.removeprefix("https://www2.camara.leg.br")
    assert recibo["decisoes"].pop(caminho) == "permitido"  # só a decisão deste caminho; a do termo permanece
    arquivos[nome] = _bytes(recibo)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_nao_autorizada_pela_politica"):
        ev._validar(arquivos)


def _alterar_da_lei(arquivos, **campos):
    linhas = _linhas(arquivos)
    _da_lei(linhas).update(campos)
    _gravar_linhas(arquivos, linhas)


@pytest.mark.parametrize("variante,motivo", [
    ("emissao_depois_da_validade", "camara_obtencao_fora_da_validade_da_politica"),
    ("emissao_antes_da_politica", "camara_obtencao_fora_da_validade_da_politica"),
    ("registro_semanas_depois", "camara_evidencia_ilegivel"),
    ("registro_antes_da_emissao", "camara_evidencia_ilegivel"),
    ("conteudo_anterior_a_politica", "camara_obtencao_anterior_a_politica"),
])
def test_r31_instantes_deslocados_da_obtencao_sao_recusados(home_com_evidencia, variante, motivo):
    arquivos = _arquivos(home_com_evidencia)
    _, recibo = _politica(arquivos, WWW2)
    linha = _da_lei(_linhas(arquivos))
    alteracoes = {
        "emissao_depois_da_validade": {"emitida_em": _mais(recibo["valido_ate"], seconds=1),
                                       "em": _mais(recibo["valido_ate"], seconds=2)},
        "emissao_antes_da_politica": {"emitida_em": _mais(recibo["obtido_em"], hours=-1),
                                      "em": _mais(recibo["obtido_em"], hours=-1, seconds=1)},
        "registro_semanas_depois": {"em": _mais(linha["emitida_em"], days=21)},  # `em` é escrito após a resposta
        "registro_antes_da_emissao": {"em": _mais(linha["emitida_em"], seconds=-1)},
        "conteudo_anterior_a_politica": {"capturado_em": _mais(recibo["obtido_em"], days=-1)},
    }[variante]
    _alterar_da_lei(arquivos, **alteracoes)
    with pytest.raises(ev.EvidenciaInvalida, match=motivo):
        ev._validar(arquivos)


def test_r31_o_tempo_de_resposta_nao_e_recusado_em_em_tras_da_validade_da_politica(home_com_evidencia):
    """`em` é escrito DEPOIS da resposta: pode ultrapassar o vencimento sem invalidar uma emissão que ocorreu dentro dele."""
    arquivos = _arquivos(home_com_evidencia)
    _, recibo = _politica(arquivos, WWW2)
    emitida = _mais(recibo["valido_ate"], seconds=-5)
    _alterar_da_lei(arquivos, emitida_em=emitida, em=_mais(emitida, seconds=20))
    ev._validar(arquivos)


def _recibo_do_termo_com(arquivos, **campos) -> str:
    """Troca o recibo do termo por outro com os campos dados, NOMEADO pelo hash dos novos bytes, e religa as obtenções.
    Devolve o novo selo. A ativação continua apontando o antigo (a validação dos vínculos do termo vem antes)."""
    nome = next(n for n in arquivos if n.startswith("termo/") and n.endswith(".recibo.json"))
    recibo = {**_json(arquivos[nome]), **campos}
    dados = _bytes(recibo)
    novo = sha256(dados)
    antigo = nome.split(".")[1]
    del arquivos[nome]
    arquivos[f"termo/{recibo['sha256']}.{novo}.recibo.json"] = dados
    linhas = _linhas(arquivos)
    for linha in linhas:
        if linha.get("termo_recibo_sha256") == antigo:
            linha["termo_recibo_sha256"] = novo
    _gravar_linhas(arquivos, linhas)
    return novo


def test_r31_captura_do_termo_depois_da_validade_da_politica_e_recusada(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    _, recibo = _politica(arquivos, WWW2)
    _recibo_do_termo_com(arquivos, capturado_em=_mais(recibo["valido_ate"], hours=1))
    with pytest.raises(ev.EvidenciaInvalida, match="camara_termo_fora_da_validade_da_politica"):
        ev._validar(arquivos)


def test_r31_termo_capturado_depois_da_emissao_que_o_cita_e_recusado(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    _, recibo = _politica(arquivos, WWW2)
    _recibo_do_termo_com(arquivos, capturado_em=_mais(recibo["obtido_em"], minutes=30))  # válido, mas depois da emissão
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_termo_posterior_a_emissao"):
        ev._validar(arquivos)


def test_r31_sufixo_temporal_do_recibo_arquivado_incompativel_com_o_instante_declarado_e_recusado(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    nome, _ = _politica(arquivos, WWW2)
    instante = int(nome.rsplit("-", 1)[1].removesuffix(".json"))
    arquivos[f"{nome.rsplit('-', 1)[0]}-{instante + 3600}.json"] = arquivos.pop(nome)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_politica_instante_do_nome_incoerente"):
        ev._validar(arquivos)


def test_r31_obtencao_aponta_o_recibo_do_termo_e_nao_so_o_conteudo(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    _alterar_da_lei(arquivos, termo_recibo_sha256="0" * 64)  # o conteúdo existe, o recibo apontado não
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_sem_termo"):
        ev._validar(arquivos)


def test_r31_termo_nulo_so_onde_a_ausencia_e_legitima_e_marcada(tmp_path):
    p, t, relogio, estado = portao(tmp_path / "h", {LEI: resposta(LEI, b"<html>l</html>")}, instrumento=True)
    p.obter(LEI)  # portão sem ativação exigida (replay e instrumento): ausência de termo legítima e marcada
    arquivos = _arquivos(estado.home)
    linha = _da_lei(_linhas(arquivos))
    assert linha["termo_sha256"] is None and linha["sem_termo"] == "portao_sem_ativacao_exigida"
    ev._validar(arquivos)  # controle positivo
    sem_marcador = dict(arquivos)
    _alterar_da_lei(sem_marcador, sem_termo=None)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_evidencia_ilegivel"):  # ausência não marcada = perda de evidência
        ev._validar(sem_marcador)
    marcado_com_termo = dict(arquivos)
    _alterar_da_lei(marcado_com_termo, termo_sha256=TERMO_SHA, termo_recibo_sha256="1" * 64)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_evidencia_ilegivel"):
        ev._validar(marcado_com_termo)


def test_r31_exportacao_recusa_home_cuja_politica_nao_autorizava_a_obtencao(home_com_evidencia, tmp_path):
    arquivos = _arquivos(home_com_evidencia)
    nova = _politica_sintetica(arquivos, "User-agent: *\nDisallow: /legin/fed/\n")
    linhas = _linhas(arquivos)
    _da_lei(linhas)["politica_sha256"] = nova["sha256"]
    _gravar_linhas(arquivos, linhas)
    copia = tmp_path / "copia"
    for relativo, dados in arquivos.items():
        if relativo.startswith("evidencias/"):
            continue
        alvo = copia / "camara" / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_nao_autorizada_pela_politica"):
        ev.exportar(copia, tmp_path / "saida")


# --- R3-2: o preflight valida a UNIÃO do home com o pacote -------------------------------------------------------------------
def _pacote(home, destino) -> dict[str, bytes]:
    hashes, entrada = ev.exportar(home, destino)
    return ev.preparar(destino, {"camara_evidencias": entrada, "arquivos_sha256": hashes})


def _home_com_obtencao_sem_termo(tmp_path, pacote) -> Path:
    alvo = tmp_path / "destino"
    quebrada = {**_json(pacote["obtencoes.jsonl"].splitlines()[-1]), "termo_sha256": "0" * 64,
                "termo_recibo_sha256": "0" * 64, "sem_termo": None}
    (alvo / "camara").mkdir(parents=True)
    (alvo / "camara" / "obtencoes.jsonl").write_bytes(json.dumps(quebrada, sort_keys=True).encode() + b"\n")
    return alvo


def _foto(home) -> dict[str, bytes]:
    return {p.relative_to(home).as_posix(): p.read_bytes() for p in sorted(home.rglob("*")) if p.is_file()}


def test_r32_home_incoerente_com_pacote_integro_e_recusado_sem_escrever(home_com_evidencia, tmp_path):
    pacote = _pacote(home_com_evidencia, tmp_path / "saida")
    ev._validar(pacote)  # o pacote, sozinho, é íntegro
    destino = _home_com_obtencao_sem_termo(tmp_path, pacote)
    antes = _foto(destino)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_sem_termo:0{64}"):
        ev.instalar(destino, pacote)
    assert _foto(destino) == antes  # nada foi escrito: nem staging, nem arquivo do pacote


def test_r32_a_publicacao_recusa_no_preflight_antes_de_publicar(home_com_evidencia, tmp_path):
    pacote = _pacote(home_com_evidencia, tmp_path / "saida")
    destino = _home_com_obtencao_sem_termo(tmp_path, pacote)
    publicacao = ev.Publicacao(destino, pacote, tmp_path / "staging")
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_sem_termo"):
        publicacao.preparar()
    assert not publicacao.alterou and not (tmp_path / "staging").exists()


def test_r32_controle_home_coerente_com_pacote_integro_instala_e_a_uniao_valida(home_com_evidencia, tmp_path):
    pacote = _pacote(home_com_evidencia, tmp_path / "saida")
    destino = tmp_path / "limpo"
    ev.instalar(destino, pacote)
    ev._validar(_arquivos(destino))
    ev.instalar(destino, pacote)  # idempotente
    ev._validar(_arquivos(destino))


# --- R3-3: a busca identifica a obra sem `LIMIT 1` por rótulo ----------------------------------------------------------------
def _obra_extra(svc, *, rotulo, numero, ano, fonte, texto, caminho, resp, autoridade="federal", tipo="lei"):
    """Outra obra com a MESMA redação no MESMO caminho; o `rotulo` pode colidir com o da obra existente."""
    svc.conn.execute("INSERT OR IGNORE INTO source(id, authority, profile, hosts_json) VALUES (?,?,?,?)",
                     (fonte, "federal", "camara_norma" if fonte == "camara_legin" else "planalto", "[]"))
    work_id = repo.upsert_work(svc.conn, jurisdiction="br", authority=autoridade, kind=tipo, number=numero, year=ano,
                               label=rotulo)
    capture_id = repo.save_capture(svc.conn, resp, fonte, home=svc.home)
    digest = hashlib.sha256(texto.encode()).hexdigest()
    with svc.conn:
        svc.conn.execute("INSERT INTO provision(id, work_id, scope, path) VALUES (?,?,?,?)",
                         (f"p-{numero}-{ano}", work_id, "", caminho))
        svc.conn.execute("INSERT INTO redaction(id, provision_id, text, text_sha256) VALUES (?,?,?,?)",
                         (f"r-{numero}-{ano}", f"p-{numero}-{ano}", texto, digest))
        svc.conn.execute("INSERT INTO extract(id, capture_id, parser_version, text_sha256) VALUES (?,?,?,?)",
                         (f"e-{numero}-{ano}", capture_id, "t", digest))
        svc.conn.execute("INSERT INTO occurrence(id, redaction_id, extract_id) VALUES (?,?,?)",
                         (f"o-{numero}-{ano}", f"r-{numero}-{ano}", f"e-{numero}-{ano}"))
    return work_id, resp


def _texto_e_caminho(svc, rw):
    return svc.conn.execute(
        "SELECT r.text, p.path FROM redaction r JOIN provision p ON p.id=r.provision_id WHERE p.work_id=? "
        "ORDER BY length(r.text) DESC LIMIT 1", (rw.work_id,)).fetchone()


def _resp_camara(numero):
    return resposta(f"https://www2.camara.leg.br/legin/fed/lei/1990-1999/{numero}.html",
                    f"<html>obra {numero}</html>".encode())


def _itens(svc, texto, caminho, **kw):
    out = svc.buscar_legislacao(" ".join(texto.split()[:6]), limite=50, **kw)
    return [i for i in out["itens"] if i["caminho"] == caminho]


COLISOES = [
    pytest.param({"numero": "9999", "ano": 1999}, id="rotulo_e_ano_diferentes"),
    pytest.param({"numero": "6404", "ano": 1976, "autoridade": "outra"}, id="mesma_numeracao_outra_autoridade"),
    pytest.param({"numero": "6404", "ano": 1976, "tipo": "decreto"}, id="mesma_numeracao_outro_tipo"),
    pytest.param({"numero": "6404", "ano": 1977}, id="mesmo_numero_outro_ano"),
]


@pytest.mark.parametrize("identidade", COLISOES)
def test_r33_rotulo_colidente_sem_como_identificar_a_obra_nao_recebe_texto_nem_atribuicao_de_origem_camara(
        verifica_populada, tmp_path, identidade):
    svc, rw, _ = verifica_populada  # obra A: Planalto
    ativar_home(svc.home, tmp_path)
    texto, caminho = _texto_e_caminho(svc, rw)
    rotulo = svc.conn.execute("SELECT label FROM work WHERE id=?", (rw.work_id,)).fetchone()[0]
    resp = _resp_camara(identidade["numero"] + str(identidade["ano"]))
    _, resp = _obra_extra(svc, rotulo=rotulo, texto=texto, caminho=caminho, fonte="camara_legin", resp=resp,
                          **identidade)
    Estado(svc.home).registrar_obtencao(_registro(resp.sha256, resp.url, TERMO_SHA, resp.fetched_at, home=svc.home))
    itens = _itens(svc, texto, caminho, fonte="__somente_local__")
    assert itens
    for item in itens:
        assert item["nao_indexado"] is True and item["motivo"] == "OBRA_AMBIGUA"
        assert item["work_id"] is None and "atribuicao" not in item and "atribuicoes" not in item
        assert item["trecho"] is None  # a obra candidata é de origem Câmara: sem atribuição não há texto Câmara


def test_r33_controle_obra_unica_pelo_rotulo_continua_identificada_e_sem_atribuicao_alheia(verifica_populada, tmp_path):
    svc, rw, _ = verifica_populada
    ativar_home(svc.home, tmp_path)
    texto, caminho = _texto_e_caminho(svc, rw)
    resp = _resp_camara("99991999")
    _obra_extra(svc, rotulo="Lei 9999/1999", numero="9999", ano=1999, fonte="camara_legin", texto=texto,
                caminho=caminho, resp=resp)  # rótulo DISTINTO: sem colisão
    Estado(svc.home).registrar_obtencao(_registro(resp.sha256, resp.url, TERMO_SHA, resp.fetched_at, home=svc.home))
    itens = [i for i in _itens(svc, texto, caminho, fonte="__somente_local__") if i["work_id"] == rw.work_id]
    assert itens and all("atribuicao" not in i and not i.get("nao_indexado") and i["trecho"] for i in itens)


def test_r33_com_filtro_de_fonte_a_obra_da_fonte_e_a_unica_candidata(verifica_populada, tmp_path):
    svc, rw, _ = verifica_populada  # obra A (Planalto) e obra B (Câmara) com o MESMO rótulo, texto e caminho
    ativar_home(svc.home, tmp_path)
    texto, caminho = _texto_e_caminho(svc, rw)
    rotulo = svc.conn.execute("SELECT label FROM work WHERE id=?", (rw.work_id,)).fetchone()[0]
    resp = _resp_camara("99991999")
    obra_b, _ = _obra_extra(svc, rotulo=rotulo, numero="9999", ano=1999, fonte="camara_legin", texto=texto,
                            caminho=caminho, resp=resp)
    Estado(svc.home).registrar_obtencao(_registro(resp.sha256, resp.url, TERMO_SHA, resp.fetched_at, home=svc.home))
    do_planalto = _itens(svc, texto, caminho, fonte="planalto")
    assert do_planalto and all(i["work_id"] == rw.work_id and "atribuicao" not in i and "atribuicoes" not in i
                               for i in do_planalto)  # a obra B (Câmara) não empresta nem recebe o item
    da_camara = _itens(svc, texto, caminho, fonte="camara_legin")
    assert da_camara and all(i["work_id"] == obra_b and i["atribuicao"]["termo_sha256"] == TERMO_SHA
                             for i in da_camara)


def test_r33_duas_obras_camara_de_mesmo_rotulo_nunca_trocam_de_atribuicao(verifica_populada, tmp_path):
    svc, rw, _ = verifica_populada
    ativar_home(svc.home, tmp_path)
    texto, caminho = _texto_e_caminho(svc, rw)
    rotulo = svc.conn.execute("SELECT label FROM work WHERE id=?", (rw.work_id,)).fetchone()[0]
    for numero, ano in (("9998", 1998), ("9999", 1999)):
        resp = _resp_camara(f"{numero}{ano}")
        _obra_extra(svc, rotulo=rotulo, numero=numero, ano=ano, fonte="camara_legin", texto=texto, caminho=caminho,
                    resp=resp)
        Estado(svc.home).registrar_obtencao(_registro(resp.sha256, resp.url, TERMO_SHA, resp.fetched_at,
                                                      home=svc.home))
    itens = _itens(svc, texto, caminho, fonte="camara_legin")
    assert itens
    for item in itens:  # duas obras Câmara são candidatas do mesmo item: nenhuma é escolhida por ordem
        assert item["nao_indexado"] is True and item["motivo"] == "OBRA_AMBIGUA" and item["work_id"] is None
        assert "atribuicao" not in item and "atribuicoes" not in item and item["trecho"] is None


# --- R3-4 e R3-5: falhas depois da obtenção do termo -------------------------------------------------------------------------
def _sessao(tmp_path, rotas=None):
    return portao(tmp_path / "h", {**rotas_www(BUSCA), LEI: resposta(LEI, b"<html>lei</html>"), **(rotas or {})},
                  instrumento=True)


@pytest.mark.parametrize("etapa", ["guardar_termo", "gravar_pre_ativacao"])
def test_r34_falha_ao_preservar_o_termo_encerra_a_sessao_e_o_outro_host_nao_emite_depois_da_recuperacao(
        tmp_path, monkeypatch, etapa):
    p, t, relogio, estado = _sessao(tmp_path)
    original = getattr(Estado, etapa)

    def falhar(self, *a, **k):
        raise EstadoIndisponivel("disco")

    monkeypatch.setattr(Estado, etapa, falhar)
    with pytest.raises(Unavailable) as erro:
        ativ.capturar(p, estado, relogio)
    assert erro.value.reason == "persistencia_local_falhou"
    monkeypatch.setattr(Estado, etapa, original)  # o armazenamento se recupera na MESMA sessão
    emitidas = list(t.urls)
    for url in (BUSCA, LEI):  # os dois hosts
        with pytest.raises(Unavailable) as depois:
            p.obter(url)
        assert depois.value.reason == "persistencia_local_falhou"
    with pytest.raises(Unavailable, match="persistencia_local_falhou"):
        ativ.capturar(p, estado, relogio)
    assert t.urls == emitidas  # nada mais foi emitido naquela sessão
    novo, t2, _, _ = portao(tmp_path / "h", {**rotas_www(BUSCA)}, instrumento=True)  # retomada: só em nova unidade
    assert novo.obter(BUSCA).status == 200 and BUSCA in t2.urls


def test_r35_termo_com_interpretacao_invalida_entra_nas_barreiras_do_recurso_e_nao_e_falha_local(tmp_path):
    ruim = resposta(TERMO_URL, b"<html>termo \xff\xfe invalido em utf-8</html>")  # 200, text/html, charset=utf-8
    p, t, relogio, estado = _sessao(tmp_path, {TERMO_URL: ruim})
    with pytest.raises(Unavailable) as erro:
        ativ.capturar(p, estado, relogio)
    assert erro.value.reason == "termo_resposta_invalida" and erro.value.evidencia["bloqueio"] == "corpo_ou_mime"
    bloqueio = estado.bloqueio_do_recurso(WWW2, TERMO_URL)
    assert bloqueio is not None  # primeiro a existência, depois os campos
    assert bloqueio["classe"] == "corpo_ou_mime" and bloqueio["motivo"] == "transporte_RespostaInvalida"
    assert p._escopo().terminal is None  # distinta de falha local de interpretação
    assert estado.ler_pre_ativacao() is None and not list((tmp_path / "h" / "camara").glob("termo/*"))
    emitidas = list(t.urls)
    with pytest.raises(Unavailable) as depois:  # o host (www2) pelo restante da sessão
        p.obter(LEI)
    assert depois.value.evidencia["bloqueio"] == "corpo_ou_mime" and t.urls == emitidas
    novo, t2, _, _ = portao(tmp_path / "h", {TERMO_URL: ruim}, instrumento=True)  # e o recurso, persistido
    with pytest.raises(Unavailable) as persistido:
        novo.obter(TERMO_URL)
    assert persistido.value.evidencia["bloqueio"] == "corpo_ou_mime" and TERMO_URL not in t2.urls


# --- R3-6: conteúdo do termo e obtenção do termo têm identidades distintas -----------------------------------------------------
def _rotas_em(relogio, politica_texto: str) -> dict:
    """Respostas carimbadas no instante do recebimento (como o transporte vivo), pelo relógio controlado."""
    base = {**rotas_da_fixture(), ROBOTS_WWW: robots_resp(ROBOTS_WWW, politica_texto),
            ROBOTS_WWW2: robots_resp(ROBOTS_WWW2, politica_texto), TERMO_URL: resposta(TERMO_URL, TERMO_HTML)}
    return {url: (lambda r=r: dataclasses.replace(r, fetched_at=relogio.agora().isoformat())) for url, r in base.items()}


def _ativar_em(tmp_path, nome, inicio, politica_texto):
    """Home ativado com o MESMO termo (bytes idênticos), num instante e sob uma política próprios, com uma obtenção."""
    relogio = RelogioFalso(inicio)
    home, rotas = tmp_path / nome, _rotas_em(relogio, politica_texto)
    p, t, relogio, estado = portao(home, rotas, relogio=relogio, instrumento=True)
    pre = ativ.capturar(p, estado, relogio)
    revisao = tmp_path / f"revisao-{nome}.json"
    revisao.write_text(json.dumps({"auditor": "A", "revisado_em": "2026-11-09", "termo_sha256": pre["termo_sha256"],
                                   "resultado": "conforme"}), encoding="utf-8")
    ativ.registrar(estado, revisao, relogio)
    obter_vinculado(home, rotas, relogio, LEI)
    return home, estado


INICIO_A = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
INICIO_B = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
POLITICA_B = LIVRE + "Disallow: /privado\n"


def test_r36_recapturar_o_mesmo_termo_sob_outra_politica_preserva_o_recibo_historico(tmp_path):
    home, estado = _ativar_em(tmp_path, "h", INICIO_A, LIVRE)
    registro = estado.ler_ativacao()
    digest, selo1 = registro["termo_sha256"], registro["termo_recibo_sha256"]
    arquivo1 = home / "camara" / "termo" / f"{digest}.{selo1}.recibo.json"
    bytes1 = arquivo1.read_bytes()
    assert ativ.ativacao(estado) is not None
    # outro instante e outra política (os robots mudaram), mesmos bytes do termo
    inicio2 = INICIO_A + timedelta(hours=25)
    relogio2 = RelogioFalso(inicio2)
    p, t, relogio, _ = portao(home, _rotas_em(relogio2, POLITICA_B), relogio=relogio2, instrumento=True)
    pre2 = ativ.capturar(p, estado, relogio)
    assert pre2["termo_sha256"] == digest and pre2["termo_recibo_sha256"] != selo1  # outra obtenção, mesmo conteúdo
    assert arquivo1.read_bytes() == bytes1  # o recibo histórico NÃO foi sobrescrito
    assert len(list((home / "camara" / "termo").glob(f"{digest}.*.recibo.json"))) == 2
    assert estado.termo_preservado(digest, selo1) is not None and estado.termo_preservado(digest, pre2["termo_recibo_sha256"])
    assert estado.termo_preservado(digest, selo1)["politica_robots_sha256"] != estado.termo_preservado(
        digest, pre2["termo_recibo_sha256"])["politica_robots_sha256"]
    assert ativ.ativacao(estado) is not None  # a ativação anterior continua válida: o vínculo documental não se rompeu
    arquivos = _arquivos(home)
    ev._validar(arquivos)  # e o conjunto, com os dois recibos, é íntegro (cada captura sob a sua política)
    assert sum(1 for n in arquivos if n.startswith(f"termo/{digest}.") and n.endswith(".recibo.json")) == 2


def test_r36_snapshots_com_termo_identico_sob_instantes_e_politicas_distintas_coexistem_e_referenciam_o_recibo_certo(
        tmp_path):
    a, estado_a = _ativar_em(tmp_path, "a", INICIO_A, LIVRE)
    b, estado_b = _ativar_em(tmp_path, "b", INICIO_B, POLITICA_B)
    digest = estado_a.ler_ativacao()["termo_sha256"]
    assert digest == estado_b.ler_ativacao()["termo_sha256"]  # o mesmo conteúdo
    selo_a, selo_b = selo_do_termo(a, digest), selo_do_termo(b, digest)
    assert selo_a != selo_b  # obtenções distintas
    c = tmp_path / "c"
    for home, nome in ((a, "sa"), (b, "sb")):
        ev.instalar(c, _pacote(home, tmp_path / nome))
    assert {p.name.split(".")[1] for p in (c / "camara" / "termo").glob(f"{digest}.*.recibo.json")} == {selo_a, selo_b}
    ev._validar(_arquivos(c))
    do_termo = {(o["termo_sha256"], o["termo_recibo_sha256"]) for o in Estado(c).obtencoes() if o["termo_sha256"]}
    assert do_termo == {(digest, selo_a), (digest, selo_b)}  # cada obtenção aponta o recibo da sua própria obtenção
    for o in Estado(c).obtencoes():
        if o["termo_sha256"]:
            assert Estado(c).termo_preservado(o["termo_sha256"], o["termo_recibo_sha256"]) is not None
            assert termo_da_captura(c, o["sha256"], o["url"], o["capturado_em"]) == digest
    reexport = _pacote(c, tmp_path / "sc")  # e a reexportação do anexado leva os dois recibos
    assert {n.split(".")[1] for n in reexport if n.startswith(f"termo/{digest}.") and n.endswith(".recibo.json")} == {
        selo_a, selo_b}


def test_r36_a_identidade_da_obtencao_muda_com_o_recibo_e_a_do_conteudo_nao(tmp_path):
    home, estado = _ativar_em(tmp_path, "h", INICIO_A, LIVRE)
    recibo = estado.termo_preservado(estado.ler_ativacao()["termo_sha256"], estado.ler_ativacao()["termo_recibo_sha256"])
    outro = {**recibo, "capturado_em": _mais(recibo["capturado_em"], minutes=1)}
    digest = estado.guardar_termo(TERMO_HTML, outro)
    assert digest == sha256(TERMO_HTML) == recibo["sha256"]
    assert len(list((home / "camara" / "termo").glob("*.html"))) == 1  # um corpo
    assert len(list((home / "camara" / "termo").glob("*.recibo.json"))) == 2  # dois recibos
