"""Decisão 0039: atualização STJ/STF sem limpar checkpoint."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import freoa_verifica.connectors.stj as stj
import freoa_verifica.semente as seed
from freoa_verifica.semente import SyncState
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response

T0 = datetime(2026, 10, 18, tzinfo=timezone.utc)


class Fonte:
    """CKAN falso: meses 202601..202610, corpo e metadados mutáveis por id."""

    def __init__(self, monkeypatch):
        self.relogio = T0
        self.corpo = {}
        self.meta = {}
        self.fetches = []
        self.resources = [{"id": f"r{m}", "name": f"2026{m:02d}28.json", "format": "JSON",
                           "url": f"https://dadosabertos.web.stj.jus.br/dataset/r{m}"} for m in range(1, 11)]
        monkeypatch.setattr(stj, "_agora", lambda: self.relogio)
        monkeypatch.setattr(stj, "connector_fetch", self.fetch)

    def fetch(self, url, **kw):
        if "package_show" in url:
            res = [{**r, **self.meta.get(r["id"], {})} for r in self.resources]
            body = json.dumps({"success": True, "result": {"resources": res}}).encode()
        else:
            rid = url.rsplit("/", 1)[-1]
            self.fetches.append(rid)
            body = json.dumps([{"id": rid + "-a", "ementa": self.corpo.get(rid, "EMENTA ORIGINAL")}]).encode()
        return Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(),
                        self.relogio.isoformat(), [], "application/json")


def _sync(svc):
    c = svc._get("stj")
    c.sync_state = SyncState(svc.conn)
    return c


def _ementas(c, termo):
    return [h.metadata["ementa"] for h in c.search(termo, limite=5)]


def test_last_modified_alterado_rebaixa_e_atualiza_indice(tmp_path, monkeypatch):
    f = Fonte(monkeypatch)
    f.meta["r3"] = {"last_modified": "2026-03-01"}
    with Verifica(tmp_path) as svc:
        c = _sync(svc)
        c.sync(orgaos=["pkg"])
        f.fetches.clear()
        f.relogio += timedelta(days=1)
        c.sync(orgaos=["pkg"])
        assert "r3" not in f.fetches  # antigo, 1 dia, metadado igual
        f.meta["r3"] = {"last_modified": "2026-10-10"}
        f.corpo["r3"] = "EMENTA CORRIGIDA"
        svc.conn.execute("UPDATE sync_state SET updated_at='2000-01-01T00:00:00+00:00' WHERE fonte='stj_cache'")  # expira o cache de 24 h do package_show
        svc.conn.commit()
        c.sync(orgaos=["pkg"])
        assert "r3" in f.fetches
        assert _ementas(c, "CORRIGIDA") == ["EMENTA CORRIGIDA"]
        assert "EMENTA ORIGINAL" in _ementas(c, "ORIGINAL")[0]  # os outros recursos seguem intactos
        n = svc.conn.execute("SELECT COUNT(*) FROM sync_state WHERE chave LIKE 'resource:r3:%'").fetchone()[0]
        assert n == 1  # checkpoint nunca foi tocado à mão


def test_mes_recente_sempre_revalidado_mesmo_com_checkpoint_e_prior(tmp_path, monkeypatch):
    f = Fonte(monkeypatch)
    with Verifica(tmp_path) as svc:
        c = _sync(svc)
        c.sync(orgaos=["pkg"], max_itens=5)
        c.sync(orgaos=["pkg"], max_itens=7)  # checkpoint/prior de outra chave
        f.fetches.clear()
        c.sync(orgaos=["pkg"], max_itens=5)
        assert sorted(f.fetches) == ["r10", "r9"]
        f.corpo["r10"] = "MUDOU NO MES CORRENTE"
        c.sync(orgaos=["pkg"], max_itens=5)
        assert _ementas(c, "CORRENTE") == ["MUDOU NO MES CORRENTE"]


def test_idade_da_captura_5_dias_nao_baixa_31_dias_baixa(tmp_path, monkeypatch):
    f = Fonte(monkeypatch)
    with Verifica(tmp_path) as svc:
        c = _sync(svc)
        c.sync(orgaos=["pkg"])
        f.relogio += timedelta(days=5)
        f.fetches.clear()
        c.sync(orgaos=["pkg"])
        assert "r1" not in f.fetches
        f.relogio += timedelta(days=26)  # 31 dias desde a captura
        f.fetches.clear()
        c.sync(orgaos=["pkg"])
        assert "r1" in f.fetches and len(f.fetches) == 10


def test_sha_igual_nao_reprocessa_e_carimba(tmp_path, monkeypatch):
    f = Fonte(monkeypatch)
    puts = []
    orig = stj.StjConnector._put
    monkeypatch.setattr(stj.StjConnector, "_put", staticmethod(lambda *a: (puts.append(a[2]), orig(*a))[1]))
    with Verifica(tmp_path) as svc:
        c = _sync(svc)
        c.sync(orgaos=["pkg"])
        puts.clear()
        f.relogio += timedelta(days=40)
        assert c.sync(orgaos=["pkg"]) == 0 and puts == []
        info = json.loads(svc.conn.execute(
            "SELECT payload_json FROM sync_state WHERE chave='resource:r1:None'").fetchone()[0])
        assert info["revalidado_em"] == f.relogio.isoformat() == info["ultima_captura_ok"]
        assert svc.doctor(offline=True)["stj_atualizacao"]["atraso_dias"] == 0
        f.relogio += timedelta(days=3)
        assert stj.resumo_atualizacao(svc.conn)["atraso_dias"] == 3


def test_falha_preserva_ultima_captura_ok(tmp_path, monkeypatch):
    f = Fonte(monkeypatch)
    with Verifica(tmp_path) as svc:
        c = _sync(svc)
        c.sync(orgaos=["pkg"])
        f.relogio += timedelta(days=2)
        real = f.fetch

        def quebra(url, **kw):
            if "dataset/r10" in url:
                raise RuntimeError("fora")
            return real(url, **kw)

        monkeypatch.setattr(stj, "connector_fetch", quebra)
        c.sync(orgaos=["pkg"])
        row = svc.conn.execute("SELECT status,payload_json FROM sync_state WHERE chave='resource:r10:None'").fetchone()
        info = json.loads(row["payload_json"])
        assert row["status"] == "indisponivel" and info["ultima_captura_ok"] == T0.isoformat()
        assert stj.resumo_atualizacao(svc.conn)["atraso_dias"] == 0  # r9 foi revalidado; resumo = captura mais recente


def test_stf_sumulas_revalidadas_apos_30_dias(tmp_path, monkeypatch):
    from tests.test_p5_precedentes_sumulas import _fake_stf_fetch, stf_mod
    monkeypatch.setattr(stf_mod, "connector_fetch", _fake_stf_fetch)
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as svc:
        chamados = []
        orig = svc._index_candidate_juris
        monkeypatch.setattr(svc, "_index_candidate_juris",
                            lambda *a, **k: (chamados.append(a[1].key), orig(*a, **k))[1])
        seed.SementeSync(svc, rate_delay=0, max_itens=9, fontes=["stf"]).sync_stf()
        assert chamados
        chamados.clear()
        seed.SementeSync(svc, rate_delay=0, max_itens=9, fontes=["stf"]).sync_stf()
        ok = {r[0] for r in svc.conn.execute("SELECT chave FROM sync_state WHERE fonte='stf' AND status='parseado'")}
        assert ok and not (set(chamados) & ok)  # parseadas há menos de 30 dias não são refeitas
        velho = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        svc.conn.execute("UPDATE sync_state SET updated_at=? WHERE fonte='stf'", (velho,))
        svc.conn.commit()
        chamados.clear()
        seed.SementeSync(svc, rate_delay=0, max_itens=9, fontes=["stf"]).sync_stf()
        assert ok <= set(chamados)
