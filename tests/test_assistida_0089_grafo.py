"""0089 (b): cenarios sinteticos offline, sem navegador ou rede."""

from __future__ import annotations

import json

import pytest

from freoa_verifica.assistida.perfis import PERFIS, resolver_grafo

from tests.assistida_0089_util import (
    sessao as sessao,
    captura,
    metadados,
    URL,
    URN,
    UID,
    META,
    BIN,
    BODY,
)


@pytest.mark.parametrize(
    "caso",
    [
        "valido",
        "B_sem_A",
        "urn_divergente",
        "uuid_trocado",
        "duplo_elemento",
        "segunda_A",
        "outra_URN",
        "dois_B_divergentes",
        "dois_B_identicos",
        "version",
        "id",
    ],
)
def test_grafo_completo(sessao, caso):
    args = {}
    if caso == "urn_divergente":
        args["urn"] = URN.replace("6404", "6385")
    if caso == "uuid_trocado":
        args["uid"] = UID.replace("f612", "f613")
    if caso == "version":
        args["version"] = "Atual"
    if caso == "id":
        args["eid"] = URN + "@1976-12-15"
    if caso == "duplo_elemento":
        args["extra"] = json.loads(metadados())["encoding"]
    ca = captura(META, metadados(**args), mime="application/json")
    cb = captura(BIN, BODY)
    cs = [ca, cb]
    if caso == "B_sem_A":
        cs = [cb]
    if caso == "segunda_A":
        cs.append(
            captura(META, metadados() + b" ", ident="a2", mime="application/json")
        )
    if caso == "outra_URN":
        urn = URN.replace("6404", "6385")
        cs.append(
            captura(
                META.replace(URN, urn),
                metadados(urn=urn),
                ident="a2",
                mime="application/json",
            )
        )
    if caso.startswith("dois_B"):
        cs.append(
            captura(
                BIN, BODY if caso.endswith("identicos") else BODY + b" ", ident="b2"
            )
        )
    docs = resolver_grafo(PERFIS["normas_leg"], cs, orcamento=sessao)
    assert len(docs) == (1 if caso in {"valido", "dois_B_identicos"} else 0)
    if docs:
        assert docs[0].dependentes == (ca,)
        assert docs[0].vinculo["metadados_sha256"] == ca.resposta.sha256
        assert docs[0].vinculo["legislationLegalValue"] == "UnofficialLegalValue"


def test_url_publica_gramatica_limite_declarado():
    # Risco residual normativo: um nome que pareça token mas satisfaça a classe pública
    # é sanitizável; não se inventa um detector semântico de segredos.
    url = URL.replace("l6404", "TOKEN_PUBLICO_123")
    assert PERFIS["planalto"].sanitizar(url) == url
    assert PERFIS["planalto"].sanitizar(url + "?token=segredo") is None
