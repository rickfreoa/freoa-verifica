"""Regressões sintéticas de evidência, escopo e distribuição."""
from pathlib import Path
import hashlib
import io
import json
import tarfile
import zipfile

import pytest
from freoa_verifica.service import Verifica
from freoa_verifica.aliases import WorkKey
from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.snapshot import _verify_sums, _extract_archive, pack_snapshot
from freoa_verifica.store import blobs


def docx(*paragraphs):
    from xml.sax.saxutils import escape
    stream = io.BytesIO()
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    paragraphs = (paragraphs[0], 'Art. 1. Abertura.', *paragraphs[1:]) if paragraphs and paragraphs[0].startswith('Resolução') else ('Art. 1. Abertura.', *paragraphs)
    xml += ''.join('<w:p><w:r><w:t>'+escape(t)+'</w:t></w:r></w:p>' for t in paragraphs)
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('word/document.xml', xml+'</w:body></w:document>')
    return stream.getvalue()


@pytest.mark.parametrize('target,path', [
    ('Caput','art87'), ('Caput do art. 87','art87'),
    ('Parágrafo único','art87.parunico'), ('Inciso II','art87.parunico.inc2'),
    ('Alínea c','art87.parunico.inc2.ali-c'), ('Item 3','art87.parunico.inc2.ali-c.item3'),
])
def test_editorial_separated(target,path):
    note=target+' com redação dada pela Resolução CVM nº 912, de 7 de maio de 2020.'
    d=parse_cvm_docx(docx('Art. 87. Regra principal.', 'Parágrafo único. Regra particular.',
                        'II – Condição segunda.', 'c) Condição da alínea.', '3. Condição do item.', note))
    assert not any(note in r.text for p in d.provisions for r in p.redactions)
    assert d.provision(path).redactions[-1].annotations[-1].kind=='redacao_dada'


@pytest.mark.parametrize('target',['Anexo II','Incisos II e III','Itens 3.b e 3.c','Subseção IV','Suplemento G'])
def test_uncertain_editorial_blocks(target):
    note=target+' incluído pela Resolução CVM nº 912, de 7 de maio de 2020.'
    d=parse_cvm_docx(docx('Art. 87. Regra principal.', note))
    assert any(i.blocking_scope for i in d.issues)
    assert note not in d.provision('art87').redactions[-1].text


@pytest.fixture
def populated(tmp_path,monkeypatch):
    monkeypatch.setenv('FV_OFFLINE','1')
    with Verifica(tmp_path/'home') as s:
        d=ParsedDocument('test','1','Lei 8765/1999',None,'Regra principal.',provisions=[
            Provision('art87','Art. 87','',redactions=[Redaction('Regra principal.',False,0)])])
        rw=s.indexar_obra(source_id='planalto',work_key=WorkKey('federal','lei','8765',1999),
                         document=d,body=b'captured receipt',url='https://www.planalto.gov.br/test')
        yield s,rw


@pytest.mark.parametrize('attack',['missing','corrupt'])
def test_evidence_after_cache(populated,attack):
    s,rw=populated
    query='art. 87 da Lei 8765/1999'
    assert s.verificar_citacao(query,trecho='Regra principal.')['text']['status']=='verified'
    p=blobs.blob_path(rw.sha256,s.home)
    if attack=='missing': p.unlink()
    else: p.write_bytes(b'corrupted receipt')
    expected='EVIDENCIA_AUSENTE' if attack=='missing' else 'EVIDENCIA_CORROMPIDA'
    with Verifica(s.home) as fresh:
        for service in [s,fresh]:
            r=service.verificar_citacao(query,trecho='Regra principal.')
            assert r['identity']['status']=='unavailable'
            assert r['identity']['reason_code']==expected
            assert service.verificar_texto(query+': "Regra principal."')['citacoes'][0]['status']=='indisponivel'


@pytest.mark.parametrize('n',['999999','987654321'])
def test_missing_device(populated,n):
    s,_=populated
    raw=f'art. {n} da Lei 8765/1999'
    r=s.verificar_citacao(raw)
    assert r['identity']['status']=='not_found'
    assert r['identity']['reason_code']=='DISPOSITIVO_INEXISTENTE'
    assert r['citation']['raw']==raw
    assert s.verificar_texto(raw)['citacoes'][0]['status']=='inexistente'
    resolution=s.resolver_citacao(raw)
    assert resolution['status']=='inexistente'
    assert resolution['identity']['reason_code']=='DISPOSITIVO_INEXISTENTE'


@pytest.mark.parametrize('separator',[':', '—','–',',','que dispõe','segundo o qual','in verbis'])
@pytest.mark.parametrize('quotes',[('"','"'),('“','”'),("'","'"),('‘','’')])
def test_quotes(populated,separator,quotes):
    s,_=populated
    row=s.verificar_texto(f'art. 87 da Lei 8765/1999 {separator} {quotes[0]}Regra principal.{quotes[1]}')['citacoes'][0]
    assert row['trecho_conferido']=='Regra principal.'
    assert row['identity']['status']=='verified'
    assert row['text']['status']=='verified'


@pytest.mark.parametrize("quotes", [("“", "”"), ("\"", "\""), ("'", "'")])
def test_unassociated_quotes(populated, quotes):
    s,_=populated
    row=s.verificar_texto(f'Lei 8765/1999. Considerações distantes: {quotes[0]}Outra frase.{quotes[1]}')['citacoes'][0]
    assert row['aspas_nao_associadas']
    assert row['text']['status']!='verified'


@pytest.mark.parametrize('selector',['../outside/db','/absolute/db',chr(67)+':/db','missing.db'])
def test_snapshot_selector(tmp_path,selector):
    (tmp_path/'listed.txt').write_bytes(b'listed')
    m={'arquivos_sha256':{'listed.txt':hashlib.sha256(b'listed').hexdigest()},'db_arquivo':selector}
    raw=json.dumps(m).encode(); (tmp_path/'MANIFEST.json').write_bytes(raw)
    sums={**m['arquivos_sha256'],'MANIFEST.json':hashlib.sha256(raw).hexdigest()}
    (tmp_path/'SHA256SUMS').write_text(''.join(f'{v}  {k}\n' for k,v in sums.items()))
    assert _verify_sums(tmp_path,m) is not None


@pytest.mark.parametrize('name,kind',[('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('hard',tarfile.LNKTYPE)])
def test_archive_unsafe(tmp_path,name,kind):
    archive=tmp_path/'a.tar.gz'; dest=tmp_path/'dest'; dest.mkdir()
    with tarfile.open(archive,'w:gz') as t:
        entry=tarfile.TarInfo(name); entry.type=kind; entry.linkname='../outside'; t.addfile(entry)
    with pytest.raises(ValueError): _extract_archive(archive,dest)


def test_archive_roundtrip(populated,tmp_path):
    s,_=populated
    directory=tmp_path/'export'; assert s.snapshot_export(directory)['status']=='ok'
    archive=tmp_path/'snapshot.tar.gz'; pack_snapshot(directory,archive)
    with Verifica(tmp_path/'installed') as target:
        assert target.snapshot_install(archive, aceitar_nao_vinculado=True)['status']=='ok'
        assert target.verificar_citacao('art. 87 da Lei 8765/1999',trecho='Regra principal.')['text']['status']=='verified'


def test_punctuation_strike():
    from freoa_verifica.parsers.planalto import parse_planalto
    d=parse_planalto(b'<html><body><p>Art. 87. Regra.</p><p>III <s>-</s> Texto completo do inciso.</p></body></html>')
    p=d.provision('art87.inc3')
    assert len(p.redactions)==1
    assert not p.redactions[0].struck
    assert 'Texto completo' in p.redactions[0].text


@pytest.mark.parametrize('attack',['missing','corrupt'])
def test_facades_reject_invalid_evidence(populated,attack,monkeypatch):
    import asyncio
    import subprocess
    import sys
    from fastapi.testclient import TestClient
    from freoa_verifica.rest import create_app
    from freoa_verifica.mcp_server import create_mcp
    from freoa_verifica import mcp_server as ms
    from mcp import Client
    from tests.test_mcp import _tool_payload
    s,rw=populated
    monkeypatch.setenv('FV_HOME',str(s.home))
    query='art. 87 da Lei 8765/1999'
    path=blobs.blob_path(rw.sha256,s.home)
    if attack=='missing': path.unlink()
    else: path.write_bytes(b'bad')
    expected='EVIDENCIA_AUSENTE' if attack=='missing' else 'EVIDENCIA_CORROMPIDA'
    cli=subprocess.run([sys.executable,'-m','freoa_verifica.cli','verifica','--json',query,'--trecho','Regra principal.'],capture_output=True,text=True,check=True)
    assert json.loads(cli.stdout)['identity']['reason_code']==expected
    with TestClient(create_app(home=str(s.home),token='test-token')) as client:
        response=client.post('/v1/verificacoes',json={'citacao':query,'trecho':'Regra principal.'},headers={'Authorization':'Bearer test-token'})
        assert response.status_code==200
        assert response.json()['identity']['reason_code']==expected
    server=create_mcp(home=str(s.home))
    monkeypatch.setitem(ms._servicos, str(s.home), s)
    async def run():
        async with Client(server) as client:
            result=await client.call_tool('verificar_citacao',{'citacao':query,'trecho':'Regra principal.'})
            assert _tool_payload(result)['identity']['reason_code']==expected
    asyncio.run(run())


def test_latest_download_authenticates_checksum(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from freoa_verifica import snapshot
    from freoa_verifica.connectors import httputil
    payload=io.BytesIO()
    with tarfile.open(fileobj=payload,mode='w:gz') as tar:
        entry=tarfile.TarInfo('MANIFEST.json'); entry.size=2; tar.addfile(entry,io.BytesIO(b'{}'))
    body=payload.getvalue()
    name='freoa-verifica-snapshot-20261018.tar.gz'
    calls=[]
    def fetch(url,**kwargs):
        calls.append(url)
        if url.endswith('/latest'):
            data=json.dumps({'assets':[{'name':name,'browser_download_url':'https://github.com/rickfreoa/freoa-verifica/releases/download/v1/'+name}]}).encode()
        elif url.endswith('.sha256'): data=(hashlib.sha256(body).hexdigest()+'  '+name).encode()
        else: data=body
        if kwargs.get("sink") is not None:
            Path(kwargs["sink"]).write_bytes(data)
        return SimpleNamespace(body=b"" if kwargs.get("sink") else data, sha256=hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(snapshot, "_snapshots_oficiais", lambda: [{"arquivo": name, "sha256": hashlib.sha256(body).hexdigest(), "derived_version": 3}])
    monkeypatch.setattr(httputil,'connector_fetch',fetch)
    monkeypatch.setattr(snapshot,'_new_staging',lambda **kw: tmp_path/'staging')
    (tmp_path/'staging').mkdir()
    assert (snapshot._download_latest_release()/'MANIFEST.json').is_file()
    assert any(url.endswith('.sha256') for url in calls)
    def bad(url,**kwargs):
        if kwargs.get("sink") is not None:
            Path(kwargs["sink"]).write_bytes(body)
        return SimpleNamespace(body=b'0'*64 if url.endswith('.sha256') else b'', sha256=hashlib.sha256(body).hexdigest())
    monkeypatch.setattr(httputil,'connector_fetch',bad)
    with pytest.raises(ValueError,match='asset_integridade'):
        snapshot._download_release('https://github.com/rickfreoa/freoa-verifica/releases/download/v1/'+name)


def test_archive_total_limit(tmp_path,monkeypatch):
    from freoa_verifica import snapshot
    archive=tmp_path/'big.tar.gz'; dest=tmp_path/'dest'; dest.mkdir()
    with tarfile.open(archive,'w:gz') as tar:
        entry=tarfile.TarInfo('large'); entry.size=3; tar.addfile(entry,io.BytesIO(b'123'))
    monkeypatch.setattr(snapshot,'ARCHIVE_SIZE_LIMIT',2)
    with pytest.raises(ValueError,match='tamanho_excedido'): _extract_archive(archive,dest)


def test_previous_words_preserved():
    from freoa_verifica.parsers.planalto import parse_planalto
    d=parse_planalto(b'<html><body><p>Art. 87. Regra.</p><p><s>III - Texto anterior completo.</s></p><p>III - Texto atual completo.</p></body></html>')
    assert d.provision('art87.inc3').redactions[0].text=='Texto anterior completo.'


def test_explicit_invalid_device(populated):
    s,_=populated
    result=s.verificar_citacao('artigo banana da Lei 8765/1999')
    assert result['identity']['status']=='not_found'
    assert result['identity']['reason_code']=='formato_invalido'
    assert 'banana' in result['citation']['raw']
    assert s.resolver_citacao('artigo banana da Lei 8765/1999')['status']=='formato_invalido'


def test_editorial_events_and_uncertain_descendants(tmp_path,monkeypatch):
    monkeypatch.setenv('FV_OFFLINE','1')
    raw=docx('Resolução CVM nº 911, de 7 de maio de 2019','Art. 87. Regra principal.',
             'Caput com redação dada pela Resolução CVM nº 912, de 7 de maio de 2020.')
    with Verifica(tmp_path/'home') as s:
        s.indexar_obra(source_id='cvm_normas',work_key=WorkKey('cvm','resolucao','911',2019),
                     document=parse_cvm_docx(raw),body=raw,url='https://conteudo.cvm.gov.br/test.docx')
        assert s.historico_dispositivo('art. 87 da Resolução CVM 911/2019')['eventos']
        result=s.verificar_citacao('art. 87 da Resolução CVM 911/2019',trecho='Caput com redação dada pela Resolução CVM nº 912, de 7 de maio de 2020.')
        assert result['text']['status']!='verified'
    for target in ['Item 1.11','Alínea b.2.10','Inciso II e III','§ 2º-A']:
        note=target+' incluído pela Resolução CVM nº 912, de 7 de maio de 2020.'
        d=parse_cvm_docx(docx('Art. 87. Regra.', 'II – Outra regra.', note))
        assert any(i.code=='ORPHAN_ANNOTATION' and i.blocking_scope for i in d.issues)


def test_scope_note_does_not_cross_subsections():
    raw=docx('Art. 87. Regra.', 'Subseção II', 'Art. 88. Segunda regra.',
             'Subseção III', 'Art. 89. Terceira regra.',
             'Subseção II incluída pela Resolução CVM nº 912, de 7 de maio de 2020.')
    d=parse_cvm_docx(raw)
    assert d.provision('art88').redactions[-1].annotations
    assert not d.provision('art89').redactions[-1].annotations


@pytest.mark.parametrize('year,number',[(2009,718),(2018,977),(2025,1489)])
def test_mp_url_variants(year,number):
    from freoa_verifica.connectors.planalto import urls_for_work
    urls=urls_for_work('MPV',number,year)
    assert any(u.endswith(f'/Mpv/{number}.htm') for u in urls)
    assert any(u.endswith(f'/Mpv/mpv{number}.htm') for u in urls)


def test_snapshot_download_failure_is_explicit(populated,monkeypatch):
    from freoa_verifica import snapshot
    from freoa_verifica.connectors.base import Unavailable
    s,_=populated
    def unavailable(**kwargs): raise Unavailable('http_503')
    monkeypatch.setattr(snapshot,'_download_latest_release',unavailable)
    assert s.snapshot_install()=={'status':'erro','motivo':'http_503'}


@pytest.mark.parametrize('mutation',['traversal','no_hash','unlisted'])
def test_snapshot_db_selection_rejected_before_import(tmp_path,mutation):
    from freoa_verifica.snapshot import install_snapshot
    package=tmp_path/'package'; package.mkdir()
    external=tmp_path/'outside'; external.mkdir()
    with Verifica(external) as source:
        source.conn.execute("INSERT INTO work(id,jurisdiction,authority,kind,number,year,label) VALUES ('external-marker','br','federal','lei','765432',1998,'external')")
        source.conn.commit()
    import shutil
    shutil.copy2(external/'verifica.sqlite3',package/'db')
    data=(package/'db').read_bytes(); digest=hashlib.sha256(data).hexdigest()
    m={'db_arquivo':'db','db_sha256':digest,'arquivos_sha256':{'db':digest}}
    if mutation=='traversal': m['db_arquivo']='../outside/verifica.sqlite3'; m.pop('db_sha256')
    elif mutation=='no_hash': m.pop('db_sha256')
    else: m['arquivos_sha256']={'listed.txt':hashlib.sha256(b'listed').hexdigest()}; (package/'listed.txt').write_bytes(b'listed')
    raw=json.dumps(m).encode(); (package/'MANIFEST.json').write_bytes(raw)
    sums={**m['arquivos_sha256'],'MANIFEST.json':hashlib.sha256(raw).hexdigest()}
    (package/'SHA256SUMS').write_text(''.join(f'{v}  {k}\n' for k,v in sums.items()))
    with Verifica(tmp_path/'target') as target:
        assert install_snapshot(target,package, aceitar_nao_vinculado=True)['status']=='erro'
        assert not target.conn.execute("SELECT 1 FROM work WHERE id='external-marker'").fetchone()


@pytest.mark.parametrize('target',['Subitem iii','Subitem 1.3.7','Subitens 1.2 e 1.3','Preâmbulo','Participante','III-A','Parágrafos 8, 9 e 10','\uf0a7 Subitem 2.4'])
def test_additional_editorial_forms_are_not_comparable(target):
    note=target+' com redação dada pela Resolução CVM nº 912, de 7 de maio de 2020.'
    d=parse_cvm_docx(docx('Art. 87. Regra principal.',note))
    assert note not in d.provision('art87').redactions[-1].text
    assert d.provision('art87').ambiguous
