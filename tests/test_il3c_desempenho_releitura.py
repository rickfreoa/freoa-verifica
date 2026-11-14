"""Regressão de desempenho da releitura Câmara (CI de 2cf5a0d/ad89d58: jobs > 6 h).

Causa medida (perfil de 9ec8028, LSA): `_revalidar_camara` a ~950 ms por chamada contra ~20 ms na base, 90% em
`detect_challenge -> normalizar_para_busca` repetido sobre os mesmos corpos várias vezes por consulta. Correção:
(1) `normalizar_para_busca` equivalente por `str.translate`; (2) conferência de política/desafio memorizada só
dentro da mesma operação síncrona externa. Hash, status e instante seguem conferidos em toda chamada.
"""
import random
import unicodedata

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors import camara_legin
from freoa_verifica.texto_resposta import normalizar_para_busca
from tests.test_camara_legin import FIX
from tests.test_il2c_r2 import acervo_r2  # noqa: F401 (fixture de módulo: replay offline, sem rede)


def _referencia(texto: str) -> str:
    """Forma anterior, caractere a caractere: o oráculo da equivalência."""
    base = unicodedata.normalize("NFKC", texto).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c))


def test_normalizar_equivale_a_forma_anterior_em_corpos_reais():
    corpos = [p.read_bytes().decode("utf-8", "replace") for p in sorted(FIX.glob("camara_*.html"))[:6]]
    assert corpos
    for corpo in corpos:
        assert normalizar_para_busca(corpo) == _referencia(corpo)


def test_normalizar_equivale_a_forma_anterior_em_unicode_arbitrario():
    rng = random.Random(83)
    alfabeto = ([chr(c) for c in range(0x20, 0x250)] + [chr(c) for c in range(0x300, 0x370)]  # combinantes
                + list("ﬁﬂ²ǅẞİı̇ÅͅẞÅＡ ") + [chr(c) for c in (0x1d400, 0x1f600, 0x0e33)])
    for _ in range(400):
        texto = "".join(rng.choice(alfabeto) for _ in range(rng.randint(0, 200)))
        assert normalizar_para_busca(texto) == _referencia(texto), repr(texto)
    assert normalizar_para_busca("") == ""


def _contar_conferencias(monkeypatch):
    chamadas = []
    original = camara_legin._revalidar

    def contar(resp, url, **kw):
        chamadas.append((url, resp.sha256))
        return original(resp, url, **kw)
    monkeypatch.setattr(camara_legin, "_revalidar", contar)
    return chamadas


def test_memo_vale_so_na_operacao_e_cada_pagina_e_conferida_uma_vez(acervo_r2, monkeypatch):  # noqa: F811
    svc = acervo_r2
    rw = svc._resolve(WorkKey("federal", "lei", "6404", 1976))
    caminho = rw.document.provisions[0].path
    chamadas = _contar_conferencias(monkeypatch)
    primeira = svc.obter_dispositivo(work_id=rw.work_id, caminho=caminho)
    assert primeira.get("status") == "encontrada", primeira
    n = len(chamadas)
    assert n and len(set(chamadas)) == n  # nenhuma página reconferida dentro da mesma operação
    assert getattr(svc._local, "validadas_camara", None) is None  # memo descartado ao fim
    svc.obter_dispositivo(work_id=rw.work_id, caminho=caminho)
    assert len(chamadas) == 2 * n  # nova operação reconfere tudo: nenhuma aprovação persistente
    assert set(chamadas[n:]) == set(chamadas[:n])


def test_releitura_fora_de_operacao_nao_herda_memo(acervo_r2, monkeypatch):  # noqa: F811
    svc = acervo_r2
    rw = svc._resolve(WorkKey("federal", "lei", "6404", 1976))
    chamadas = _contar_conferencias(monkeypatch)
    svc._revalidar_camara(rw)
    n = len(chamadas)
    svc._revalidar_camara(rw)
    assert n and len(chamadas) == 2 * n


def test_hash_e_reconferido_mesmo_com_assinatura_memorizada(acervo_r2, monkeypatch):  # noqa: F811
    """O memo pula só a política/desafio; bytes trocados com a mesma assinatura são recusados."""
    from dataclasses import replace
    from freoa_verifica.connectors.base import Unavailable
    svc = acervo_r2
    rw = svc._resolve(WorkKey("federal", "lei", "6404", 1976))
    pagina = svc._resposta_camara(rw.url, rw.sha256, capture_id=rw.capture_id)
    validadas = set()
    con = camara_legin.CamaraLeginConnector()
    con._validar_response(pagina, pagina.url, validadas=validadas)
    assert validadas
    adulterada = replace(pagina, body=pagina.body + b" ")
    with pytest.raises(Unavailable, match="hash_captura_divergente"):
        con._validar_response(adulterada, pagina.url, validadas=validadas)
