"""0091 emenda A: metadados normas.leg como gatilho, escopo do home e manutenção agendada."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors import normas_leg as nl
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica import revalidacao as rev
from freoa_verifica.service import Verifica, SourceUnavailable
from tests._camara_util import RelogioFalso, Transporte, resposta
from tests.fixture_util import load_fixture

ROBOTS = nl.BASE + "/robots.txt"
KEY = WorkKey("federal", "lei_complementar", "118", 2005)
URN = nl.urn_da_chave(KEY)
T0 = "2026-01-01T00:00:00+00:00"


def _meta_url(urn: str = URN) -> str:
    return nl.url_metadados(urn)


def _meta_base() -> dict:
    # Derivação sintética a partir da captura real LC 118 (sem editar o fixture).
    base = json.loads(load_fixture("normas_leg_meta_mp2158"))
    base["urn"] = URN
    base["legislationIdentifier"] = URN
    base["dateModified"] = "2026-10-16"
    for item in base["encoding"]:
        if item.get("version") == "Current" and item.get("inLanguage") == "pt":
            item["encodesCreativeWork"] = {
                "@id": f"https://normas.leg.br/?urn={URN}@2026-10-16~texto;pt"
            }
    return base


def _obra(svc: Verifica, corpo: str = "<p>Art. 1º Teste.</p>") -> str:
    body = f"<html><body><p>LC 118/2005</p>{corpo}</body></html>".encode()
    url = "https://example.invalid/lc118.htm"
    svc.indexar_obra(
        source_id="planalto",
        work_key=KEY,
        document=parse_planalto(body, base_url=url),
        body=body,
        url=url,
        label="LC 118/2005",
        fetched_at=T0,
        content_type="text/html; charset=utf-8",
    )
    return svc.conn.execute("SELECT id FROM work WHERE authority='federal' AND kind='lei_complementar' "
                            "AND number='118' AND year=2005").fetchone()[0]


def _portao(tmp_path, rotas: dict):
    relogio = RelogioFalso()
    tr = Transporte(relogio, {ROBOTS: resposta(ROBOTS, b"User-agent: *\nAllow: /\n", mime="text/plain"), **rotas})
    return nl.NormasLegConnector(home=tmp_path, portao=nl.NormasPortao(tr, home=tmp_path, relogio=relogio)), tr


def test_url_metadados_literal_e_admitida():
    url = _meta_url()
    assert "%3A" not in url and URN in url
    info = nl.admitir(url)
    assert info["recurso"] == "metadados"


def test_sinal_extraido_da_derivacao_sintetica():
    sinal = rev.sinal_de_metadados(_meta_base())
    assert sinal == {"date_modified": "2026-10-16", "versao_current": "2026-10-16"}


def test_sinal_none_sem_current_pt():
    meta = _meta_base()
    meta["dateModified"] = None
    meta["encoding"] = [e for e in meta["encoding"] if e.get("version") != "Current"]
    assert rev.sinal_de_metadados(meta) is None


@pytest.mark.repositorio  # lê o código-fonte do repositório; fora da seleção da wheel
def test_gatilho_nao_entra_em_outros_modulos():
    raiz = Path(__file__).resolve().parents[1] / "freoa_verifica"
    permitidos = {raiz / "revalidacao.py", raiz / "service.py", raiz / "cli.py", raiz / "bateria.py"}
    for path in raiz.rglob("*.py"):
        if path in permitidos:
            continue
        texto = path.read_text(encoding="utf-8")
        for tok in (rev.FONTE_META, rev.FONTE_PENDENTE):
            assert not re.search(rf"\b{re.escape(tok)}\b", texto), f"{path} referencia {tok}"


def test_primeira_leitura_e_inalterado_e_alterado(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    meta = _meta_base()
    url = _meta_url()
    con, _ = _portao(tmp_path, {url: resposta(url, json.dumps(meta).encode(), mime="application/json")})
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        svc._connectors["normas_leg"] = con
        r1 = rev.revalidar(svc)
        assert r1["resultados"][0]["resultado"] == "primeira_leitura"
        assert svc.conn.execute("SELECT 1 FROM sync_state WHERE fonte=? AND chave=?",
                                (rev.FONTE_META, work_id)).fetchone()
        assert svc.conn.execute("SELECT 1 FROM sync_state WHERE fonte=? AND chave=?",
                                (rev.FONTE_PENDENTE, work_id)).fetchone() is None
        r2 = rev.revalidar(svc)
        assert r2["resultados"][0]["resultado"] == "inalterado"
        meta2 = {**meta, "dateModified": "2026-11-01"}
        con.paginas.clear()
        con, _ = _portao(tmp_path, {url: resposta(url, json.dumps(meta2).encode(), mime="application/json")})
        svc._connectors["normas_leg"] = con
        r3 = rev.revalidar(svc)
        assert r3["resultados"][0]["resultado"] == "alterado"
        row = svc.conn.execute("SELECT motivo FROM sync_state WHERE fonte=? AND chave=?",
                               (rev.FONTE_PENDENTE, work_id)).fetchone()
        assert row[0] == "metadados_alterados"


def test_falha_nao_marca_pendente(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    url = _meta_url()
    con, tr = _portao(tmp_path, {})
    tr.rotas[url] = Unavailable("resposta_inesperada", evidencia={"status": 500})
    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        svc._connectors["normas_leg"] = con
        r = rev.revalidar(svc)
        assert r["resultados"][0]["resultado"] == "indisponivel"
        assert svc.conn.execute("SELECT 1 FROM sync_state WHERE fonte=?", (rev.FONTE_PENDENTE,)).fetchone() is None
        assert svc.conn.execute("SELECT COUNT(*) FROM sync_state WHERE fonte=? AND chave=?",
                                (rev.FONTE_META, work_id)).fetchone()[0] == 0


def test_host_barrado_para_obras_restantes(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    url = _meta_url()
    con, tr = _portao(tmp_path, {})
    tr.rotas[url] = Unavailable("desafio_captcha", "ambiental_desafio", {"status": 403})
    with Verifica(tmp_path) as svc:
        _obra(svc)
        body = b"<html><body><p>Lei 6404</p><p>Art. 1.</p></body></html>"
        url2 = "https://example.invalid/l6404.htm"
        svc.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "6404", 1976),
                         document=parse_planalto(body, base_url=url2), body=body, url=url2, label="Lei 6404/1976",
                         fetched_at=T0, content_type="text/html; charset=utf-8")
        svc._connectors["normas_leg"] = con
        r = rev.revalidar(svc, limite=5)
        assert any(x["resultado"] == "indisponivel" and x["motivo"] == "host_barrado" for x in r["resultados"][1:])


def test_sem_escopo_json_comportamento_anterior(tmp_path):
    assert not rev.escopo_restrito(tmp_path)


def test_escopo_restrito_fora_da_manutencao(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    rev.gravar_escopo(tmp_path, "decisão de teste")
    body = b"<html><body><p>LC 118</p><p>Art. 1.</p></body></html>"
    url = "https://example.invalid/lc118.htm"

    class _CamaraFora:
        def resolve(self, key):
            raise Unavailable("especie_busca_nao_demonstrada")

    with Verifica(tmp_path) as svc:
        svc.indexar_obra(source_id="planalto", work_key=KEY, document=parse_planalto(body, base_url=url),
                         body=body, url=url, label="LC 118", fetched_at=T0, content_type="text/html; charset=utf-8")
        con, _ = _portao(tmp_path, {})
        svc._connectors["normas_leg"] = con
        svc._connectors["camara_legin"] = _CamaraFora()
        with pytest.raises(SourceUnavailable) as exc:
            svc._capture_work(KEY)
        assert any(c["resultado"] == "fora_do_escopo_do_home" and c["fonte"] == "normas_leg"
                   for c in exc.value.fontes_consultadas)


def test_abrir_normas_leg_grava_escopo_e_reabertura(tmp_path):
    with Verifica(tmp_path) as svc:
        con, _ = _portao(tmp_path, {})
        svc._connectors["normas_leg"] = con
        r = svc.abrir_normas_leg("titular autorizou metadados")
        assert (tmp_path / "normas_leg" / "escopo.json").is_file()
        assert r["escopo"]["decisao"] == "titular autorizou metadados"
        assert r["reaberturas"]


def test_pendente_renovado_apaga_marca(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    from freoa_verifica.verify import ResolvedWork

    with Verifica(tmp_path) as svc:
        work_id = _obra(svc)
        rev._gravar_sync(svc.conn, rev.FONTE_PENDENTE, work_id, "pendente", motivo="metadados_alterados", payload={})
        captura = svc.conn.execute("SELECT capture_id FROM parsed_document WHERE work_id=?", (work_id,)).fetchone()[0]
        doc = parse_planalto(b"<html><body><p>Art. 1</p></body></html>", base_url="https://example.invalid")
        falsa = ResolvedWork(work_id=work_id, work_key=KEY, work_date=None, source_id="normas_leg", capture_id=captura,
                             fetched_at=T0, url="https://example.invalid", sha256="0" * 64, document=doc,
                             quarantined=False)
        monkeypatch.setattr(svc, "_capture_work", lambda *a, **k: falsa)
        r = svc.renovar_acervo(dias=9999, limite=5)
        assert r["renovadas"]
        assert svc.conn.execute("SELECT 1 FROM sync_state WHERE fonte=? AND chave=?",
                                (rev.FONTE_PENDENTE, work_id)).fetchone() is None


def test_manter_grava_manutencao_json(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path) as svc:
        out = svc.manter_acervo()
        assert (tmp_path / "manutencao.json").is_file()
        assert out["status"] == "indisponivel"


def test_doctor_acervo_manutencao_alertas(tmp_path):
    velho = (datetime.now(timezone.utc) - timedelta(hours=49)).replace(microsecond=0).isoformat()
    (tmp_path / "manutencao.json").write_text(json.dumps({"status": "ok", "fim": velho}), encoding="utf-8")
    chk = rev.consulta_manutencao(tmp_path)
    assert chk["nome"] == "acervo_manutencao" and chk["status"] == "alerta"
    (tmp_path / "manutencao.json").write_text(json.dumps({"status": "parcial", "fim": velho}), encoding="utf-8")
    chk2 = rev.consulta_manutencao(tmp_path)
    assert chk2["status"] == "falha"


def test_agendar_monta_comando_windows_e_linux(tmp_path, monkeypatch):
    from freoa_verifica import acervo_manutencao as agenda

    chamadas: list[list[str]] = []
    agenda.definir_executar_sistema(lambda cmd: chamadas.append(cmd) or (0, "ok", ""))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(agenda, "caminho_fv", lambda: Path(r"C:\venv\Scripts\fv.exe"))
    agenda.agendar_instalar(tmp_path, "05:43")
    assert chamadas and chamadas[0][0] == "schtasks"
    xml_tarefa = Path(chamadas[0][chamadas[0].index("/XML") + 1]).read_text(encoding="utf-16")
    assert "/RU" not in chamadas[0] and "--home" in xml_tarefa and "<StartWhenAvailable>true" in xml_tarefa
    chamadas.clear()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(agenda.Path, "home", classmethod(lambda cls: tmp_path))  # nunca o ~/.config real
    agenda.agendar_instalar(tmp_path, "06:00")
    assert (tmp_path / ".config" / "systemd" / "user" / "fv-manter.timer").is_file()
    assert any(c[0] == "systemctl" for c in chamadas)
    agenda.definir_executar_sistema(None)


def test_linha_agendada_e_aceita_pelo_parser_do_fv(tmp_path):
    """--home é opção global do `fv`: depois do subcomando o argparse recusaria a tarefa inteira."""
    from freoa_verifica import acervo_manutencao as agenda
    from freoa_verifica.cli import build_parser

    home = tmp_path / "home com espaço"
    args = build_parser().parse_args(agenda.argumentos(home))
    assert args.cmd == "acervo" and args.acervo_cmd == "manter" and args.home == str(home)
    xml = agenda.xml_tarefa(home, "05:43")  # gerado pelo próprio código: conferido como texto, sem parser XML
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml and "<RunLevel>LeastPrivilege</RunLevel>" in xml
    argumentos_xml = xml.split("<Arguments>", 1)[1].split("</Arguments>", 1)[0]
    assert argumentos_xml.startswith("--home ") and argumentos_xml.endswith("acervo manter --json")
    assert agenda.conteudo_systemd_service(home).count("--home") == 1
