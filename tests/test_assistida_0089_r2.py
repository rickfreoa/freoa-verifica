"""Regressões r2: recibos e eventos sintéticos, sem rede ou navegador."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from freoa_verifica import transport as t
from freoa_verifica.assistida.ambiente import RecusaSessao
from freoa_verifica.assistida.cdp import Alvo
from freoa_verifica.assistida.perfis import PERFIS, resolver_grafo
from freoa_verifica.assistida.persistencia import persistir, recibo
from freoa_verifica.service import Verifica
from freoa_verifica.snapshot import (
    _conferir_vinculos_assistidos,
    export_snapshot,
    install_snapshot,
)
from freoa_verifica.store import repo
from tests.assistida_0089_util import (
    sessao as sessao,
    adapter,
    captura,
    entregar,
    request,
    metadados,
    META,
    BIN,
    BODY,
    URL,
    VigiaSintetico,
)
from tests.harness_assistida_0089_cenarios import (
    coletar_controles_passividade,
    comparar_passividade,
)
from tests.test_assistida_0089_harness import _pedido_origem


AUSENTE = "__ausente__"
INVALIDOS = [AUSENTE, None, "", " \t", 1, [], {}]


@pytest.fixture
def par_publicado(tmp_path, sessao, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    cs = [captura(META, metadados(), mime="application/json"), captura(BIN, BODY)]
    docs = resolver_grafo(PERFIS["normas_leg"], cs, orcamento=sessao)
    with Verifica(home=tmp_path / "origem") as svc:
        bid = persistir(
            svc.conn,
            svc.home,
            PERFIS["normas_leg"],
            docs,
            {0},
            VigiaSintetico(),
            orcamento=sessao,
        )[0]
        aid = svc.conn.execute(
            "SELECT id FROM capture WHERE url=?", (META,)
        ).fetchone()[0]
        svc.conn.execute("DROP TRIGGER capture_no_update")
        yield svc, aid, bid, cs, docs


def adulterar(svc, cid, caminho, valor):
    data = json.loads(
        svc.conn.execute(
            "SELECT assistida_json FROM capture WHERE id=?", (cid,)
        ).fetchone()[0]
    )
    alvo = data
    for k in caminho[:-1]:
        alvo = alvo[k]
    if valor == AUSENTE:
        alvo.pop(caminho[-1])
    else:
        alvo[caminho[-1]] = valor
    svc.conn.execute(
        "UPDATE capture SET assistida_json=? WHERE id=?", (json.dumps(data), cid)
    )
    svc.conn.commit()


@pytest.mark.parametrize("valor", INVALIDOS)
@pytest.mark.parametrize(
    "caminho",
    [
        ("vinculo",),
        ("obtencao_id",),
        ("sessao_id",),
        *[
            ("vinculo", k)
            for k in (
                "metadados_capture_id",
                "metadados_obtencao_id",
                "metadados_sha256",
                "urn",
                "uuid",
                "version",
                "@id",
                "legislationLegalValue",
            )
        ],
    ],
)
def test_snapshot_e_evidencia_recusam_vinculo_incompleto(par_publicado, caminho, valor):
    svc, _, bid, _, _ = par_publicado
    adulterar(svc, bid, caminho, valor)
    with pytest.raises(ValueError, match="snapshot_vinculo_assistido_invalido"):
        _conferir_vinculos_assistidos(svc.conn, "main")
    out = svc.obter_evidencia(bid)
    assert (
        out["status"] == "indisponivel" and out["motivo"] == "recibo_assistido_invalido"
    )


@pytest.mark.parametrize("valor", INVALIDOS)
def test_igualdade_entre_ids_ausentes_nao_prova_vinculo(par_publicado, valor):
    svc, aid, bid, _, _ = par_publicado
    adulterar(svc, aid, ("obtencao_id",), valor)
    adulterar(svc, bid, ("vinculo", "metadados_obtencao_id"), valor)
    with pytest.raises(ValueError, match="snapshot_vinculo_assistido_invalido"):
        _conferir_vinculos_assistidos(svc.conn, "main")
    assert svc.obter_evidencia(bid)["motivo"] == "recibo_assistido_invalido"


@pytest.mark.parametrize(
    "caso", ["sem_vinculo", "null_igual_null", "a_automatica", "a_recurso_b"]
)
def test_instalador_publico_recusa_classe_sem_publicar(par_publicado, tmp_path, caso):
    svc, aid, bid, _, _ = par_publicado
    if caso == "sem_vinculo":
        adulterar(svc, bid, ("vinculo",), AUSENTE)
    elif caso == "null_igual_null":
        adulterar(svc, aid, ("obtencao_id",), None)
        adulterar(svc, bid, ("vinculo", "metadados_obtencao_id"), None)
    elif caso == "a_automatica":
        svc.conn.execute(
            "UPDATE capture SET modalidade_acesso='automatico',procedencia='captura_direta' WHERE id=?",
            (aid,),
        )
    else:
        svc.conn.execute("UPDATE capture SET final_url=? WHERE id=?", (BIN, aid))
    svc.conn.commit()
    pacote = tmp_path / "pacote"
    assert export_snapshot(svc.conn, svc.home, pacote)["status"] == "ok"
    with Verifica(home=tmp_path / "destino") as destino:
        out = install_snapshot(destino, pacote, aceitar_nao_vinculado=True)
        assert (
            out["status"] == "erro"
            and "snapshot_vinculo_assistido_invalido" in out["motivo"]
        )
        assert destino.conn.execute("SELECT count(*) FROM capture").fetchone()[0] == 0


@pytest.mark.parametrize("valor", INVALIDOS[1:])
@pytest.mark.parametrize("campo", ["obtencao_id", "sessao_id"])
@pytest.mark.parametrize("indice", [0, 1])
def test_grafo_e_selecao_recusam_identidades_invalidas(
    sessao, tmp_path, valor, campo, indice
):
    cs = [captura(META, metadados(), mime="application/json"), captura(BIN, BODY)]
    docs = resolver_grafo(PERFIS["normas_leg"], cs, orcamento=sessao)
    cs[indice] = replace(cs[indice], **{campo: valor})
    with pytest.raises(ValueError, match="IDENTIDADE_ASSISTIDA_INVALIDA"):
        resolver_grafo(PERFIS["normas_leg"], cs, orcamento=sessao)
    doc = replace(docs[0], captura=cs[1], dependentes=(cs[0],))
    with Verifica(home=tmp_path) as svc:
        with pytest.raises(ValueError, match="IDENTIDADE_ASSISTIDA_INVALIDA"):
            persistir(
                svc.conn,
                svc.home,
                PERFIS["normas_leg"],
                [doc],
                {0},
                VigiaSintetico(),
                orcamento=sessao,
            )
        assert svc.conn.execute("SELECT count(*) FROM capture").fetchone()[0] == 0


@pytest.mark.parametrize(
    "defeito", ["sem_vinculo", "identidade", "hash", "dependentes"]
)
def test_selecao_nao_persiste_documento_sem_fundamento(par_publicado, defeito):
    svc, _, _, _, docs = par_publicado
    d = docs[0]
    if defeito == "sem_vinculo":
        d = replace(d, vinculo={})
    elif defeito == "dependentes":
        d = replace(d, dependentes=())
    else:
        k = "metadados_obtencao_id" if defeito == "identidade" else "metadados_sha256"
        d = replace(d, vinculo={**d.vinculo, k: "x" * 64})
    antes = svc.conn.execute("SELECT count(*) FROM capture").fetchone()[0]
    with pytest.raises(ValueError, match="VINCULO_ASSISTIDO_INVALIDO"):
        persistir(
            svc.conn,
            svc.home,
            PERFIS["normas_leg"],
            [d],
            {0},
            VigiaSintetico(),
            orcamento=t.SessaoPortaAssistida(
                PERFIS["normas_leg"].porta, navegador="sintetico"
            ),
        )
    assert svc.conn.execute("SELECT count(*) FROM capture").fetchone()[0] == antes


@pytest.mark.parametrize("valor", INVALIDOS)
def test_repo_nao_grava_b_sem_vinculo(par_publicado, valor):
    svc, _, _, cs, _ = par_publicado
    data = recibo(cs[1])
    if valor != AUSENTE:
        data["vinculo"] = valor
    with pytest.raises(ValueError, match="VINCULO_ASSISTIDO_INVALIDO"):
        repo.save_capture(
            svc.conn,
            cs[1].resposta,
            "normas_leg",
            home=svc.home,
            procedencia="sessao_assistida",
            assistida=data,
        )


@pytest.mark.parametrize("procedencia", ["snapshot", "sessao_assistida"])
def test_legado_b_e_metadados_a_legitimamente_sem_vinculo(par_publicado, procedencia):
    svc, _, bid, _, _ = par_publicado
    svc.conn.execute(
        "UPDATE capture SET modalidade_acesso=NULL,procedencia=?,assistida_json=NULL WHERE id=?",
        (procedencia, bid),
    )
    _conferir_vinculos_assistidos(
        svc.conn, "main"
    )  # A assistida sem vínculo; B legado sem modalidade.


@pytest.mark.parametrize("tipo", ["service_worker", "worker", "iframe"])
def test_alvo_nao_candidato_nao_exige_metadados_de_candidata(sessao, tipo):
    ad = adapter(sessao)
    ad.alvos["cdp"] = Alvo("outro", tipo, "", True)
    ad.processar(
        {
            "sessionId": "cdp",
            "method": "Network.requestWillBeSent",
            "params": {
                "requestId": "r",
                "frameId": "",
                "request": {"url": URL, "method": "GET"},
                "type": "Document",
            },
        }
    )
    ad.processar(
        {
            "sessionId": "cdp",
            "method": "Network.responseReceived",
            "params": {"requestId": "r"},
        }
    )
    assert not ad.fechado and not ad.pedidos and not ad.canal.comandos
    ad.descartar()


def test_iframe_excluido_antes_de_metadados_de_iniciador(sessao):
    ad = adapter(sessao)
    request(ad, frameId="filho", initiator=None, documentURL=None)
    assert not ad.fechado and not ad.pedidos
    assert ad.motivos_recusas == [(URL, "PEDIDO_ASSISTIDO_SEM_PROVA")]
    ad.descartar()


@pytest.mark.parametrize("outras_flags", [True, False])
def test_sw_sem_tls_ou_extrainfo_recusa_candidata_com_motivo(sessao, outras_flags):
    ad = adapter(sessao)
    request(ad)
    ad.processar(
        {
            "sessionId": "cdp",
            "method": "Network.responseReceived",
            "params": {
                "requestId": "pedido",
                "response": {
                    "fromServiceWorker": True,
                    **(
                        {"fromDiskCache": False, "fromPrefetchCache": False}
                        if outras_flags
                        else {}
                    ),
                },
            },
        }
    )
    assert not ad.fechado and not sessao._encerrada
    assert ad.pedidos["cdp", "pedido"].recusada
    assert ad.motivos_recusas == [(URL, "ORIGEM_ASSISTIDA_SEM_PROVA")]
    # Eventos tardios da resposta já recusada não a readmitem nem invalidam sessão.
    ad.processar(
        {
            "sessionId": "cdp",
            "method": "Network.responseReceivedExtraInfo",
            "params": {"requestId": "pedido"},
        }
    )
    request(ad, rid="boa")
    entregar(ad, rid="boa")
    assert ad.pedidos["cdp", "boa"].admitida is not None
    ad.descartar()


@pytest.mark.parametrize(
    "evento",
    ["requestWillBeSentExtraInfo", "responseReceivedExtraInfo", "responseReceived"],
)
def test_metadado_seguranca_ausente_recusa_so_candidata(sessao, monkeypatch, evento):
    ad = adapter(sessao)
    original = ad._evento

    def truncar(sid, rid, metodo, dados):
        if metodo == evento:
            dados = deepcopy(dados)
            if evento == "responseReceived":
                del dados["response"]["securityDetails"]
            else:
                del dados["headers"]
        return original(sid, rid, metodo, dados)

    monkeypatch.setattr(ad, "_evento", truncar)
    request(ad)
    entregar(ad)
    assert not ad.fechado and ad.pedidos["cdp", "pedido"].recusada
    assert ad.motivos_recusas == [(URL, "METADADOS_SEGURANCA_ASSISTIDOS_AUSENTES")]
    ad.descartar()


def test_resposta_malformada_continua_encerrando_sessao(sessao):
    ad = adapter(sessao)
    request(ad)
    with pytest.raises(RecusaSessao, match="EVENTO_CDP_INVALIDO"):
        ad.processar(
            {
                "sessionId": "cdp",
                "method": "Network.responseReceived",
                "params": {"requestId": "pedido"},
            }
        )
    assert ad.fechado and sessao._encerrada
    ad.descartar()


@pytest.mark.parametrize("observado_em", [2, 3, 4, None])
def test_controles_ate_reproduzir_q_do_adaptador_ou_teto(observado_em):
    com = [_pedido_origem(("Accept-Language", "pt;q=0.6"))]
    chamadas = []

    def executar(nome, observar):
        chamadas.append((nome, observar))
        return (
            com
            if len(chamadas) == observado_em
            else [_pedido_origem(("Accept-Language", "pt;q=0.5"))]
        )

    controles = coletar_controles_passividade(executar, adaptador=com)
    assert len(controles) == (observado_em or 4)
    assert all(not observar for _, observar in chamadas)
    d = comparar_passividade(*controles[:2], com, controles_adicionais=controles[2:])
    assert d["passou"] is (observado_em is not None)
    if observado_em is None:
        assert d["alternativas_nao_observadas"]


def test_q_preserva_combinacao_ocorrencia_e_multiplicidade():
    def pedidos(qs):
        return [_pedido_origem(("Accept-Language", f"pt;q={q}")) for q in qs]

    um, dois = pedidos(["0.5", "0.6"]), pedidos(["0.6", "0.5"])
    assert comparar_passividade(um, dois, dois)["passou"]
    assert not comparar_passividade(um, dois, pedidos(["0.5", "0.5"]))["passou"]


@pytest.mark.parametrize("defeito", ["id", "obtencao", "hash", "urn"])
@pytest.mark.parametrize("valor", [None, "", "outro"])
def test_repo_confronta_referencia_a_antes_de_gravar(par_publicado, defeito, valor):
    svc, aid, _, cs, docs = par_publicado
    campo = {
        "id": "metadados_capture_id",
        "obtencao": "metadados_obtencao_id",
        "hash": "metadados_sha256",
        "urn": "urn",
    }[defeito]
    data = recibo(cs[1], {**docs[0].vinculo, "metadados_capture_id": aid, campo: valor})
    antes = svc.conn.execute("SELECT count(*) FROM capture").fetchone()[0]
    with pytest.raises(ValueError, match="VINCULO_ASSISTIDO_INVALIDO"):
        repo.save_capture(
            svc.conn,
            cs[1].resposta,
            "normas_leg",
            home=svc.home,
            procedencia="sessao_assistida",
            assistida=data,
        )
    assert svc.conn.execute("SELECT count(*) FROM capture").fetchone()[0] == antes


def test_planalto_assistido_sem_vinculo_legitimo(tmp_path, sessao):
    cs = [captura(URL, BODY)]
    docs = resolver_grafo(PERFIS["planalto"], cs, orcamento=sessao)
    with Verifica(home=tmp_path) as svc:
        cid = persistir(
            svc.conn,
            svc.home,
            PERFIS["planalto"],
            docs,
            {0},
            VigiaSintetico(),
            orcamento=sessao,
        )[0]
        _conferir_vinculos_assistidos(svc.conn, "main")
        assert svc.obter_evidencia(cid)["status"] == "encontrada"


def test_recurso_desconhecido_nao_vira_autonomo_por_ausencia_de_vinculo(par_publicado):
    svc, _, bid, _, _ = par_publicado
    adulterar(svc, bid, ("vinculo",), AUSENTE)
    svc.conn.execute(
        "UPDATE capture SET final_url=? WHERE id=?", (BIN + "?invalida", bid)
    )
    with pytest.raises(ValueError, match="snapshot_vinculo_assistido_invalido"):
        _conferir_vinculos_assistidos(svc.conn, "main")


def test_grafo_recusa_colisao_de_obtencao_id(sessao):
    a = captura(META, metadados(), mime="application/json")
    b = replace(captura(BIN, BODY), obtencao_id=a.obtencao_id)
    with pytest.raises(ValueError, match="IDENTIDADE_ASSISTIDA_INVALIDA"):
        resolver_grafo(PERFIS["normas_leg"], [a, b], orcamento=sessao)


@pytest.mark.parametrize(
    "ausente", ["requestWillBeSentExtraInfo", "responseReceivedExtraInfo"]
)
def test_extrainfo_nao_emitido_nao_vira_ausencia_de_credenciais(
    sessao, monkeypatch, ausente
):
    ad = adapter(sessao)
    original = ad._evento

    def omitir(sid, rid, metodo, dados):
        if metodo != ausente:
            return original(sid, rid, metodo, dados)

    monkeypatch.setattr(ad, "_evento", omitir)
    request(ad)
    entregar(ad)
    curso = ad.pedidos["cdp", "pedido"]
    assert curso.admitida is None
    monkeypatch.setattr(ad, "relogio", lambda: curso.inicio + 31)
    ad.fiscalizar_capturas()
    assert not ad.fechado and curso.recusada
    assert ad.motivos_recusas == [(URL, "METADADOS_SEGURANCA_ASSISTIDOS_AUSENTES")]
    ad.descartar()


def test_rotulo_legado_il0_nao_inventa_modalidade_nem_recibo(tmp_path):
    c = captura(URL, BODY)
    with Verifica(home=tmp_path) as svc:
        svc.conn.execute(
            "INSERT INTO source(id,authority,profile,hosts_json) VALUES ('s','a','p','[]')"
        )
        cid = repo.save_capture(
            svc.conn, c.resposta, "s", home=svc.home, procedencia="sessao_assistida"
        )
        row = repo.get_capture(svc.conn, cid)
        assert row["procedencia"] == "sessao_assistida"
        assert row["modalidade_acesso"] is None and row["assistida_json"] is None
        _conferir_vinculos_assistidos(svc.conn, "main")
        out = svc.obter_evidencia(cid)
        assert out["status"] == "encontrada" and "proveniencia" not in out


@pytest.mark.parametrize(
    "url,mime", [(URL, "text/html"), (META, "application/json"), (BIN, "text/html")]
)
def test_recursos_0089_nao_usam_compatibilidade_il0_sem_recibo(tmp_path, url, mime):
    fonte = "planalto" if url == URL else "normas_leg"
    c = captura(url, metadados() if url == META else BODY, mime=mime)
    with Verifica(home=tmp_path) as svc:
        with pytest.raises(ValueError, match="IDENTIDADE_ASSISTIDA_INVALIDA"):
            repo.save_capture(
                svc.conn,
                c.resposta,
                fonte,
                home=svc.home,
                procedencia="sessao_assistida",
            )
        assert svc.conn.execute("SELECT count(*) FROM capture").fetchone()[0] == 0


@pytest.mark.parametrize("procedencia", ["snapshot", "sessao_assistida"])
@pytest.mark.parametrize("modalidade", [None, "automatico", "sessao_assistida"])
def test_recibo_moderno_nao_vira_legado_por_mudanca_de_rotulo(
    par_publicado, procedencia, modalidade
):
    svc, _, bid, _, _ = par_publicado
    adulterar(svc, bid, ("vinculo",), AUSENTE)
    svc.conn.execute(
        "UPDATE capture SET procedencia=?,modalidade_acesso=? WHERE id=?",
        (procedencia, modalidade, bid),
    )
    with pytest.raises(ValueError, match="snapshot_vinculo_assistido_invalido"):
        _conferir_vinculos_assistidos(svc.conn, "main")
    assert svc.obter_evidencia(bid)["motivo"] == "recibo_assistido_invalido"
