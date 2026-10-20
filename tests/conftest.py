"""Fixtures compartilhadas M5 — repositório populado com LSA (só art. 254-A)."""

from __future__ import annotations

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.service import Verifica
from tests.fixture_util import load_fixture, load_meta

LSA_KEY = WorkKey("federal", "lei", "6404", 1976)
WORK_DATE_LSA = "1976-12-15"


@pytest.fixture(scope="session")
def _lsa_art254a():
    """Parse completo uma vez; devolve só o dispositivo usado nos testes M5."""
    body = load_fixture("planalto_lei_6404_1976")
    full = parse_planalto(
        body,
        base_url="https://www.planalto.gov.br/ccivil_03/leis/",
    )
    prov = full.provision("art254-A")
    assert prov is not None
    slim = ParsedDocument(
        profile=full.profile,
        parser_version=full.parser_version,
        title=full.title or "Lei nº 6.404/1976",
        ementa=full.ementa,
        text=prov.redactions[-1].text if prov.redactions else "",
        provisions=[
            Provision(
                path=prov.path,
                label=prov.label,
                scope=prov.scope,
                headings=list(prov.headings),
                redactions=[
                    Redaction(
                        text=r.text,
                        struck=r.struck,
                        order=r.order,
                        annotations=list(r.annotations),
                        span=r.span,
                        superseded_without_strike=r.superseded_without_strike,
                    )
                    for r in prov.redactions
                ],
                ambiguous=prov.ambiguous,
            )
        ],
        issues=list(full.issues),
    )
    entry = load_meta()["planalto_lei_6404_1976"]
    return body, slim, entry


@pytest.fixture
def verifica_populada(tmp_path, monkeypatch, _lsa_art254a):
    home = tmp_path / "fv-m5"
    home.mkdir()
    monkeypatch.setenv("FV_HOME", str(home))
    monkeypatch.setenv("FV_OFFLINE", "1")
    body, doc, entry = _lsa_art254a
    svc = Verifica(home=home)
    rw = svc.indexar_obra(
        source_id="planalto",
        work_key=LSA_KEY,
        document=doc,
        body=body,
        url=entry["url"],
        fetched_at=entry.get("capturado_em"),
        work_date=WORK_DATE_LSA,
        label="Lei nº 6.404/1976",
    )
    yield svc, rw, doc
    svc.close()


@pytest.fixture(autouse=True)
def isolated_staging(tmp_path, monkeypatch):
    """Todo staging de testes permanece no temporario do proprio teste."""
    monkeypatch.setenv("FV_STAGING_DIR", str(tmp_path / "staging-root"))
    # SQLite e subprocessos também precisam de uma raiz gravável por teste.
    for variable in ("TEMP", "TMP", "SQLITE_TMPDIR"):
        monkeypatch.setenv(variable, str(tmp_path))


# Python recente cria ACL privada com mode=0700 no Windows. O token restrito
# precisa que os temporarios de teste herdem a ACL do diretorio do projeto.
import os
from uuid import uuid4
from pathlib import Path
from _pytest.tmpdir import TempPathFactory


if os.name == "nt":
    class _InheritedTempPathFactory(TempPathFactory):
        def getbasetemp(self):
            if self._basetemp is None:
                root = self._given_basetemp or Path(".tmp")
                root = Path(root).resolve()
                root.mkdir(parents=True, exist_ok=True)
                self._basetemp = root / ("pytest-" + uuid4().hex)
                self._basetemp.mkdir()
            return self._basetemp

        def mktemp(self, basename, numbered=True):
            basename = self._ensure_relative_to_basetemp(basename)
            name = basename + uuid4().hex if numbered else basename
            directory = self.getbasetemp() / name
            directory.mkdir()
            return directory

    @pytest.fixture(scope="session")
    def tmp_path_factory(request):
        # Preserva os artefatos para diagnóstico, como a retenção do pytest.
        return _InheritedTempPathFactory.from_config(request.config, _ispytest=True)


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    if os.name == "nt":
        # xdist usa a factory do config antes de solicitar a fixture de sessão.
        # A factory herdável também precisa valer para o controlador Windows.
        config._tmp_path_factory = _InheritedTempPathFactory.from_config(config, _ispytest=True)
    # O teste do pacote instalado roda sem pytest.ini; registra o marcador aqui.
    config.addinivalue_line("markers", "live: testes que acessam fontes oficiais reais")


@pytest.fixture
def planalto_offline(monkeypatch):
    """Planalto servido pela captura real da Lei 6.404/1976 (sem rede); outras obras: `http_404`.

    A decisão 0058 impede cair no Senado após recusa do Planalto; testes que precisam de uma captura
    federal não podem depender de a rede aceitar a requisição.
    """
    import hashlib

    from freoa_verifica.connectors.base import Unavailable
    from freoa_verifica.connectors.planalto import PlanaltoConnector
    from freoa_verifica.transport import Response

    entry = load_meta()["planalto_lei_6404_1976"]

    class _PlanaltoOffline(PlanaltoConnector):
        def fetch(self, candidate):
            if candidate.key != "LEI:6404:1976":
                raise Unavailable("http_404")
            body = load_fixture("planalto_lei_6404_1976")
            return Response(entry["url"], entry["url"], 200, {}, body, hashlib.sha256(body).hexdigest(),
                            entry.get("capturado_em") or "2026-01-01T00:00:00+00:00", [], "text/html")

    original = Verifica._get

    def _get(self, connector_id):
        if connector_id == "planalto" and not isinstance(self._connectors.get("planalto"), _PlanaltoOffline):
            self._connectors["planalto"] = _PlanaltoOffline()
        return original(self, connector_id)

    monkeypatch.setattr(Verifica, "_get", _get)
