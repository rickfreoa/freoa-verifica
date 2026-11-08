"""Decisão 0080 §2 (fluxo de ativação), §6 (reabertura), §8 (D6, inventário, HMAC). Sintético; sem rede."""
import hashlib
import hmac
import io
import json
import re

import pytest

from freoa_verifica import camara_instrumento as ci
from freoa_verifica.cli import build_parser
from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import Estado
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.connectors.camara_portao import Portao
from tests._camara_util import (BUSCA, LEI, ROBOTS_WWW, ROBOTS_WWW2, TERMO_HTML, RelogioFalso, Transporte, barreira,
                                da_fixture, portao, resposta, robots_resp)

# Gerador: corpo do termo em `tests/_camara_util.py` (TERMO_HTML), sintético; o termo real é capturado só na
# ativação ao vivo, que esta sessão não executa.


def revisao_arquivo(tmp_path, sha, **extra):
    caminho = tmp_path / "revisao.json"
    dados = {"auditor": "Auditor Codex", "revisado_em": "2026-11-09", "termo_sha256": sha, "resultado": "conforme",
             **extra}
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return caminho


def capturado(tmp_path, rotas=None):
    p, t, relogio, estado = portao(tmp_path / "home", rotas, instrumento=True)
    pre = ativ.capturar(p, estado, relogio)
    return p, t, relogio, estado, pre


# --- etapas 1 e 2 ---------------------------------------------------------------------------------------------------
def test_capturar_le_robots_antes_do_termo_e_preserva_o_termo_integro(tmp_path):
    p, t, relogio, estado, pre = capturado(tmp_path)
    assert t.urls == [ROBOTS_WWW2, ROBOTS_WWW, TERMO_URL]  # robots dos dois hosts, só então o termo
    sha = hashlib.sha256(TERMO_HTML).hexdigest()
    assert pre["termo_sha256"] == sha and set(pre["robots_sha256"]) == {"www.camara.leg.br", "www2.camara.leg.br"}
    recibo = estado.termo_preservado(sha)
    assert recibo and {recibo[k] for k in ("url", "status", "mime", "bytes", "sha256")} == {
        TERMO_URL, 200, "text/html", len(TERMO_HTML), sha}
    assert recibo["capturado_em"] and recibo["data_ou_versao_exibida"] == "05/11/2026"
    assert recibo["politica_robots_sha256"] == pre["robots_sha256"]["www2.camara.leg.br"]
    assert (tmp_path / "home" / "camara" / "termo" / f"{sha}.html").read_bytes() == TERMO_HTML
    assert not (tmp_path / "home" / "camara_ativacao.json").exists()  # capturar nunca ativa


@pytest.mark.parametrize("rotas,motivo", [
    ({ROBOTS_WWW2: robots_resp(ROBOTS_WWW2, "User-agent: *\nDisallow: /termo-de-uso")}, "robots_recusa"),
    ({ROBOTS_WWW2: robots_resp(ROBOTS_WWW2, "User-agent: *\nDisallow: /legin/fed/")}, "robots_recusa"),
    ({ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nDisallow: /legislacao")}, "robots_recusa"),
    ({ROBOTS_WWW2: robots_resp(ROBOTS_WWW2, "lixo")}, "robots_inconclusivo"),
    ({ROBOTS_WWW2: barreira("http_404", None, 404)}, "robots_inconclusivo"),
    ({ROBOTS_WWW2: barreira("http_403", "recusa_identificado", 403)}, "http_403"),
    ({TERMO_URL: barreira("http_403", "recusa_identificado", 403)}, "http_403"),
    ({TERMO_URL: barreira("http_404", None, 404)}, "http_404"),
    ({TERMO_URL: resposta(TERMO_URL, b"")}, "corpo_vazio"),
])
def test_falha_em_qualquer_etapa_impede_a_ativacao_e_nada_e_gravado(tmp_path, rotas, motivo):
    p, t, relogio, estado = portao(tmp_path / "home", rotas, instrumento=True)
    with pytest.raises(Unavailable) as erro:
        ativ.capturar(p, estado, relogio)
    assert erro.value.reason == motivo or motivo in erro.value.reason
    assert estado.ler_pre_ativacao() is None and estado.ler_ativacao() is None
    if motivo.startswith("robots_"):
        assert TERMO_URL not in t.urls  # robots recusado ou inconclusivo: o termo nem é pedido


def test_termo_com_redirecionamento_nao_e_seguido_nem_preservado(tmp_path):
    from dataclasses import replace
    r = replace(resposta(TERMO_URL, b"x"), status=301, redirects=["https://www2.camara.leg.br/outro"],
                final_url="https://www2.camara.leg.br/outro")
    p, t, relogio, estado = portao(tmp_path / "home", {TERMO_URL: r}, instrumento=True)
    with pytest.raises(Unavailable):
        ativ.capturar(p, estado, relogio)
    assert "https://www2.camara.leg.br/outro" not in t.urls and estado.ler_pre_ativacao() is None


# --- etapas 3 e 4 ---------------------------------------------------------------------------------------------------
def test_registrar_sem_precondicoes_ou_sem_revisao_nao_ativa(tmp_path):
    estado = Estado(tmp_path / "home")
    with pytest.raises(Unavailable, match="pre_condicoes_nao_cumpridas"):
        ativ.registrar(estado, tmp_path / "nao-existe.json")
    p, t, relogio, estado, pre = capturado(tmp_path)
    with pytest.raises(Unavailable, match="revisao_do_auditor_ausente_ou_ilegivel"):
        ativ.registrar(estado, tmp_path / "nao-existe.json")
    assert ativ.ativacao(estado) is None


@pytest.mark.parametrize("extra,motivo", [
    ({"resultado": "divergente"}, "termo_divergente_exige_revisao_da_decisao"),
    ({"termo_sha256": "0" * 64}, "termo_revisado_difere_do_preservado"),
    ({"auditor": ""}, "revisao_do_auditor_incompleta"),
    ({"revisado_em": " "}, "revisao_do_auditor_incompleta"),
])
def test_revisao_invalida_impede_a_ativacao(tmp_path, extra, motivo):
    p, t, relogio, estado, pre = capturado(tmp_path)
    with pytest.raises(Unavailable, match=motivo):
        ativ.registrar(estado, revisao_arquivo(tmp_path, pre["termo_sha256"], **extra))
    assert estado.ler_ativacao() is None


def test_revisao_com_corpo_nao_json_ou_sem_campo_nao_ativa(tmp_path):
    p, t, relogio, estado, pre = capturado(tmp_path)
    ruim = tmp_path / "r.json"
    ruim.write_text("não é json")
    with pytest.raises(Unavailable):
        ativ.registrar(estado, ruim)
    ruim.write_text(json.dumps({"auditor": "x"}))
    with pytest.raises(Unavailable, match="incompleta"):
        ativ.registrar(estado, ruim)


def test_termo_nao_preservado_impede_a_ativacao_e_a_invalida_depois(tmp_path):
    p, t, relogio, estado, pre = capturado(tmp_path)
    arquivo = tmp_path / "home" / "camara" / "termo" / f"{pre['termo_sha256']}.html"
    arquivo.unlink()  # termo capturado mas não preservado
    with pytest.raises(Unavailable, match="termo_revisado_difere_do_preservado"):
        ativ.registrar(estado, revisao_arquivo(tmp_path, pre["termo_sha256"]), relogio)
    arquivo.write_bytes(TERMO_HTML)
    registro = ativ.registrar(estado, revisao_arquivo(tmp_path, pre["termo_sha256"]), relogio)
    assert ativ.ativacao(estado) == registro
    arquivo.write_bytes(TERMO_HTML + b" adulterado")  # bytes preservados que não conferem com o hash
    assert ativ.ativacao(estado) is None


def test_robots_que_mudou_depois_da_captura_exige_refazer(tmp_path):
    p, t, relogio, estado, pre = capturado(tmp_path)
    t.rotas[ROBOTS_WWW2] = robots_resp(ROBOTS_WWW2, "User-agent: *\nDisallow: /wp-admin\n")
    relogio.avancar(25 * 3600)
    p.garantir_politica("www2.camara.leg.br")  # releitura com outro conteúdo
    with pytest.raises(Unavailable, match="robots_mudou_desde_a_captura"):
        ativ.registrar(estado, revisao_arquivo(tmp_path, pre["termo_sha256"]), relogio)


def test_registro_valido_grava_hashes_versao_instante_e_revisao(tmp_path):
    p, t, relogio, estado, pre = capturado(tmp_path)
    arquivo = revisao_arquivo(tmp_path, pre["termo_sha256"])
    registro = ativ.registrar(estado, arquivo, relogio)
    gravado = json.loads((tmp_path / "home" / "camara_ativacao.json").read_text("utf-8"))
    assert gravado == registro
    assert gravado["termo_sha256"] == pre["termo_sha256"] and gravado["robots_sha256"] == pre["robots_sha256"]
    assert gravado["versao_produto"] and gravado["instante"] and gravado["termo_url"] == TERMO_URL
    assert gravado["revisao"]["sha256"] == hashlib.sha256(arquivo.read_bytes()).hexdigest()
    assert gravado["revisao"]["resultado"] == "conforme" and gravado["revisao"]["auditor"] == "Auditor Codex"
    assert ativ.ativacao(estado) is not None


@pytest.mark.parametrize("campo,valor", [("termo_sha256", "f" * 64), ("instante", "2020-01-01T00:00:00+00:00"),
                                          ("versao_produto", "9.9.9")])
def test_registro_de_ativacao_adulterado_mantem_a_rota_pendente(tmp_path, campo, valor):
    p, t, relogio, estado, pre = capturado(tmp_path)
    ativ.registrar(estado, revisao_arquivo(tmp_path, pre["termo_sha256"]), relogio)
    arquivo = tmp_path / "home" / "camara_ativacao.json"
    dados = json.loads(arquivo.read_text("utf-8"))
    dados[campo] = valor
    arquivo.write_text(json.dumps(dados), encoding="utf-8")
    assert ativ.ativacao(estado) is None


# --- o conector só vai ao vivo com a ativação -------------------------------------------------------------------------
def servir_fixtures(monkeypatch, termo=True):
    respostas = {r.url: r for r in (da_fixture(k) for k in ("robots_portal", "robots_legin", "busca_lei6404",
                                                              "norma_lei6404", "textos_atualizado_lei6404",
                                                              "textos_original_lei6404"))}
    respostas[TERMO_URL] = resposta(TERMO_URL, TERMO_HTML)
    chamadas = []

    def falso(url, **kw):
        chamadas.append(url)
        assert kw["max_redirects"] == 0 and kw["repeticao"] == 0
        return respostas[url]

    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", falso)
    return respostas, chamadas


def test_sem_registro_o_conector_continua_pendente_e_nao_emite(tmp_path, monkeypatch, proibir_rede):
    respostas, chamadas = servir_fixtures(monkeypatch)
    con = CamaraLeginConnector(home=tmp_path / "home", relogio=RelogioFalso())
    with pytest.raises(Unavailable, match="ativacao_ao_vivo_pendente"):
        con.search("Lei 6404/1976")
    assert chamadas == []
    assert con.health().probes[0].detail == "ativacao_ao_vivo_pendente"


def test_depois_do_registro_o_conector_vai_ao_vivo_pelo_portao(tmp_path, monkeypatch, proibir_rede):
    respostas, chamadas = servir_fixtures(monkeypatch)
    relogio = RelogioFalso()
    home = tmp_path / "home"
    p = Portao(connector_fetch, estado=Estado(home), relogio=relogio, instrumento=True)
    pre = ativ.capturar(p, Estado(home), relogio)
    ativ.registrar(Estado(home), revisao_arquivo(tmp_path, pre["termo_sha256"]), relogio)
    chamadas.clear()
    con = CamaraLeginConnector(home=home, relogio=relogio)
    found = con.search("Lei 6404/1976")
    assert len(found) >= 1 and chamadas[-1].startswith("https://www.camara.leg.br/legislacao/busca")
    assert con.health().probes[0].detail == "ativada_sem_sonda_de_saude"
    assert con._portao.emitidas == 1 and all(c.startswith("https://www") for c in chamadas)  # só a busca; robots persistido


def test_conector_ativado_nao_obtem_o_termo_nem_vizinhos(tmp_path, monkeypatch, proibir_rede):
    respostas, chamadas = servir_fixtures(monkeypatch)
    con = CamaraLeginConnector(home=tmp_path / "home", relogio=RelogioFalso())
    for url in (TERMO_URL, TERMO_URL + "/", "https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade"):
        with pytest.raises(Unavailable):
            con._obter_recurso(url)
    assert chamadas == []


# --- CLI e instrumento -----------------------------------------------------------------------------------------------
def rodar(args, tmp_path, transporte=None, relogio=None):
    parsed = build_parser().parse_args(["--home", str(tmp_path / "home"), "camara", *args])
    saida = io.StringIO()
    codigo = ci.executar(parsed, transporte=transporte, relogio=relogio, out=saida)
    return codigo, saida.getvalue()


def test_cli_fluxo_capturar_depois_registrar(tmp_path):
    relogio = RelogioFalso()
    t = Transporte(relogio)
    codigo, saida = rodar(["ativar", "--capturar"], tmp_path, t, relogio)
    sha = hashlib.sha256(TERMO_HTML).hexdigest()
    assert codigo == 0 and json.loads(saida)["termo_sha256"] == sha
    codigo, _ = rodar(["ativar", "--registrar"], tmp_path, t, relogio)  # sem arquivo de revisão
    assert codigo == 1 and not (tmp_path / "home" / "camara_ativacao.json").exists()
    codigo, saida = rodar(["ativar", "--registrar", "--revisao", str(revisao_arquivo(tmp_path, sha))], tmp_path, t, relogio)
    assert codigo == 0 and (tmp_path / "home" / "camara_ativacao.json").exists()
    codigo, saida = rodar(["estado"], tmp_path, t, relogio)
    assert json.loads(saida)["ativacao"] is True


def test_cli_exige_uma_fase_e_o_instrumento_tem_teto_de_200(tmp_path):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["camara", "ativar"])
    p = ci._portao(tmp_path, Transporte(RelogioFalso()), RelogioFalso())
    assert p.instrumento and p.teto_sessao == 200


def test_reabertura_registrada_pelo_comando(tmp_path):
    relogio = RelogioFalso()
    t = Transporte(relogio, {ROBOTS_WWW: barreira("http_403", "recusa_identificado", 403)})
    rodar(["ativar", "--capturar"], tmp_path, t, relogio)
    estado = Estado(tmp_path / "home")
    assert estado.bloqueio_do_host("www.camara.leg.br", relogio.agora())
    assert rodar(["reabrir", "--host", "www.camara.leg.br"], tmp_path)[0] == 2  # sem decisão: recusado
    assert rodar(["reabrir", "--url", BUSCA], tmp_path)[0] == 2  # sem revisão: recusado
    assert rodar(["reabrir", "--host", "exemplo.gov.br", "--decisao", "d"], tmp_path)[0] == 2
    codigo, saida = rodar(["reabrir", "--host", "www.camara.leg.br", "--decisao", "0081"], tmp_path, relogio=relogio)
    assert codigo == 0 and json.loads(saida)["reaberto"] is True
    assert estado.bloqueio_do_host("www.camara.leg.br", relogio.agora()) is None
    assert estado.reaberturas("www.camara.leg.br")[-1]["decisao"] == "0081"
    assert estado.politica("www.camara.leg.br") is None  # a reabertura obriga nova leitura de robots


# --- §8: D6, inventário por normas, HMAC -------------------------------------------------------------------------------
PADRAO_PROIBIDO = re.compile(r"camara\.leg\.br|https?://|[0-9a-f]{64}|6404|1976|lei", re.I)


def rodar_reserva(args, tmp_path, transporte, relogio, capsys, privado="privado.json"):
    """Executa em `--reserva`; devolve (código, stdout, stderr, conteúdo do arquivo privado do guardião)."""
    destino = tmp_path / privado
    parsed = build_parser().parse_args(["--home", str(tmp_path / "home"), "camara", *args, "--reserva",
                                        "--saida-privada", str(destino)])
    capsys.readouterr()
    codigo = ci.executar(parsed, transporte=transporte, relogio=relogio)
    visto = capsys.readouterr()
    return codigo, visto.out, visto.err, json.loads(destino.read_text("utf-8")) if destino.exists() else None


def test_modo_reserva_nao_comunica_predicado_operacional_por_nenhum_canal(tmp_path, capsys):
    """D6 (0080 §8.3): nem ok/falha, nem classe, nem ativação, nem bloqueio em stdout, stderr ou código de saída;
    falha e sucesso são indistinguíveis por esses canais."""
    relogio = RelogioFalso()
    falha_t = Transporte(relogio, {TERMO_URL: barreira("http_403", "recusa_identificado", 403)})
    ok_t = Transporte(RelogioFalso())
    r_falha = rodar_reserva(["ativar", "--capturar"], tmp_path / "f", falha_t, relogio, capsys)
    r_ok = rodar_reserva(["ativar", "--capturar"], tmp_path / "o", ok_t, ok_t.relogio, capsys)
    assert r_falha[:3] == r_ok[:3] == (0, "", "")  # código, stdout e stderr idênticos para falha e sucesso
    assert r_falha[3]["resultado"] == "falha" and r_ok[3]["resultado"] == "ok"  # o guardião recebe o integral
    estado = rodar_reserva(["estado"], tmp_path / "o", ok_t, ok_t.relogio, capsys)
    registrar = rodar_reserva(["ativar", "--registrar"], tmp_path / "o", ok_t, ok_t.relogio, capsys)
    assert estado[:3] == registrar[:3] == (0, "", "")
    assert "ativacao" in estado[3] and registrar[3]["resultado"] == "falha"


def test_modo_reserva_contem_falhas_inesperadas_sem_caminho_nem_traceback(tmp_path, monkeypatch, capsys):
    def explode(*a, **k):
        raise OSError(f"{tmp_path}/lei-6404-1976 inacessivel")
    monkeypatch.setattr(ci, "ativar", explode)
    relogio = RelogioFalso()
    r = rodar_reserva(["ativar", "--capturar"], tmp_path, Transporte(relogio), relogio, capsys)
    assert r[:3] == (0, "", "")
    assert "6404" not in json.dumps(r[3]) and str(tmp_path) not in json.dumps(r[3])  # só o tipo, nunca o caminho


def test_modo_reserva_sem_saida_privada_e_recusado_pelo_cli():
    from freoa_verifica.cli import main
    with pytest.raises(SystemExit) as erro:
        main(["camara", "estado", "--reserva"])
    assert erro.value.code == 2


def test_modo_comum_traz_o_diagnostico(tmp_path):
    relogio = RelogioFalso()
    t = Transporte(relogio, {TERMO_URL: barreira("http_403", "recusa_identificado", 403)})
    codigo, comum = rodar(["ativar", "--capturar"], tmp_path / "a", t, relogio)
    assert codigo == 1 and "http_403" in comum and "camara.leg.br" in comum


@pytest.mark.parametrize("item", [
    {"url": "https://www2.camara.leg.br/legin/fed/lei/x"}, {"kind": "lei", "number": "6404"},
    {"kind": "decreto", "number": "1", "year": 1976}, {"kind": "lei", "number": "6404/76", "year": 1976},
    {"kind": "lei", "number": "6404", "year": 1976, "url": "https://x"}, {"kind": "lei", "number": "0", "year": 1976},
    "https://www2.camara.leg.br/legin/fed/lei/x",
])
def test_inventario_e_de_normas_nunca_de_urls(item):
    with pytest.raises(ValueError, match="inventario_so_aceita"):
        ci._norma(item)


def test_compromisso_hmac_sobre_a_serializacao_canonica_com_chave_de_256_bits():
    chave = bytes(range(32))
    hashes = ["b" * 64, "a" * 64]
    esperado = hmac.new(chave, json.dumps(["a" * 64, "b" * 64], separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
    assert ci.compromisso_hmac(chave, hashes) == esperado == ci.compromisso_hmac(chave, hashes[::-1])
    assert ci.compromisso_hmac(bytes(32), hashes) != esperado
    with pytest.raises(ValueError, match="256"):
        ci.compromisso_hmac(b"curta", hashes)


def ativado(tmp_path, monkeypatch):
    respostas, chamadas = servir_fixtures(monkeypatch)
    relogio = RelogioFalso()
    home = tmp_path / "home"
    pre = ativ.capturar(Portao(connector_fetch, estado=Estado(home), relogio=relogio, instrumento=True),
                        Estado(home), relogio)
    ativ.registrar(Estado(home), revisao_arquivo(tmp_path, pre["termo_sha256"]), relogio)
    return home, relogio, respostas, chamadas


def test_inventario_so_roda_com_ativacao(tmp_path, monkeypatch, proibir_rede):
    servir_fixtures(monkeypatch)
    normas = tmp_path / "normas.json"
    normas.write_text(json.dumps([{"kind": "lei", "number": "6404", "year": 1976}]))
    out = ci.inventariar(tmp_path / "home", normas, tmp_path / "saida", relogio=RelogioFalso())
    assert out["resultado"] == "falha" and out["motivo"] == "ativacao_ao_vivo_pendente"


def test_inventario_pela_cadeia_de_descoberta_preserva_origem_e_gera_hmac(tmp_path, monkeypatch, proibir_rede):
    home, relogio, respostas, chamadas = ativado(tmp_path, monkeypatch)
    normas = tmp_path / "normas.json"
    normas.write_text(json.dumps([{"kind": "lei", "number": "6404", "year": 1976}]))
    chave = tmp_path / "chave.bin"
    chave.write_bytes(bytes(range(32)))
    saida = tmp_path / "saida"
    out = ci.inventariar(home, normas, saida, relogio=relogio, chave_hmac=chave)
    assert out["resultado"] == "ok" and out["obtidas"] == 1
    recibos = [json.loads(p.read_text("utf-8")) for p in saida.rglob("*.recibo.json")]
    por_url = {r["url"]: r for r in recibos}
    assert por_url[LEI]["origem"]["url"].startswith("https://www.camara.leg.br/legislacao/busca")  # norma ← busca
    alvos = [r for r in recibos if "normaatualizada" in r["url"]]
    assert alvos and alvos[0]["origem"]["href"] and alvos[0]["origem"]["sha256"] == por_url[LEI]["sha256"]
    assert alvos[0]["politica_robots_sha256"] and alvos[0]["sha256"] == respostas[alvos[0]["url"]].sha256
    compromisso = json.loads((saida / "compromisso.json").read_text("utf-8"))
    esperado = ci.compromisso_hmac(chave.read_bytes(), sorted({r["sha256"] for r in recibos}))
    assert compromisso["hmac_sha256"] == esperado
    # nenhuma URL fora da cadeia busca → norma → links publicados foi pedida
    assert all(u in respostas for u in chamadas)


def test_inventario_reserva_nao_comunica_nada_e_o_integral_vai_ao_arquivo_privado(tmp_path, monkeypatch, proibir_rede,
                                                                                     capsys):
    home, relogio, respostas, chamadas = ativado(tmp_path, monkeypatch)
    normas = tmp_path / "normas.json"
    normas.write_text(json.dumps([{"kind": "lei", "number": "6404", "year": 1976}]))
    chave = tmp_path / "chave.bin"
    chave.write_bytes(bytes(range(32)))
    capsys.readouterr()
    parsed = build_parser().parse_args(["--home", str(home), "camara", "inventariar", str(normas), "--destino",
                                        str(tmp_path / "reserva"), "--chave-hmac", str(chave), "--reserva",
                                        "--saida-privada", str(tmp_path / "guardiao.json")])
    assert ci.executar(parsed, relogio=relogio) == 0
    visto = capsys.readouterr()
    assert (visto.out, visto.err) == ("", "")
    assert json.loads((tmp_path / "guardiao.json").read_text("utf-8"))["resultado"] == "ok"
    assert (tmp_path / "reserva" / "compromisso.json").exists()  # compromisso fica com o guardião
    curta = tmp_path / "curta.bin"
    curta.write_bytes(b"x" * 8)
    parsed = build_parser().parse_args(["--home", str(home), "camara", "inventariar", str(normas), "--destino",
                                        str(tmp_path / "r2"), "--chave-hmac", str(curta), "--reserva",
                                        "--saida-privada", str(tmp_path / "guardiao2.json")])
    assert ci.executar(parsed, relogio=relogio) == 0  # falha também com o mesmo código
    visto = capsys.readouterr()
    assert (visto.out, visto.err) == ("", "")
    assert json.loads((tmp_path / "guardiao2.json").read_text("utf-8"))["resultado"] == "falha"


# --- testes causais (§9): a proteção removida tem de fazer o teste correspondente falhar ----------------------------------
VIZINHOS = ("https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade", TERMO_URL + "?x=1", TERMO_URL + "/")
FALHA_DO_TESTE = pytest.fail.Exception  # `pytest.raises(Unavailable)` que não vê a exceção: a asserção do teste em si


def _admissao_do_termo():
    """Os vizinhos do termo têm resposta válida no dublê: sem a recusa o portão emitiria e `raises` falharia."""
    p, t, *_ = portao(rotas={u: resposta(u, b"<html>x</html>") for u in VIZINHOS})
    for url in VIZINHOS:
        with pytest.raises(Unavailable) as erro:
            p.obter(url)
        assert erro.value.reason in {"termo_url_nao_admitida", "rota_camara_nao_admitida", "url_camara_invalida"}
    assert t.chamadas == []


def test_causal_liberar_caminho_vedado_quebra_a_admissao(monkeypatch):
    _admissao_do_termo()
    from freoa_verifica.connectors import camara_portao as cp
    monkeypatch.setattr(cp, "validar_termo", lambda url: {"recurso": "termo", "mime": "text/html"})
    with pytest.raises(FALHA_DO_TESTE):  # a falha é a do predicado de admissão, não de um dublê sem rota
        _admissao_do_termo()


def _ritmo():
    p, t, relogio, _ = portao(rotas={BUSCA: resposta(BUSCA, b"<html>ok</html>")})
    p.obter(BUSCA)
    p.obter(BUSCA)
    inicios = [c[2] for c in t.chamadas]
    assert all(b - a >= 10.0 for a, b in zip(inicios, inicios[1:]))


def test_causal_retirar_a_espera_quebra_o_ritmo(monkeypatch):
    _ritmo()
    monkeypatch.setattr(Portao, "_esperar", lambda self, host, intervalo: None)
    with pytest.raises(AssertionError):
        _ritmo()


def test_causal_aceitar_termo_nao_preservado_quebra_a_ativacao(tmp_path, monkeypatch):
    p, t, relogio, estado, pre = capturado(tmp_path)
    (tmp_path / "home" / "camara" / "termo" / f"{pre['termo_sha256']}.html").unlink()
    arquivo = revisao_arquivo(tmp_path, pre["termo_sha256"])
    with pytest.raises(Unavailable, match="termo_revisado_difere_do_preservado"):
        ativ.registrar(estado, arquivo, relogio)
    www2 = pre["robots_sha256"]["www2.camara.leg.br"]
    monkeypatch.setattr(Estado, "termo_preservado", lambda self, digest: {"sha256": digest, "politica_robots_sha256": www2})
    assert ativ.registrar(estado, arquivo, relogio)  # com a proteção removida a ativação passaria: o teste acima falharia


DESTINO_3XX = "https://www2.camara.leg.br/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html"


def _redireciona():
    from dataclasses import replace
    return replace(resposta(BUSCA, b"x"), status=302, redirects=[DESTINO_3XX], final_url=DESTINO_3XX)


def test_3xx_nunca_e_seguido_e_nenhum_destino_e_emitido():
    p, t, *_ = portao(rotas={BUSCA: _redireciona(), DESTINO_3XX: resposta(DESTINO_3XX, b"<html>destino</html>")})
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA)
    assert erro.value.evidencia["bloqueio"] == "redirecionamento"
    assert DESTINO_3XX not in t.urls  # nenhum destino de redirecionamento é obtido, ainda que do mesmo host


def test_causal_aceitar_3xx_como_resposta_quebra_a_regra(monkeypatch):
    monkeypatch.setattr(Portao, "_resposta_invalida", staticmethod(lambda resp, url, rota: None))
    p, t, *_ = portao(rotas={BUSCA: _redireciona()})
    with pytest.raises(FALHA_DO_TESTE):  # sem a classificação do 3xx o portão entrega a resposta
        with pytest.raises(Unavailable):
            p.obter(BUSCA)


def test_causal_seguir_redirecionamento_quebra_a_regra_do_transporte(monkeypatch):
    p, t, *_ = portao(rotas={BUSCA: resposta(BUSCA, b"x")})
    p.obter(BUSCA)
    original = Portao._emitir

    def com_redirecionamento(self, url, rota, host, atraso=None):
        self_transporte = self.transporte
        self.transporte = lambda u, **kw: self_transporte(u, **{**kw, "max_redirects": 3})
        return original(self, url, rota, host, atraso)

    monkeypatch.setattr(Portao, "_emitir", com_redirecionamento)
    p2, t2, *_ = portao(rotas={BUSCA: resposta(BUSCA, b"x")})
    with pytest.raises(AssertionError, match="repetição e redirecionamento"):
        p2.obter(BUSCA)


def test_causal_expor_ok_ou_falha_da_reserva_quebra_o_d6(tmp_path, monkeypatch, capsys):
    t = Transporte(RelogioFalso(), {TERMO_URL: barreira("http_403", "recusa_identificado", 403)})
    r = rodar_reserva(["ativar", "--capturar"], tmp_path / "a", t, t.relogio, capsys)
    assert r[:3] == (0, "", "")
    original = ci._executar_reserva

    def vaza(args, transporte, relogio):  # variante defeituosa: devolve o predicado operacional como código de saída
        original(args, transporte, relogio)
        return 1

    monkeypatch.setattr(ci, "_executar_reserva", vaza)
    t2 = Transporte(RelogioFalso(), {TERMO_URL: barreira("http_403", "recusa_identificado", 403)})
    r2 = rodar_reserva(["ativar", "--capturar"], tmp_path / "b", t2, t2.relogio, capsys)
    assert r2[0] == 1  # com a proteção removida o canal do código de saída vazaria: o teste D6 acima falharia
