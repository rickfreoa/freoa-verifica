"""Regressões gerais de identidade, lacunas históricas e integridade de consultas."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.identity import declared_identity
from freoa_verifica.parsers.model import Annotation, ParsedDocument, Provision, Redaction
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.service import Verifica
from freoa_verifica.store import blobs
from freoa_verifica.temporal import select
from tests.test_r5 import populated, docx


@pytest.mark.parametrize('kind,label,authority', [
    ('resolucao','RESOLUÇÃO CVM','cvm'), ('instrucao','INSTRUÇÃO CVM','cvm'),
    ('parecer_orientacao','PARECER DE ORIENTAÇÃO CVM','cvm'),
    ('resolucao_bcb','RESOLUÇÃO BCB','bcb'), ('resolucao','RESOLUÇÃO CMN','cmn'),
])
def test_year_identity_and_repair(tmp_path, monkeypatch, kind, label, authority):
    monkeypatch.setenv('FV_OFFLINE','1')
    title=f'{label} Nº 9876, DE 13 DE JULHO DE 2022'
    doc=ParsedDocument('test','1',title,None,'Regra.', provisions=[
        Provision('art1','Art. 1','',redactions=[Redaction('Regra.',False,0)])])
    key=WorkKey(authority,kind,'9876',0)
    with Verifica(tmp_path/'home') as s:
        rw=s.indexar_obra(source_id='cvm_normas' if authority=='cvm' else 'bcb',work_key=key,
                         document=doc,body=title.encode(),url='https://example.org/ato')
        assert rw.work_key.year==2022
        assert s._resolve(WorkKey(authority,kind,'9876',2022)).work_id==rw.work_id
        assert s._resolve(WorkKey(authority,kind,'9876',2023)) is None
        before=[tuple(r) for r in s.conn.execute('SELECT * FROM capture')]
        with s.conn:
            s.conn.execute('UPDATE work SET year=0 WHERE id=?',(rw.work_id,))
        s._clear_caches()
        assert s._resolve(WorkKey(authority,kind,'9876',2022)).work_key.year==2022
        assert s.reparar_anos()=={'reparados':[],'pendentes':[]}
        assert before==[tuple(r) for r in s.conn.execute('SELECT * FROM capture')]


@pytest.mark.parametrize('number,year',[('044',2021),('080',2022),('160',2022),('175',2022)])
def test_cvm_consolidated_year(number, year):
    raw=(Path(__file__).parent/'fixtures'/f'cvm_resol_{number}_consolid_docx.docx').read_bytes()
    assert declared_identity(parse_cvm_docx(raw))[0].year==year


def test_cvm_act_page_year():
    from freoa_verifica.connectors.cvm_normas import _parse_ato_html
    raw=(Path(__file__).parent/'fixtures/cvm_resol_080_page.html').read_bytes()
    d=_parse_ato_html(raw,base_url='https://conteudo.cvm.gov.br/')
    assert declared_identity(d)[0]==WorkKey('cvm','resolucao','80',2022)


@pytest.mark.parametrize('header,year',[
    ('INSTRUÇÃO CVM N o 480, DE 7 DEZEMBRO DE 200 9 COM AS ALTERAÇÕES INTRODUZIDAS PELA INSTRUÇÃO CVM 488/10',2009),
    ('RESOLUÇÃO CVM Nº 172, DE 1º DE NOVEMBRO DE 2022',2022),
    ('Resolução CVM no 166, de 1o de SETEMBRO de 2022',2022),
])
def test_epigraph_typography(header,year):
    d=ParsedDocument('cvm_pdf','1','',None,header+'\nArt. 1º Regra.')
    assert declared_identity(d)[0].year==year


def test_bcb_metadata_year():
    from freoa_verifica.parsers.bcb_json import parse_bcb_json
    raw=(Path(__file__).parent/'fixtures/bcb_res_cmn_4966.json').read_bytes()
    assert declared_identity(parse_bcb_json(raw))[0].year==2021


def test_empty_history_is_unknown():
    result=select(Provision('art1','Art. 1',''), '2001-01-01')
    assert result.status=='unknown'
    assert result.reason=='HISTORICO_ANTERIOR_AUSENTE'


@pytest.mark.parametrize('method,source',[('buscar_normas_cvm','cvm_normas'),('buscar_normas_bcb','bcb')])
@pytest.mark.parametrize('attack',['missing','corrupt'])
def test_specialized_searches_authenticate(populated,monkeypatch,method,source,attack):
    from freoa_verifica.connectors.base import Candidate
    s,rw=populated
    class Connector:
        def search(self,*args,**kwargs):
            return [Candidate(source,'1','Ato',url='https://example.org/ato',snippet='Regra principal.')]
    monkeypatch.setattr(s,'_get',lambda source: Connector())
    monkeypatch.setattr(s,'_index_candidate_legis',lambda *args: {'trecho':'Regra principal.','capture_id':rw.capture_id})
    monkeypatch.setenv('FV_OFFLINE','0')
    assert getattr(s,method)('regra')['status']=='ok'
    path=blobs.blob_path(rw.sha256,s.home)
    if attack=='missing': path.unlink()
    else: path.write_bytes(b'bad')
    expected='EVIDENCIA_AUSENTE' if attack=='missing' else 'EVIDENCIA_CORROMPIDA'
    assert getattr(s,method)('regra')['reason_code']==expected


def test_all_works_have_year_or_reason(populated, tmp_path):
    s,rw=populated
    with s.conn:
        s.conn.execute('UPDATE work SET year=0 WHERE id=?',(rw.work_id,))
        s.conn.execute("INSERT INTO work(id,jurisdiction,authority,kind,number,year) VALUES ('unresolved','BR','cvm','resolucao','987654',0)")
    first=s.reparar_anos()
    assert len(first['reparados'])==1 and len(first['pendentes'])==1
    assert s.reparar_anos()['pendentes']==first['pendentes']
    assert not s.conn.execute('SELECT w.id FROM work w LEFT JOIN work_year_issue i ON i.work_id=w.id WHERE w.year<=0 AND (i.reason IS NULL OR i.reason="")').fetchall()
    export=tmp_path/'snapshot'
    assert s.snapshot_export(export)['status']=='ok'
    with Verifica(tmp_path/'installed') as target:
        installed=target.snapshot_install(export)
        assert installed['status']=='ok', installed
        assert target.conn.execute('SELECT reason FROM work_year_issue').fetchone()[0]=='ANO_NAO_DECLARADO'


@pytest.mark.parametrize('annotation,expected', [('redacao_dada','unknown'),('incluido','nao_existia'),(None,'unknown')])
def test_before_first_available_redaction(annotation,expected):
    anns=[Annotation(annotation,'nota',act_date='2010-01-01')] if annotation else []
    p=Provision('art7','Art. 7','',redactions=[Redaction('Texto.',False,0,annotations=anns)])
    r=select(p,'2009-01-01',work_date='1990-01-01' if annotation else None)
    assert r.status==expected
    if expected=='unknown':
        assert r.reason=='HISTORICO_ANTERIOR_AUSENTE'
    assert select(p,'1980-01-01',work_date='1990-01-01').status=='nao_existia'


@pytest.mark.parametrize('attack',['missing','corrupt'])
def test_auxiliary_facades_authenticate(populated, attack, monkeypatch):
    from fastapi.testclient import TestClient
    from freoa_verifica.rest import create_app
    from freoa_verifica.mcp_server import create_mcp
    from mcp import Client
    from tests.test_mcp import _tool_payload
    s,rw=populated
    q='art. 87 da Lei 8765/1999'
    assert s.obter_dispositivo(citacao=q)['status']=='encontrada'
    p=blobs.blob_path(rw.sha256,s.home)
    if attack=='missing': p.unlink()
    else: p.write_bytes(b'corrupt')
    expected='EVIDENCIA_AUSENTE' if attack=='missing' else 'EVIDENCIA_CORROMPIDA'
    calls=[('obter_dispositivo',{'citacao':q}),('resolver_citacao',{'citacao':q}),
           ('historico_dispositivo',{'citacao':q}),('obter_evidencia',{'capture_id':rw.capture_id}),
           ('buscar_legislacao',{'q':'principal'})]
    with Verifica(s.home) as fresh:
        for svc in [s,fresh]:
            for name,params in calls:
                result=getattr(svc,name)(**params)
                assert result=={'status':'unavailable','motivo':expected,'reason_code':expected}
        monkeypatch.setenv('FV_HOME',str(s.home))
        for cmd,args in [('lei',[q]),('resolve',[q]),('historico',[q]),
                         ('evidencia',[rw.capture_id]),('busca',['principal'])]:
            cli=subprocess.run([sys.executable,'-m','freoa_verifica.cli',cmd,*args,'--json'],
                               capture_output=True,text=True)
            assert cli.returncode==0, cli.stderr
            assert json.loads(cli.stdout)['reason_code']==expected
        with TestClient(create_app(home=str(s.home),token='test-token')) as client:
            for route,params in [('/v1/dispositivos',{'citacao':q}),('/v1/citacoes/resolver',{'citacao':q}),
                                 ('/v1/dispositivos/historico',{'citacao':q}),
                                 (f'/v1/evidencias/{rw.capture_id}',{}),('/v1/legislacao',{'q':'principal'})]:
                result=client.get(route,params=params,headers={'Authorization':'Bearer test-token'})
                assert result.status_code==200
                assert result.json()['reason_code']==expected
        server=create_mcp(home=str(s.home))
        from freoa_verifica import mcp_server
        monkeypatch.setattr(mcp_server,'_svc',s)
        async def run():
            async with Client(server) as client:
                for name,params in calls:
                    assert _tool_payload(await client.call_tool(name,params))['reason_code']==expected
        asyncio.run(run())


@pytest.mark.parametrize('attack',['missing','corrupt'])
def test_decision_queries_authenticate(populated,attack,monkeypatch):
    from freoa_verifica.store import repo
    from freoa_verifica.ids import new_ulid
    from fastapi.testclient import TestClient
    from freoa_verifica.rest import create_app
    from freoa_verifica.mcp_server import create_mcp
    from freoa_verifica import mcp_server
    from mcp import Client
    from tests.test_mcp import _tool_payload
    s,rw=populated
    did=repo.upsert_decision(s.conn,court='STJ',kind='acordao',official_id='987654',class_='REsp')
    with s.conn:
        s.conn.execute('INSERT INTO decision_document(id,decision_id,capture_id,kind,text,sha256) VALUES (?,?,?,?,?,?)',
                       (new_ulid(),did,rw.capture_id,'ementa','Regra principal.',rw.sha256))
    repo.index_decision(s.conn,ementa='Regra principal.',inteiro_teor='',court='STJ',class_='REsp',official_id='987654')
    assert s.obter_decisao(did)['status']=='encontrada'
    assert s.pesquisar_jurisprudencia('principal')['itens']
    path=blobs.blob_path(rw.sha256,s.home)
    if attack=='missing': path.unlink()
    else: path.write_bytes(b'bad')
    expected='EVIDENCIA_AUSENTE' if attack=='missing' else 'EVIDENCIA_CORROMPIDA'
    calls=[('obter_decisao',{'id':did}),('pesquisar_jurisprudencia',{'q':'principal'})]
    with Verifica(s.home) as fresh:
        for svc in [s,fresh]:
            for name,params in calls:
                assert getattr(svc,name)(**params)['reason_code']==expected
    with TestClient(create_app(home=str(s.home),token='test-token')) as client:
        for route,params in [(f'/v1/decisoes/{did}',{}),('/v1/jurisprudencia',{'q':'principal'})]:
            assert client.get(route,params=params,headers={'Authorization':'Bearer test-token'}).json()['reason_code']==expected
    server=create_mcp(home=str(s.home))
    monkeypatch.setattr(mcp_server,'_svc',s)
    async def run():
        async with Client(server) as client:
            for name,params in calls:
                assert _tool_payload(await client.call_tool(name,params))['reason_code']==expected
    asyncio.run(run())
    monkeypatch.setenv('FV_HOME',str(s.home))
    for cmd,args in [('decisao',[did]),('juris',['principal'])]:
        cli=subprocess.run([sys.executable,'-m','freoa_verifica.cli',cmd,*args,'--json'],capture_output=True,text=True)
        assert cli.returncode==0,cli.stderr
        assert json.loads(cli.stdout)['reason_code']==expected


def test_export_single_archive_cli(populated,tmp_path,monkeypatch):
    s,_=populated
    monkeypatch.setenv('FV_HOME',str(s.home))
    archive=tmp_path/'freoa-verifica-snapshot-20261018.tar.gz'
    result=subprocess.run([sys.executable,'-m','freoa_verifica.cli','snapshot','export',
                           '--arquivo-unico','--saida',str(archive),'--json'],capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    assert json.loads(result.stdout)['status']=='ok'
    assert Path(str(archive)+'.sha256').is_file()
    with Verifica(tmp_path/'clean') as target:
        assert target.snapshot_install(archive)['status']=='ok'
        assert target.verificar_citacao('art. 87 da Lei 8765/1999',trecho='Regra principal.')['text']['status']=='verified'


def test_install_latest_snapshot_without_arguments(populated,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from freoa_verifica.connectors import httputil
    s,_=populated
    archive=tmp_path/'freoa-verifica-snapshot-build-1.tar.gz'
    assert s.snapshot_export(archive)['status']=='ok'
    url='https://github.com/rickfreoa/freoa-verifica/releases/download/v1/'+archive.name
    calls=[]
    def fetch(request,**kwargs):
        calls.append(request)
        if request.endswith('/latest'):
            return SimpleNamespace(body=json.dumps({'assets':[
                {'name':'freoa_verifica-1.0.0.tar.gz','browser_download_url':url+'-sdist'},
                {'name':archive.name,'browser_download_url':url}]}).encode())
        if request.endswith('.sha256'):
            return SimpleNamespace(body=Path(str(archive)+'.sha256').read_bytes())
        assert request==url
        return SimpleNamespace(body=archive.read_bytes())
    monkeypatch.setattr(httputil,'connector_fetch',fetch)
    with Verifica(tmp_path/'latest') as target:
        assert target.snapshot_install()['status']=='ok'
        assert target.verificar_citacao('art. 87 da Lei 8765/1999')['identity']['status']=='verified'
    assert calls==['https://api.github.com/repos/rickfreoa/freoa-verifica/releases/latest',url,url+'.sha256']
