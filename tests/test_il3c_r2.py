"""IL.3-c R2: fronteiras reais com grafos sintéticos, sem parser filho ou rede."""
import json
import hashlib
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from freoa_verifica import camara_instrumento as ci
from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Candidate, LocalParserFailure, Unavailable
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.parsers.camara_legin import parse_camara_legin
from freoa_verifica.parsers.model import EditorialBlock
from freoa_verifica.service import Verifica, SourceUnavailable
from freoa_verifica.store import repo
from tests._camara_util import BUSCA
from tests.test_il3c_r1 import grafo, pagina, LSA, ATUAL, B, NORMA

KEY = WorkKey('federal', 'lei', '6404', 1976)
CASES = [
    ('raiz_ausente', 'descoberta_sem_raiz'),
    ('autorreferencia_sem_raiz', 'ciclo_descoberta'),
    ('duas_paginas', 'ciclo_descoberta'),
    ('ancestral_hash', 'hash_ancestral_divergente'),
    ('href', 'vinculo_descoberta_invalido'),
    ('rotulo', 'link_nao_publicado'),
    ('robots_raiz', 'descoberta_sem_raiz'),
    ('raiz_com_antecessor', 'raiz_descoberta_invalida'),
    ('orfa', 'vinculo_descoberta_ausente'),
    ('falha_retida', 'link_nao_publicado'),
]


def defeituoso(case):
    con = grafo()
    if case == 'raiz_ausente':
        del con.paginas[BUSCA]
    elif case == 'autorreferencia_sem_raiz':
        con.links[LSA] = (con.paginas[LSA], LSA, 'A')
    elif case == 'duas_paginas':
        con.links[LSA] = (con.paginas[B], LSA, 'A')
    elif case == 'ancestral_hash':
        con.links[LSA] = (pagina(BUSCA, (LSA, 'A'), (B, 'outra')), LSA, 'A')
    elif case == 'href':
        con.links[LSA] = (con.paginas[BUSCA], B, 'A')
    elif case == 'rotulo':
        con.links[LSA] = (con.paginas[BUSCA], LSA, 'outro')
    elif case == 'robots_raiz':
        root = replace(pagina('https://www.camara.leg.br/robots.txt', (LSA, 'A')),
                       mime='text/plain', content_type='text/plain')
        con.paginas[root.url] = root
        con.links[LSA] = (root, LSA, 'A')
    elif case == 'raiz_com_antecessor':
        con.links[BUSCA] = (con.paginas[LSA], BUSCA, 'retorno indevido')
    elif case == 'orfa':
        del con.links[B]
    elif case == 'falha_retida':
        # Mesmo resultado parcial de capturar_relacoes: a cadeia principal segue válida.
        con.falhas_descoberta.append(Unavailable('link_nao_publicado'))
    return con


def documento(con):
    doc = parse_camara_legin('<p>Art. 1º Texto sintético.</p>')
    doc.title = 'Lei nº 6.404, de 15 de dezembro de 1976'
    inv = {'pagina': {'url': LSA, 'sha256': con.paginas[LSA].sha256},
           'recursos': [{'url': ATUAL, 'admitido': True, 'href': ATUAL, 'rotulo': 'Texto Atualizado', 'recurso': 'atualizado', 'acao': None}],
           'descoberta': grafo().validar_descoberta(ATUAL),
           'falhas_descoberta': [{'motivo': f.reason} for f in con.falhas_descoberta]}
    doc.editorial_blocks.append(EditorialBlock(json.dumps(inv), (0, 0), 'camara_inventario'))
    con.registrar_conjunto(doc)
    return doc


def preparar_servico(svc, con, monkeypatch, writes):
    doc = documento(con)
    cand = Candidate(con.id, '6404', doc.title, LSA, metadata=NORMA)
    monkeypatch.setattr(con, 'resolve', lambda *a: cand)
    monkeypatch.setattr(con, 'fetch', lambda *a: con.paginas[ATUAL])
    monkeypatch.setattr(con, 'parse', lambda *a: doc)
    monkeypatch.setattr(svc, '_get', lambda *a: con)
    monkeypatch.setattr(svc, '_offline', lambda: False)
    monkeypatch.setattr(svc, '_camara_ativada', lambda: True)
    monkeypatch.setattr(svc, 'indexar_obra', lambda **k: writes.append('indexar') or SimpleNamespace(
        capture_id='c', work_id='w', sha256=con.paginas[ATUAL].sha256, url=ATUAL, fetched_at=con.paginas[ATUAL].fetched_at))
    monkeypatch.setattr(repo, 'save_capture', lambda *a, **k: writes.append('captura'))
    return cand, doc


@pytest.mark.parametrize('case,reason', CASES)
@pytest.mark.parametrize('boundary', ['instrumento', 'captura', 'candidato', 'indexar', 'historico', 'releitura'])
def test_n1_fronteiras_zero_gravacoes(tmp_path, monkeypatch, boundary, case, reason):
    con = defeituoso(case)
    writes = []
    if boundary == 'instrumento':
        from freoa_verifica import service
        monkeypatch.setattr(service, 'Verifica', lambda *a, **k: writes.append('abrir_home'))
        with pytest.raises(Unavailable) as exc:
            ci._persistir_unidade(tmp_path / 'nao-aberto', con, NORMA)
        assert exc.value.reason == reason
    else:
        with Verifica(home=tmp_path / 'h') as svc:
            original_indexar = svc.indexar_obra
            cand, doc = preparar_servico(svc, con, monkeypatch, writes)
            if boundary == 'captura':
                with pytest.raises(SourceUnavailable) as exc:
                    svc._capture_work(KEY)
                assert exc.value.fontes_consultadas[-1]['motivo'] == reason
            elif boundary == 'candidato':
                out = svc._index_candidate_legis(con, cand)
                assert out['motivo'] == reason
            elif boundary == 'indexar':
                with pytest.raises(Unavailable) as exc:
                    original_indexar(source_id=con.id, work_key=KEY, document=doc, body=con.paginas[ATUAL].body,
                                     url=ATUAL, descoberta_camara=con)
                assert exc.value.reason == reason
            elif boundary == 'historico':
                monkeypatch.setattr(svc, '_selecionar_camara', lambda *a: object())
                monkeypatch.setattr(con, 'capturar_relacoes', lambda *a: {
                    'materiais': [{'resposta': con.paginas[ATUAL], 'documento': doc}],
                    'pendencias': [], 'indisponibilidades': [], 'cadeia_completa': False})
                out = {}
                rw = SimpleNamespace(source_id=con.id, work_key=KEY, document=doc)
                svc._material_historico_camara(out, rw, 'art1', '2000-01-01')
                assert out['indisponibilidades_temporais'][0]['motivo'] == reason
            else:
                def carregar(url, digest, **kw):
                    page = con.paginas.get(url)
                    if page is None:
                        raise Unavailable('descoberta_sem_raiz')
                    if page.sha256 != digest:
                        raise Unavailable('hash_ancestral_divergente')
                    return page
                monkeypatch.setattr(svc, '_resposta_camara', carregar)
                monkeypatch.setattr(svc, '_authenticate_capture', lambda _: None)
                with pytest.raises(SourceUnavailable) as exc:
                    svc._revalidar_camara(SimpleNamespace(document=doc, url=ATUAL, sha256=con.paginas[ATUAL].sha256, capture_id='texto'))
                assert exc.value.reason == 'camara_releitura_sem_vinculo_validado'
            assert svc.conn.execute("SELECT count(*) FROM capture").fetchone()[0] == 0
            assert svc.conn.execute("SELECT count(*) FROM work").fetchone()[0] == 0
    assert writes == []


@pytest.fixture
def snapshot_valido(tmp_path):
    con = grafo()
    doc = documento(con)
    from freoa_verifica.snapshot import export_snapshot
    with Verifica(home=tmp_path / 'origem') as svc:
        svc.conn.execute("INSERT INTO source(id, authority, profile, hosts_json) VALUES (?,?,?,?)",
                         (con.id, con.authority, con.id, json.dumps(sorted(con.hosts))))
        for page in con.paginas.values():
            repo.save_capture(svc.conn, page, con.id, home=svc.home)
        rw = svc.indexar_obra(source_id=con.id, work_key=KEY, document=doc, body=con.paginas[ATUAL].body,
                             url=ATUAL, fetched_at=con.paginas[ATUAL].fetched_at, descoberta_camara=con,
                             content_type='text/html; charset=utf-8')
        dest = tmp_path / 'snap'
        assert export_snapshot(svc.conn, svc.home, dest)['status'] == 'ok'
    return dest, rw.capture_id


@pytest.mark.parametrize('case,reason', CASES)
def test_n1_snapshot_instalacao_zero_publicacao(tmp_path, monkeypatch, snapshot_valido, case, reason):
    import sqlite3
    from freoa_verifica import snapshot
    from tests.test_camara_0080_atribuicao import refazer_checksums
    dest, capture_id = snapshot_valido
    con = defeituoso(case)
    doc = documento(con)
    manifest = json.loads((dest / 'MANIFEST.json').read_text('utf-8'))
    for name in {manifest['db_arquivo'], 'verifica.sqlite3'}:
        conn = sqlite3.connect(dest / name)
        conn.execute('UPDATE parsed_document SET model_json=? WHERE capture_id=?', (json.dumps(asdict(doc)), capture_id))
        conn.commit()
        conn.close()
    manifest['db_sha256'] = hashlib.sha256((dest / manifest['db_arquivo']).read_bytes()).hexdigest()
    (dest / 'MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    refazer_checksums(dest)
    with Verifica(home=tmp_path / 'novo') as svc:
        before = sorted((str(p.relative_to(svc.home)), p.read_bytes()) for p in svc.home.rglob('*') if p.is_file() and 'sqlite' not in p.name and '.fv-uso' not in p.parts)
        out = snapshot._install_from_dir(svc, dest)
        assert out['status'] == 'erro' and out['motivo'] == 'camara_descoberta_invalida', (reason, out)
        assert svc.conn.execute('SELECT count(*) FROM capture').fetchone()[0] == 0
        assert sorted((str(p.relative_to(svc.home)), p.read_bytes()) for p in svc.home.rglob('*') if p.is_file() and 'sqlite' not in p.name and '.fv-uso' not in p.parts) == before


@pytest.mark.parametrize('profile', ['camara_legin', 'camara_anexo'])
@pytest.mark.parametrize('failure', ['stderr', 'processo', 'runtime', 'io', 'legada'])
def test_n2_parser_sem_texto_livre(monkeypatch, profile, failure):
    from freoa_verifica.parsers import isolated
    from freoa_verifica.connectors.base import sanitizar_falha_parser
    private = 'C:/dev/tmp/SYNTHETIC_PRIVATE child detail'
    if failure == 'legada':
        exc = LocalParserFailure(private, None, {'causa': private, 'stderr': private, 'perfil': private})
    else:
        if failure in {'processo', 'runtime'}:
            def popen(*a, **k):
                if failure == 'runtime':
                    raise RuntimeError(private)
                raise OSError(private)
            monkeypatch.setattr(isolated.subprocess, 'Popen', popen)
        elif failure == 'io':
            monkeypatch.setattr(isolated.subprocess, 'Popen', lambda *a, **k: SimpleNamespace(returncode=0, kill=lambda: None))
            def io(*a):
                raise RuntimeError(private)
            monkeypatch.setattr(isolated, '_bounded_io', io)
        else:
            monkeypatch.setattr(isolated.subprocess, 'Popen', lambda *a, **k: SimpleNamespace(returncode=4))
            monkeypatch.setattr(isolated, '_bounded_io', lambda *a: (b'', private.encode(), None))
        doc = isolated.parse_isolated(profile, b'x', 1)
        assert private not in json.dumps(asdict(doc))
        with pytest.raises(LocalParserFailure) as error:
            isolated.parse_ou_indisponivel(profile, b'x', 1)
        exc = error.value
    safe = sanitizar_falha_parser(exc, perfil=profile, url=ATUAL, sha256='a' * 64)
    assert safe.evidencia['causa'] == {'stderr': 'exit_nao_zero', 'processo': 'criacao_processo',
                                       'runtime': 'criacao_processo', 'io': 'protocolo', 'legada': 'protocolo'}[failure]
    out = ci._causa(Unavailable('falha_parser_camara', None, {**safe.evidencia, 'stderr': private}), 'persistencia_interpretacao')
    assert private not in json.dumps(out)
    assert set(out['evidencia']) <= {'fase', 'perfil', 'causa', 'url', 'sha256', 'exit_code'}


def test_compromisso_falha_preserva_causas_e_parada(tmp_path, monkeypatch):
    from tests.test_camara_0081_atribuicao_inventario_snapshot import normas_em
    monkeypatch.setattr(ci.ativ, 'ativacao', lambda _: True)
    monkeypatch.setattr(ci, '_portao', lambda *a, **k: SimpleNamespace(politica_de={}))
    tentadas = []
    class Con(CamaraLeginConnector):
        def resolve(self, norma):
            tentadas.append(norma['number'])
            raise Unavailable('http_403', 'recusa_identificado', {'bloqueio': 'host_persistente'})
    monkeypatch.setattr(ci, 'CamaraLeginConnector', lambda **k: Con())
    monkeypatch.setattr(ci, '_persistir_unidade', lambda *a: (_ for _ in ()).throw(LocalParserFailure('privado')))
    original = ci._escrever
    def escrever(path, data):
        if path.name == 'compromisso.json':
            raise OSError('C:/dev/tmp/SYNTHETIC_PRIVATE')
        return original(path, data)
    monkeypatch.setattr(ci, '_escrever', escrever)
    normas = normas_em(tmp_path)
    normas.write_text(json.dumps([NORMA, {**NORMA, 'number': '13709', 'year': 2018}]))
    chave = tmp_path / 'chave'
    chave.write_bytes(b'x' * 32)
    out = ci.inventariar(tmp_path / 'home', normas, tmp_path / 'saida', chave_hmac=chave)
    assert tentadas == ['6404']
    assert [c['fase'] for c in out['falhas']] == ['obtencao', 'persistencia_interpretacao', 'compromisso']
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(out)

def test_historico_falha_absorvida_por_capturar_relacoes(tmp_path, monkeypatch):
    con = grafo()
    con.inventarios[LSA] = {'recursos': [{'url': B, 'acao': 'altera', 'admitido': True}]}
    monkeypatch.setattr(con, '_obter_recurso', lambda url: con.paginas[url])
    monkeypatch.setattr(con, '_inventario', lambda page: {'recursos': [
        {'url': ATUAL, 'href': ATUAL, 'rotulo': 'nao publicado', 'admitido': True}]})
    cand = Candidate(con.id, '6404', '', LSA)
    partial = con.capturar_relacoes(cand)
    assert partial['indisponibilidades'][0]['motivo'] == 'link_nao_publicado'
    assert con.falhas_descoberta[0].reason == 'link_nao_publicado'
    with Verifica(home=tmp_path / 'h') as svc:
        writes = []
        _, doc = preparar_servico(svc, con, monkeypatch, writes)
        monkeypatch.setattr(svc, '_selecionar_camara', lambda *a: object())
        monkeypatch.setattr(con, 'capturar_relacoes', lambda *a: partial)
        out = {}
        svc._material_historico_camara(out, SimpleNamespace(source_id=con.id, work_key=KEY, document=doc),
                                     'art1', '2000-01-01')
        assert writes == []  # auditoria: antes eram solicitadas quatro capturas.
        assert out['indisponibilidades_temporais'][-1]['motivo'] == 'link_nao_publicado'


@pytest.mark.parametrize('case,reason', CASES)
def test_n1_exportacao_sem_publicacao(tmp_path, monkeypatch, case, reason):
    from freoa_verifica import snapshot
    from freoa_verifica.connectors import camara_descoberta
    con = defeituoso(case)
    doc = documento(con)
    def validar(conn, home):
        rebuilt = camara_descoberta.reconstruir(doc, con.paginas[ATUAL],
                                               lambda url, digest, **kw: con.paginas[url])
        rebuilt.validar_conjunto()
    monkeypatch.setattr(camara_descoberta, 'validar_acervo', validar)
    with Verifica(home=tmp_path / 'h') as svc:
        out = snapshot.export_snapshot(svc.conn, svc.home, tmp_path / 'nao-publicado')
    assert out == {'status': 'erro', 'motivo': 'camara_descoberta_invalida'}, reason
    assert not (tmp_path / 'nao-publicado').exists()


def test_snapshot_valido_instala_e_rele(tmp_path, snapshot_valido, monkeypatch):
    from freoa_verifica import snapshot
    dest, capture_id = snapshot_valido
    with Verifica(home=tmp_path / 'novo') as svc:
        assert snapshot._install_from_dir(svc, dest)['status'] == 'ok'
        row = repo.get_parsed_document(svc.conn, capture_id)
        from freoa_verifica.parsers.model import document_from_dict
        doc = document_from_dict(json.loads(row['model_json']))
        svc._revalidar_camara(SimpleNamespace(document=doc, url=ATUAL, sha256=grafo().paginas[ATUAL].sha256, capture_id=capture_id))
        assert svc.snapshot_export(tmp_path / 'reexportado')['status'] == 'ok'


@pytest.mark.parametrize('profile', ['camara_legin', 'camara_anexo'])
@pytest.mark.parametrize('origin', ['stderr', 'excecao'])
def test_n2_conector_portao_inventario_servico_e_fachadas(tmp_path, monkeypatch, profile, origin):
    from freoa_verifica.parsers import isolated
    from tests._camara_util import portao, resposta
    from freoa_verifica.connectors.guarda import da_chamada
    con = grafo()
    target = ATUAL
    if profile == 'camara_anexo':
        target = 'https://www2.camara.leg.br/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-anexo-pl.pdf'
        page = pagina(B, (target, 'Anexo'))
        con.paginas[B] = page
        con.paginas[target] = resposta(target, b'%PDF-1.7\nsynthetic', mime='application/pdf')
        con.links[target] = (page, target, 'Anexo')
    private = 'C:/dev/tmp/SYNTHETIC_PRIVATE child detail'
    if origin == 'excecao':
        def popen(*a, **kw):
            raise OSError(private)
        monkeypatch.setattr(isolated.subprocess, 'Popen', popen)
    else:
        monkeypatch.setattr(isolated.subprocess, 'Popen', lambda *a, **kw: SimpleNamespace(returncode=4))
        monkeypatch.setattr(isolated, '_bounded_io', lambda *a: (b'', private.encode(), None))
    with pytest.raises(Unavailable) as error:
        con.parse(con.paginas[target])
    failure = error.value
    assert failure.reason == 'falha_parser_camara'
    assert failure.evidencia['perfil'] == profile
    p, _, _, _ = portao(tmp_path / 'portao')
    with da_chamada():
        kept = p.falha_local_de_interpretacao(Unavailable('falha_parser_camara', None,
                                                        {**failure.evidencia, 'stderr': private}))
        with pytest.raises(Unavailable) as terminal:
            p.obter(LSA)
        assert terminal.value.evidencia == kept.evidencia == failure.evidencia
    # Inventário durável e retorno do instrumento passam pelo tratamento real.
    monkeypatch.setattr(ci.ativ, 'ativacao', lambda _: True)
    monkeypatch.setattr(ci, '_portao', lambda *a, **kw: SimpleNamespace(politica_de={}))
    monkeypatch.setattr(ci, 'CamaraLeginConnector', lambda **kw: con)
    def resolve(*a):
        raise failure
    monkeypatch.setattr(con, 'resolve', resolve)
    monkeypatch.setattr(ci, '_persistir_unidade', lambda *a: None)
    from tests.test_camara_0081_atribuicao_inventario_snapshot import normas_em
    out = ci.inventariar(tmp_path / 'h', normas_em(tmp_path), tmp_path / 'duravel')
    inventory = json.loads((tmp_path / 'duravel/lei-6404-1976/inventario.json').read_text('utf-8'))
    assert inventory['falha']['causas'] == out['falhas']
    assert private not in json.dumps([inventory, out])
    with Verifica(home=tmp_path / 'svc') as svc:
        monkeypatch.setattr(svc, '_get', lambda *a: con)
        monkeypatch.setattr(svc, '_offline', lambda: False)
        monkeypatch.setattr(svc, '_camara_ativada', lambda: True)
        result = svc.obter_dispositivo('art. 1 da Lei 6404/1976')
        assert result['status'] == 'indisponivel'
        assert result['fontes_consultadas'][-1]['evidencia_indisponibilidade'] == failure.evidencia
        assert private not in json.dumps(result)


@pytest.mark.parametrize('facade', ['rest', 'mcp'])
@pytest.mark.parametrize('profile', ['camara_legin', 'camara_anexo'])
def test_n2_fachadas_evidencia_tipificada(tmp_path, monkeypatch, facade, profile):
    from tests.contrato import harness
    private = 'C:/dev/tmp/SYNTHETIC_PRIVATE child detail'
    failure = Unavailable('falha_parser_camara', None, {'fase': 'interpretacao', 'perfil': profile,
                          'causa': 'exit_nao_zero', 'exit_code': 4, 'url': ATUAL, 'sha256': 'a' * 64,
                          'stderr': private, 'mensagem': private})
    con = CamaraLeginConnector()
    def resolve(*args):
        raise failure
    monkeypatch.setattr(con, 'resolve', resolve)
    with Verifica(home=tmp_path / 'h') as svc:
        monkeypatch.setattr(svc, '_get', lambda *a: con)
        monkeypatch.setattr(svc, '_offline', lambda: False)
        monkeypatch.setattr(svc, '_camara_ativada', lambda: True)
        args = {'citacao': 'art. 1 da Lei 6404/1976'}
        if facade == 'mcp':
            from freoa_verifica import mcp_server as ms
            monkeypatch.setitem(ms._servicos, str(svc.home), svc)
            result = harness.chamar_mcp(ms.create_mcp(home=str(svc.home)), 'obter_dispositivo', args)
        else:
            from freoa_verifica import rest
            from fastapi.testclient import TestClient
            monkeypatch.setattr(rest, 'Verifica', lambda **kw: svc)
            with TestClient(rest.create_app(home=str(svc.home), token=None), client=('127.0.0.1', 50000), base_url='http://127.0.0.1') as client:
                result = harness.chamar_rest(client, 'obter_dispositivo', args)
        assert result['status'] == 'indisponivel'
        evidence = result['fontes_consultadas'][-1]['evidencia_indisponibilidade']
        assert evidence == {k: v for k, v in failure.evidencia.items() if k not in {'stderr', 'mensagem'}}
        assert private not in json.dumps(result)

@pytest.mark.parametrize('case,reason', CASES)
def test_n1_inventario_duravel_zero_gravacoes(tmp_path, monkeypatch, case, reason):
    con = defeituoso(case)
    writes = []
    monkeypatch.setattr(ci, '_escrever', lambda *a: writes.append('arquivo'))
    with pytest.raises(Unavailable) as error:
        ci._gravar_unidade(tmp_path / 'nao-gravado', con, SimpleNamespace(politica_de={}), NORMA, None)
    assert error.value.reason == reason
    assert writes == [] and not (tmp_path / 'nao-gravado').exists()


@pytest.mark.parametrize('case', [None] + [c for c, _ in CASES])
def test_n1_indexar_sem_descoberta_recusa_sem_fabricar_recibo(tmp_path, monkeypatch, case):
    # r3/N3: sem o conector da unidade, nem grafo válido nem defeituoso é reconstruído
    # a partir de recibo sintético; recusa antes de qualquer leitura ou gravação.
    con = grafo() if case is None else defeituoso(case)
    doc = documento(con)
    with Verifica(home=tmp_path / 'h') as svc:
        lidos = []
        monkeypatch.setattr(svc, '_resposta_camara', lambda *a, **kw: lidos.append(a))
        with pytest.raises(Unavailable) as error:
            svc.indexar_obra(source_id=con.id, work_key=KEY, document=doc,
                             body=con.paginas[ATUAL].body, url=ATUAL,
                             fetched_at='2099-01-01T00:00:00+00:00')
        assert error.value.reason == 'camara_indexacao_sem_descoberta'
        assert lidos == []
        assert svc.conn.execute('SELECT count(*) FROM capture').fetchone()[0] == 0
        assert not list((svc.home / 'blobs').rglob('*'))

def test_releitura_busca_intermediaria_ate_portal_recusada(tmp_path, monkeypatch):
    from freoa_verifica.connectors.camara_legin import PORTAL
    con = grafo()
    portal = pagina(PORTAL, (BUSCA, 'Busca'))
    con.paginas[PORTAL] = portal
    con.links[BUSCA] = (portal, BUSCA, 'Busca')
    doc = documento(con)
    block = next(b for b in doc.editorial_blocks if b.kind == 'camara_inventario')
    inv = json.loads(block.text)
    del inv['conjunto_descoberta']  # a contraprova da auditoria usa a representação anterior.
    inv['descoberta'].append({'url': BUSCA, 'origem_url': PORTAL, 'origem_sha256': portal.sha256,
                             'href': BUSCA, 'rotulo': 'Busca'})
    block.text = json.dumps(inv)
    with Verifica(home=tmp_path / 'h') as svc:
        monkeypatch.setattr(svc, '_resposta_camara', lambda url, digest, **kw: con.paginas[url])
        monkeypatch.setattr(svc, '_authenticate_capture', lambda _: None)
        with pytest.raises(SourceUnavailable) as error:
            svc._revalidar_camara(SimpleNamespace(document=doc, url=ATUAL, sha256=con.paginas[ATUAL].sha256, capture_id='texto'))
        assert error.value.reason == 'camara_releitura_sem_vinculo_validado'
        assert error.value.__cause__.reason == 'raiz_descoberta_invalida'


def test_releitura_hash_da_pagina_declarada_confere(tmp_path, monkeypatch):
    con = grafo()
    doc = documento(con)
    block = next(b for b in doc.editorial_blocks if b.kind == 'camara_inventario')
    inv = json.loads(block.text)
    inv['pagina']['sha256'] = '0' * 64
    block.text = json.dumps(inv)
    with Verifica(home=tmp_path / 'h') as svc:
        monkeypatch.setattr(svc, '_resposta_camara', lambda url, digest, **kw: con.paginas[url])
        monkeypatch.setattr(svc, '_authenticate_capture', lambda _: None)
        with pytest.raises(SourceUnavailable) as error:
            svc._revalidar_camara(SimpleNamespace(document=doc, url=ATUAL, sha256=con.paginas[ATUAL].sha256, capture_id='texto'))
        assert error.value.__cause__.reason == 'hash_ancestral_divergente'


def test_snapshot_camara_nao_exporta_sem_corpos(tmp_path, snapshot_valido, monkeypatch):
    from freoa_verifica import snapshot
    dest, _ = snapshot_valido
    with Verifica(home=tmp_path / 'novo') as svc:
        assert snapshot._install_from_dir(svc, dest)['status'] == 'ok'
        monkeypatch.setattr(snapshot, 'BLOB_SIZE_LIMIT', 1)
        out = svc.snapshot_export(tmp_path / 'sem-corpos')
        assert out == {'status': 'erro', 'motivo': 'camara_descoberta_invalida'}
        assert not (tmp_path / 'sem-corpos').exists()


def test_hash_invalido_recusado_antes_de_abrir_blob(tmp_path, monkeypatch):
    from freoa_verifica.connectors.camara_descoberta import resposta_capturada
    from pathlib import Path
    reads = []
    monkeypatch.setattr(Path, 'read_bytes', lambda *a: reads.append('leitura'))
    with pytest.raises(Unavailable) as error:
        resposta_capturada({'sha256': '../SYNTHETIC_PRIVATE'}, tmp_path, blob_dir=tmp_path)
    assert error.value.reason == 'hash_captura_divergente' and reads == []


def test_preflight_nao_reutiliza_aprovacao_entre_fronteiras(monkeypatch):
    from freoa_verifica.connectors import camara_legin
    con = grafo()
    checked = []
    original = camara_legin._revalidar
    def validar(resp, *a, **kw):
        checked.append(resp.url)
        return original(resp, *a, **kw)
    monkeypatch.setattr(camara_legin, '_revalidar', validar)
    con.validar_conjunto()
    assert set(checked) == set(con.paginas) and len(checked) == len(con.paginas)
    checked.clear()
    con.validar_conjunto()
    assert set(checked) == set(con.paginas) and len(checked) == len(con.paginas)
    # Troca os bytes após uma fronteira aprovada, conservando o hash declarado.
    con.paginas[ATUAL] = replace(con.paginas[ATUAL], body=b'adulterado')
    with pytest.raises(Unavailable) as error:
        con.validar_conjunto()
    assert error.value.reason == 'hash_captura_divergente'


def test_falha_local_legada_mantem_terminalidade_no_instrumento_e_portao(tmp_path):
    from tests._camara_util import portao
    from freoa_verifica.connectors.guarda import da_chamada
    private = 'C:/dev/tmp/SYNTHETIC_PRIVATE detalhe'
    cause = ci._causa(LocalParserFailure(private, None, {'causa': private}), 'persistencia_interpretacao')
    assert cause['motivo'] == 'falha_parser_camara'
    assert ci._interromper([cause])
    p, _, _, _ = portao(tmp_path)
    with da_chamada():
        safe = p.falha_local_de_interpretacao(Unavailable(private, None, {'causa': private, 'stderr': private}))
        with pytest.raises(Unavailable) as error:
            p.obter(LSA)
        assert error.value.reason == safe.reason == 'falha_parser_camara'
        assert error.value.evidencia == {'fase': 'interpretacao', 'causa': 'protocolo'}
    assert private not in json.dumps([cause, safe.evidencia])


@pytest.mark.parametrize('change,reason', [('body', 'hash_captura_divergente'),
                                         ('mime', 'transporte_RespostaInvalida'),
                                         ('origem', 'descoberta_sem_raiz')])
def test_lote_descoberta_reconfere_integridade_entre_arestas(change, reason):
    con = grafo()
    page = con.paginas[LSA]
    del con.links[B]
    del con.links[ATUAL]
    def resources():
        yield {'url': B, 'href': B, 'rotulo': 'B', 'admitido': True}
        if change == 'body':
            con.paginas[LSA] = replace(page, body=b'adulterado')
        elif change == 'mime':
            con.paginas[LSA] = replace(page, mime='application/pdf')
        else:
            del con.paginas[LSA]
        yield {'url': ATUAL, 'href': ATUAL, 'rotulo': 'Texto Atualizado', 'admitido': True}
    with pytest.raises(Unavailable) as error:
        con._descobrir(page, {'recursos': resources()})
    assert error.value.reason == reason
    assert B in con.links and ATUAL not in con.links
    assert con.falhas_descoberta[0] is error.value
    with pytest.raises(Unavailable) as retained:
        con.validar_conjunto()
    assert retained.value.reason == reason


@pytest.mark.parametrize('profile', ['camara_legin', 'camara_anexo'])
def test_n2_threads_de_io_nao_emitem_excecao_livre(monkeypatch, capsys, recwarn, profile):
    from freoa_verifica.parsers import isolated
    private = 'C:/dev/tmp/SYNTHETIC_PRIVATE pipe'
    class Pipe:
        def fileno(self):
            raise RuntimeError(private)
        def close(self):
            raise OSError(private)
    killed = []
    child = SimpleNamespace(stdin=Pipe(), stdout=Pipe(), stderr=Pipe(), returncode=0,
                            pid=-1, kill=lambda: killed.append(True), wait=lambda **kw: None)
    monkeypatch.setattr(isolated.subprocess, 'Popen', lambda *a, **kw: child)
    monkeypatch.setattr(isolated.os, 'killpg', lambda *a: killed.append(True), raising=False)
    with pytest.raises(LocalParserFailure) as error:
        isolated.parse_ou_indisponivel(profile, b'x', 1)
    assert killed and error.value.evidencia['causa'] == 'protocolo'
    assert private not in json.dumps(error.value.evidencia)
    assert private not in capsys.readouterr().err
    assert not any('SYNTHETIC_PRIVATE' in str(w.message) for w in recwarn)


def test_releitura_legada_nao_omite_captura_orfa(tmp_path):
    from tests.test_camara_legin import ORIGINAL
    con = grafo()
    del con.paginas[B]  # Unidade sintética com só as três capturas da cadeia.
    doc = documento(con)
    with Verifica(home=tmp_path / 'novo') as svc:
        rw = svc.indexar_obra(source_id='camara_legin', work_key=KEY, document=doc,
                             body=con.paginas[ATUAL].body, url=ATUAL, descoberta_camara=con)
        block = next(b for b in doc.editorial_blocks if b.kind == 'camara_inventario')
        inv = json.loads(block.text)
        del inv['conjunto_descoberta']
        block.text = json.dumps(inv)
        svc.conn.execute('UPDATE parsed_document SET model_json=? WHERE capture_id=?',
                         (json.dumps(asdict(doc)), rw.capture_id))
        svc.conn.commit()
        # Controle positivo antes da inclusão da órfã, sem alterar capturas.
        svc._revalidar_camara(rw)
        repo.save_capture(svc.conn, pagina(ORIGINAL), 'camara_legin', home=svc.home)
        with pytest.raises(SourceUnavailable) as error:
            svc._revalidar_camara(rw)
        assert error.value.reason == 'camara_releitura_sem_vinculo_validado'
        assert error.value.__cause__.reason == 'vinculo_descoberta_ausente'


@pytest.mark.parametrize('boundary', ['releitura', 'exportacao'])
def test_capturas_mesmo_url_hash_nao_mascaram_resposta_invalida(tmp_path, boundary):
    con = grafo()
    text = con.paginas[ATUAL]
    if boundary == 'exportacao':
        # A captura inválida vem antes da válida, para que o mapa URL/hash
        # selecione a válida ao final. Ambas as linhas devem ser conferidas.
        con.paginas[ATUAL] = replace(text, fetched_at='2026-11-08T12:00:02+00:00')
    with Verifica(home=tmp_path / 'h') as svc:
        svc.conn.execute('INSERT INTO source(id, authority, profile, hosts_json) VALUES (?,?,?,?)',
                         (con.id, con.authority, con.id, json.dumps(sorted(con.hosts))))
        bad = replace(text, status=403, fetched_at='2026-11-08T12:00:01+00:00')
        if boundary == 'exportacao':
            repo.save_capture(svc.conn, bad, con.id, home=svc.home)
        rw = svc.indexar_obra(source_id=con.id, work_key=KEY, document=documento(con),
                             body=text.body, url=ATUAL, descoberta_camara=con)
        svc._revalidar_camara(rw)  # Controle positivo: a captura específica é válida.
        if boundary == 'releitura':
            bad_id = repo.save_capture(svc.conn, bad, con.id, home=svc.home)
            with pytest.raises(SourceUnavailable) as error:
                svc._revalidar_camara(replace(rw, capture_id=bad_id))
            assert error.value.reason == 'camara_releitura_sem_vinculo_validado'
        else:
            out = svc.snapshot_export(tmp_path / 'recusado')
            assert out == {'status': 'erro', 'motivo': 'camara_descoberta_invalida'}
            assert not (tmp_path / 'recusado').exists()


def test_n2_candidato_nao_repassa_excecao_local_inesperada(tmp_path, monkeypatch):
    con = grafo()
    private = 'C:/dev/tmp/SYNTHETIC_PRIVATE unexpected'
    with Verifica(home=tmp_path / 'h') as svc:
        writes = []
        cand, _ = preparar_servico(svc, con, monkeypatch, writes)
        def parse(*a):
            raise RuntimeError(private)
        monkeypatch.setattr(con, 'parse', parse)
        out = svc._index_candidate_legis(con, cand)
        assert out['motivo'] == 'falha_local_camara'
        assert private not in json.dumps(out) and writes == []


@pytest.mark.parametrize('instante', ['', 'nao-data', None])
def test_n3_instante_invalido_recusado_antes_de_gravar(tmp_path, instante):
    # Passe final: com o conector presente, captura sem instante real não chega ao
    # materializador genérico, que fabricaria outro recibo com o relógio.
    con = grafo()
    con.paginas[ATUAL] = replace(con.paginas[ATUAL], fetched_at=instante)
    doc = documento(con)
    with Verifica(home=tmp_path / 'h') as svc:
        with pytest.raises(Unavailable) as error:
            svc.indexar_obra(source_id=con.id, work_key=KEY, document=doc,
                             body=con.paginas[ATUAL].body, url=ATUAL, descoberta_camara=con)
        assert error.value.reason == 'instante_captura_invalido'
        assert svc.conn.execute('SELECT count(*) FROM capture').fetchone()[0] == 0
        assert not list((svc.home / 'blobs').rglob('*'))
    with pytest.raises(Unavailable) as error:
        con.validar_conjunto()
    assert error.value.reason == 'instante_captura_invalido'


@pytest.mark.parametrize('instante', ['', 'nao-data'])
@pytest.mark.parametrize('ordem', ['por_ultimo', 'entre_validos'])
def test_conf_snapshot_recusa_recibo_sem_instante_encoberto(tmp_path, instante, ordem):
    # Conferência do passe final: recibo inválido da mesma URL/hash não fica
    # encoberto por outro válido na validação do acervo (exportação e instalação).
    from freoa_verifica.connectors.camara_descoberta import validar_acervo
    con = grafo()
    with Verifica(home=tmp_path / 'h') as svc:
        svc.indexar_obra(source_id=con.id, work_key=KEY, document=documento(con),
                         body=con.paginas[ATUAL].body, url=ATUAL, descoberta_camara=con)
        validar_acervo(svc.conn, svc.home)  # controle positivo
        repo.save_capture(svc.conn, replace(con.paginas[ATUAL], fetched_at=instante),
                          'camara_legin', home=svc.home)
        if ordem == 'entre_validos':
            repo.save_capture(svc.conn, replace(con.paginas[ATUAL], fetched_at='2026-11-09T00:00:00+00:00'),
                              'camara_legin', home=svc.home)
        svc.conn.commit()
        with pytest.raises(Unavailable) as error:
            validar_acervo(svc.conn, svc.home)
        assert error.value.reason == 'instante_captura_invalido'


@pytest.mark.parametrize('defeito', ['instante', 'status', 'mime'])
@pytest.mark.parametrize('alvo', ['busca', 'norma'])
def test_conf2_releitura_nao_encobre_recibo_ancestral_invalido(tmp_path, defeito, alvo):
    # Conferência 2: na releitura, recibo ancestral inválido da mesma URL/hash não
    # fica encoberto pela seleção de uma única linha válida.
    con = grafo()
    url = BUSCA if alvo == 'busca' else con.links[ATUAL][0].final_url
    outro = '2026-11-09T00:00:00+00:00'
    ruim = {'instante': {'fetched_at': 'nao-data'},
            'status': {'status': 403, 'fetched_at': outro},
            'mime': {'mime': 'application/pdf', 'content_type': 'application/pdf', 'fetched_at': outro}}[defeito]
    with Verifica(home=tmp_path / 'h') as svc:
        rw = svc.indexar_obra(source_id=con.id, work_key=KEY, document=documento(con),
                              body=con.paginas[ATUAL].body, url=ATUAL, descoberta_camara=con)
        svc._revalidar_camara(rw)  # controle positivo
        repo.save_capture(svc.conn, replace(con.paginas[url], **ruim), 'camara_legin', home=svc.home)
        svc.conn.commit()
        with pytest.raises(SourceUnavailable) as error:
            svc._revalidar_camara(rw)
        assert 'camara_releitura_sem_vinculo_validado' in str(error.value)


def test_conf3_conferencia_comum_exige_instante():
    # Conferência 3: o acumulador e o registro de arestas não substituem nem reduzem
    # resposta com instante inválido (a conferência comum o exige).
    con = grafo()
    for url, page in list(con.paginas.items()):
        with pytest.raises(Unavailable) as error:
            con._validar_response(replace(page, fetched_at='nao-data'), url)
        assert error.value.reason == 'instante_captura_invalido'
    origem, href, rotulo = con.links[ATUAL]
    antes = dict(con.links)
    with pytest.raises(Unavailable) as error:
        con._registrar_descoberta(replace(origem, fetched_at='nao-data'), ATUAL, href, rotulo)
    assert error.value.reason == 'instante_captura_invalido'
    assert con.links == antes


@pytest.mark.parametrize('coluna,valor', [('status', 403), ('mime', 'application/pdf')])
def test_conf3_mesclagem_do_snapshot_nao_encobre_recibo_divergente(tmp_path, coluna, valor):
    # Conferência 3: a instalação não descarta recibo recebido divergente da mesma
    # tripla (sha256, url, fetched_at) antes do preflight.
    import sqlite3
    from freoa_verifica import snapshot
    con = grafo()
    with Verifica(home=tmp_path / 'h') as svc:
        svc.indexar_obra(source_id=con.id, work_key=KEY, document=documento(con),
                         body=con.paginas[ATUAL].body, url=ATUAL, descoberta_camara=con)
        svc.conn.commit()
        bases = {}
        for nome in ('vivo', 'igual', 'divergente'):
            bases[nome] = tmp_path / f'{nome}.sqlite3'
            destino = sqlite3.connect(str(bases[nome]))
            svc.conn.backup(destino)
            destino.close()
    alterar = sqlite3.connect(str(bases['divergente']))
    for (gatilho,) in alterar.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='capture'"):
        alterar.execute(f'DROP TRIGGER "{gatilho}"')
    alterar.execute(f'UPDATE capture SET {coluna}=? WHERE url=?', (valor, ATUAL))
    alterar.commit()
    alterar.close()
    snapshot._merge_attach(bases['vivo'], bases['igual'])  # controle: mesma obtenção, mesmo recibo
    with pytest.raises(ValueError, match='conflito_recibo_captura'):
        snapshot._merge_attach(bases['vivo'], bases['divergente'])
