"""Auditoria IL.3-c R1: grafos sintéticos inline, sem obtenção nem reserva."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from freoa_verifica import camara_instrumento as ci
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.store import repo
from tests._camara_util import BUSCA, resposta
from tests.test_camara_legin import LSA, ATUAL

B = 'https://www2.camara.leg.br/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-norma-pl.html'
NORMA = {"kind": "lei", "number": "6404", "year": 1976}


def pagina(url, *targets):
    # Gerador sintético: links exatos para adversários de descoberta.
    return resposta(url, ('<html><body>' + ''.join(
        f'<a href="{t}">{label}</a>' for t, label in targets) + '</body></html>').encode())


def descobrir(con, page, *targets):
    con._descobrir(page, {"recursos": [
        {"url": t, "href": t, "rotulo": label, "admitido": True} for t, label in targets]})


def grafo():
    con = CamaraLeginConnector()
    root = pagina(BUSCA, (LSA, 'A'))
    a = pagina(LSA, (ATUAL, 'Texto Atualizado'), (B, 'B'), (LSA, 'A'))
    b = pagina(B, (LSA, 'A'), (ATUAL, 'Texto Atualizado'))
    text = pagina(ATUAL)
    con.paginas.update({p.url: p for p in (root, a, b, text)})
    con.links.update({LSA: (root, LSA, 'A'), B: (a, B, 'B'), ATUAL: (a, ATUAL, 'Texto Atualizado')})
    return con


@pytest.mark.parametrize('defeito,motivo', [
    ('raiz_ausente', 'descoberta_sem_raiz'),
    ('autorreferencia_sem_raiz', 'ciclo_descoberta'),
    ('duas_paginas', 'ciclo_descoberta'),
    ('ancestral_hash', 'hash_ancestral_divergente'),
    ('href', 'vinculo_descoberta_invalido'),
    ('rotulo', 'link_nao_publicado'),
    ('robots_raiz', 'descoberta_sem_raiz'),
    ('raiz_com_antecessor', 'raiz_descoberta_invalida'),
])
def test_preflight_completo_zero_gravacoes(tmp_path, monkeypatch, defeito, motivo):
    con = grafo()
    if defeito == 'raiz_ausente':
        del con.paginas[BUSCA]
    elif defeito == 'autorreferencia_sem_raiz':
        con.links[LSA] = (con.paginas[LSA], LSA, 'A')
    elif defeito == 'duas_paginas':
        con.links[LSA] = (con.paginas[B], LSA, 'A')
    elif defeito == 'ancestral_hash':
        # Aresta tem resposta íntegra, mas diferente da captura do acumulador.
        con.links[LSA] = (pagina(BUSCA, (LSA, 'A'), (B, 'outra')), LSA, 'A')
    elif defeito == 'href':
        con.links[LSA] = (con.paginas[BUSCA], B, 'A')
    elif defeito == 'rotulo':
        con.links[LSA] = (con.paginas[BUSCA], LSA, 'outro')
    elif defeito == 'robots_raiz':
        root = pagina('https://www.camara.leg.br/robots.txt', (LSA, 'A'))
        root = replace(root, mime='text/plain', content_type='text/plain')
        con.paginas[root.url] = root
        con.links[LSA] = (root, LSA, 'A')
    else:
        con.links[BUSCA] = (con.paginas[LSA], BUSCA, 'retorno indevido')
    writes = []
    monkeypatch.setattr(repo, 'save_capture', lambda *a, **k: writes.append('captura'))
    from freoa_verifica import service
    def abrir(*a, **k):
        writes.append('abrir_home')
        raise AssertionError('home aberto antes do preflight')
    monkeypatch.setattr(service, 'Verifica', abrir)
    with pytest.raises(Unavailable, match=motivo):
        ci._persistir_unidade(tmp_path / 'home', con, NORMA)
    assert writes == []
    assert not (tmp_path / 'home').exists()


def test_descobrir_autorreferencia_exige_raiz():
    con = grafo()
    descobrir(con, con.paginas[LSA], (LSA, 'A'))
    assert con.links[LSA][0].url == BUSCA
    assert con.relacoes_observadas[-1]['classe'] == 'autorreferencia'
    del con.links[LSA]
    descobrir(con, con.paginas[LSA], (LSA, 'A'))
    assert LSA not in con.links and con.falhas_descoberta == []
    with pytest.raises(Unavailable):
        con.validar_descoberta(LSA)


def test_descobrir_retorno_e_concorrencia_preservam_proveniencia():
    con = grafo()
    del con.links[B]
    descobrir(con, con.paginas[LSA], (B, 'B'))
    before = dict(con.links)
    chain = con.validar_descoberta(ATUAL)
    descobrir(con, con.paginas[B], (LSA, 'A'), (ATUAL, 'Texto Atualizado'))
    assert con.links == before
    assert all(con.links[url] is edge for url, edge in before.items())
    assert con.validar_descoberta(ATUAL) == chain
    assert con.falhas_descoberta == []
    assert con.relacoes_observadas == [
        {'origem_url': B, 'origem_sha256': con.paginas[B].sha256, 'href': dest,
         'rotulo': label, 'destino': dest, 'classe': classe}
        for dest, label, classe in [(LSA, 'A', 'retorno'), (ATUAL, 'Texto Atualizado', 'concorrente')]]


@pytest.mark.parametrize('variante,motivo', [
    ('hash', 'hash_ancestral_divergente'), ('rotulo', 'link_nao_publicado'),
    ('vazio', 'link_nao_publicado'), ('href', 'link_nao_publicado'),
    ('resposta', 'hash_captura_divergente'), ('origem_ausente', 'descoberta_sem_raiz')])
def test_descobrir_aresta_posterior_invalida_recusada(tmp_path, monkeypatch, variante, motivo):
    con = grafo()
    page, href, label = con.links[ATUAL]
    if variante == 'hash':
        page = pagina(LSA, (ATUAL, label), (B, 'novo'))
    elif variante == 'rotulo':
        label = 'Texto Atualizado novo'
    elif variante == 'vazio':
        label = ''
    elif variante == 'href':
        href = B
    elif variante == 'resposta':
        page = replace(page, sha256='0' * 64)
    else:
        del con.paginas[LSA]
    before = dict(con.links)
    with pytest.raises(Unavailable, match=motivo):
        con._registrar_descoberta(page, ATUAL, href, label)
    assert con.links == before and con.relacoes_observadas == []
    writes = []
    monkeypatch.setattr(repo, 'save_capture', lambda *a, **k: writes.append('captura'))
    from freoa_verifica import service
    monkeypatch.setattr(service, 'Verifica', lambda *a, **k: writes.append('abrir_home'))
    with pytest.raises(Unavailable, match=motivo):
        ci._persistir_unidade(tmp_path / 'home', con, NORMA)
    assert writes == [] and not (tmp_path / 'home').exists()


def test_descobrir_duplicata_equivalente_preserva_aresta():
    con = grafo()
    before = con.links[ATUAL]
    descobrir(con, replace(con.paginas[LSA]), (ATUAL, 'Texto Atualizado'))
    assert con.links[ATUAL] is before
    assert con.relacoes_observadas[-1]['classe'] == 'duplicacao'
    assert con.validar_descoberta(ATUAL)[-1]['origem_url'] == BUSCA


def test_descobrir_varias_relacoes_publicadas_da_mesma_captura():
    con = grafo()
    href = ATUAL.removeprefix('https://www2.camara.leg.br')
    page = resposta(LSA, (f'<a href="{ATUAL}">Texto Atualizado</a>'
                         f'<a href="{href}">Outra relação publicada</a>').encode())
    con.paginas[LSA] = page
    del con.links[ATUAL]
    descobrir(con, page, (ATUAL, 'Texto Atualizado'))
    before = con.links[ATUAL]
    con._descobrir(page, {'recursos': [{'url': ATUAL, 'href': href, 'rotulo': 'Outra relação publicada', 'admitido': True}]})
    assert con.links[ATUAL] is before
    assert con.relacoes_observadas[-1]['classe'] == 'duplicacao'
    assert con.validar_descoberta(ATUAL)[0]['rotulo'] == 'Texto Atualizado'


def test_resolve_isola_descoberta_e_falhas_entre_unidades(monkeypatch):
    con = grafo()
    con.falhas_descoberta.append(Unavailable('link_nao_publicado'))
    con.relacoes_observadas.append({'classe': 'concorrente'})
    def search(_):
        assert con.paginas == con.links == con.inventarios == con._ancoras == {}
        assert con.falhas_descoberta == con.politicas == con.relacoes_observadas == []
        raise Unavailable('fim_do_duble_sem_obtencao')
    monkeypatch.setattr(con, 'search', search)
    with pytest.raises(Unavailable, match='fim_do_duble_sem_obtencao'):
        con.resolve(NORMA)


@pytest.mark.parametrize('local', ['unavailable', 'exception', 'inventario'])
def test_falhas_simultaneas_primeira_causa_e_parada_monotonica(tmp_path, monkeypatch, local):
    from tests.test_camara_0081_atribuicao_inventario_snapshot import normas_em
    monkeypatch.setattr(ci.ativ, 'ativacao', lambda _: True)
    monkeypatch.setattr(ci, '_portao', lambda *a, **k: SimpleNamespace(politica_de={}))
    tentadas = []
    class Con(CamaraLeginConnector):
        def resolve(self, norma):
            tentadas.append(norma['number'])
            raise Unavailable('http_403', 'recusa_identificado',
                              {'bloqueio': 'host_persistente', 'url': LSA, 'sha256': 'a' * 64})
    monkeypatch.setattr(ci, 'CamaraLeginConnector', lambda **kw: Con())
    def persistir(*a):
        if local == 'exception':
            raise RuntimeError('detalhe privado que nao deve vazar')
        raise Unavailable('identidade_nao_confirmada', None, {'sha256': 'b' * 64})
    monkeypatch.setattr(ci, '_persistir_unidade', persistir)
    if local == 'inventario':
        monkeypatch.setattr(ci, '_escrever', lambda *a: (_ for _ in ()).throw(OSError('disco')))
    normas = normas_em(tmp_path)
    normas.write_text(json.dumps([NORMA, {**NORMA, 'number': '13709', 'year': 2018}]))
    out = ci.inventariar(tmp_path / 'home', normas, tmp_path / 'saida')
    assert tentadas == ['6404']
    first, second, *rest = out['falhas']
    assert first == {'fase': 'obtencao', 'motivo': 'http_403', 'categoria': 'recusa_identificado',
                     'bloqueio': 'host_persistente', 'url': LSA,
                     'evidencia': {'bloqueio': 'host_persistente', 'url': LSA, 'sha256': 'a' * 64}}
    assert second['fase'] == 'persistencia_interpretacao'
    assert second['motivo'] == ('persistencia_local_falhou' if local == 'exception' else 'identidade_nao_confirmada')
    assert second['evidencia'] == ({'causa': 'RuntimeError'} if local == 'exception' else {'sha256': 'b' * 64})
    assert out['obtidas'] == 0 and out['nao_obtidas'] == 2
    if local == 'inventario':
        assert rest[0]['fase'] == 'inventario_duravel'
    else:
        inv = json.loads((tmp_path / 'saida/lei-6404-1976/inventario.json').read_bytes())
        assert inv['falha']['motivo'] == 'http_403'
        assert inv['falha']['causas'] == out['falhas']
    assert 'detalhe privado' not in json.dumps(out)


def test_d0_veto_descendente_e_nota_do_caput():
    from freoa_verifica.parsers.camara_legin import parse_camara_legin
    doc = parse_camara_legin('<body><p>Art. 1º (VETADO)</p><p>Art. 2º Corpo.</p>'
                            '<p>§ 1º (VETADO)</p><p>Art. 3º Novo.</p><p>§ 1º Filho.</p>'
                            '<p>(Caput do artigo com redação dada pela Lei nº 10.000, de 1/1/2000)</p></body>')
    from freoa_verifica.parsers.model import RevokedProvision
    for path in ('art1', 'art1.caput', 'art2.par1'):
        assert doc.provision(path).redactions[0].text == ''
    for path in ('art1', 'art2.par1'):
        with pytest.raises(RevokedProvision):
            doc.provision(path).current_text()
    assert doc.provision('art2.caput').current_text() == 'Art. 2º Corpo.'
    assert any(i.code == 'VETO' and i.path == 'art2' for i in doc.issues)
    assert doc.provision('art3.caput').current_text() == 'Art. 3º Novo.'
    ann = doc.provision('art3.caput').redactions[0].annotations
    assert len(ann) == 1 and ann[0].target_path == 'art3.caput' and ann[0].kind == 'redacao_dada'
    assert not doc.provision('art3').redactions[0].annotations
    assert not doc.provision('art3.par1').redactions[0].annotations
