"""Casos sintéticos independentes de conjuntos de medição."""
import pytest
from freoa_verifica.citation import parse_one
from freoa_verifica.aliases import WorkKey
from freoa_verifica.identity import IdentityMismatch, validate_identity
from freoa_verifica.parsers.model import ParsedDocument

# 56 combinações novas, variando ordem, ordinais e hierarquia.
DEVICES = [
 ('artigo 87', 'art87'),
 ('art. 87, caput','art87.caput'),
 ('caput do artigo 87','art87.caput'),
 ('art. 87, parágrafo único','art87.parunico'),
 ('parágrafo único do art. 87','art87.parunico'),
 ('art. 87, § 3º','art87.par3'),
 ('art. 87, § 3o','art87.par3'),
 ('art. 87, § 3°','art87.par3'),
 ('§ 3º do art. 87','art87.par3'),
 ('art. 87, inciso XIV','art87.inc14'),
 ('inciso XIV do art. 87','art87.inc14'),
 ('art. 87, XIV','art87.inc14'),
 ('art. 87, § 3º, inciso XIV','art87.par3.inc14'),
 ('inciso XIV do § 3º do art. 87','art87.par3.inc14'),
 ('art. 87, § 3º, alínea c','art87.par3.ali-c'),
 ('alínea c do § 3º do art. 87','art87.par3.ali-c'),
 ('§ 3º, c, do art. 87','art87.par3.ali-c'),
 ('art. 87, § 3º, "c"','art87.par3.ali-c'),
 ("art. 87, § 3º, 'c'",'art87.par3.ali-c'),
 ('art. 87, § 3º, (c)','art87.par3.ali-c'),
 ('art. 87, § 3º, alínea “c”','art87.par3.ali-c'),
 ('art. 87, § 3º, XIV, alínea c, item 4','art87.par3.inc14.ali-c.item4'),
 ('item 4 da alínea c do inciso XIV do § 3º do art. 87','art87.par3.inc14.ali-c.item4'),
 ('art. 87-A, § 3º','art87-A.par3'),
 ('art. 87, inciso XIV, alínea c','art87.inc14.ali-c'),
 ('alínea (c) do inciso XIV do art. 87','art87.inc14.ali-c'),
 ('art. 87, § 3º, XIV, “c”','art87.par3.inc14.ali-c'),
 ('art. 87, § 3º, XIV, item 4','art87.par3.inc14.item4'),
]
@pytest.mark.parametrize('device,path',DEVICES)
@pytest.mark.parametrize('order',['before','after'])
def test_grammar_general(device,path,order):
    text = f'Nos termos de {device}, da Lei 8.765/1999' if order=='before' else f'Lei 8.765/1999, {device}'
    cite = parse_one(text)
    # A gramática posterior só admite rótulos separados por vírgula ou "e".
    posterior_noncanonical = order == 'after' and (' do ' in device or ' da ' in device or '(' in device)
    assert cite and cite.path == (None if posterior_noncanonical else path)
    assert cite.work == WorkKey('federal','lei','8765',1999)

@pytest.mark.parametrize('field,value',[('year',2004),('number','8766'),('kind','decreto')])
def test_identity_general(field,value):
    args=dict(authority='federal',kind='lei',number='8765',year=1999)
    args[field]=value
    d=ParsedDocument('test','1','LEI Nº 8.765, DE 7 DE MAIO DE 1999',None,'')
    with pytest.raises(IdentityMismatch):
        validate_identity(WorkKey(**args),d)

@pytest.mark.parametrize('authority,title,kind,num',[('cvm','Resolução CVM nº 912, de 7 de maio de 1999','resolucao','912'),('cmn','Resolução CMN nº 9.876, de 7 de maio de 1999','resolucao','9876')])
def test_identity_regulators(authority,title,kind,num):
    d=ParsedDocument('test','1',title,None,'')
    with pytest.raises(IdentityMismatch):
        validate_identity(WorkKey(authority,kind,num,2000),d)
    with pytest.raises(IdentityMismatch):
        validate_identity(WorkKey(authority,kind,num,1999),d,'1999-05-08')

def test_heading_and_editorial():
    from freoa_verifica.parsers.html_devices import _classify_unlabeled_paragraph as classify
    assert classify('Limites das Funções e Poderes') == 'skip'
    assert classify('Nota editorial: confira a edição anterior.') == 'editorial'
    assert classify('a obrigação subsiste até o vencimento.') == 'continuation'
    assert classify('Dado inconclusivo.') == 'uncertain'

@pytest.mark.parametrize('layer',['root','package','repercussaoGeral','processoLeadingCase'])
def test_rg_singleton_lists(layer):
    from freoa_verifica.connectors.stf import _rg, _object
    data={'processoLeadingCase':{'numeroTema':741}}
    if layer=='processoLeadingCase': data[layer]=[data[layer]]
    if layer=='repercussaoGeral': data=[data]
    data={'package':{'repercussaoGeral':data}}
    if layer=='package': data['package']=[data['package']]
    if layer=='root': data=[data]
    assert _object(_rg(data)['processoLeadingCase'])['numeroTema']==741

def test_capture_mismatch_not_indexed(tmp_path,monkeypatch):
    from freoa_verifica.service import Verifica
    from freoa_verifica.connectors.base import Candidate
    from freoa_verifica.transport import Response
    from freoa_verifica.parsers.planalto import parse_planalto
    import hashlib
    body=b'<html><body><h1>LEI N. 8765, DE 7 DE MAIO DE 1999</h1><p>Art. 1 A regra permanece.</p></body></html>'
    doc=ParsedDocument('test','1','Lei 8765/1999',None,'')
    class Connector:
        def resolve(self,key): return Candidate('planalto','candidate','metadata','https://www.planalto.gov.br/ccivil_03/test.htm')
        def fetch(self,c): return Response(c.url,c.url,200,{},body,hashlib.sha256(body).hexdigest(),'2026-01-01T00:00:00+00:00',[],'text/html')
        def parse(self,r): return doc
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s,'_get',lambda name:Connector())
        result=s.verificar_citacao('Lei 8765/2000, art. 1',trecho='A regra permanece.')
        assert result['identity']['status']=='not_found'
        assert result['identity']['reason_code']=='IDENTIDADE_DIVERGENTE'
        assert s.conn.execute('SELECT COUNT(*) FROM work').fetchone()[0]==0
        assert s.conn.execute('SELECT COUNT(*) FROM capture').fetchone()[0]==0

def test_repair_preserves_capture_and_detaches_key(tmp_path):
    from freoa_verifica.service import Verifica
    d=ParsedDocument('test','1','Lei 8765/1999',None,'')
    with Verifica(tmp_path) as s:
        rw=s.indexar_obra(source_id='planalto',work_key=WorkKey('federal','lei','8765',1999),document=d,body=b'receipt',url='https://www.planalto.gov.br/test')
        # Simula associação legada defeituosa, sem alterar captura/modelo.
        s.conn.execute('UPDATE work SET year=2000 WHERE id=?',(rw.work_id,));s.conn.commit()
        assert len(s.reparar_identidades())==1
        assert s.reparar_identidades()==[]
        assert s.conn.execute("SELECT count(*) FROM work WHERE authority='federal' AND year=2000").fetchone()[0]==0
        assert s.conn.execute('SELECT sha256 FROM capture WHERE id=?',(rw.capture_id,)).fetchone()[0]==rw.sha256
        assert not s.conn.execute('PRAGMA foreign_key_check').fetchall()


def test_planalto_nao_repete_por_conta_propria(monkeypatch):
    # FIX5/F-02: a repetição é política do transporte; o conector faz uma chamada por URL.
    from freoa_verifica.connectors import planalto
    from freoa_verifica.connectors.base import Candidate,Unavailable
    calls=[]
    def fetch(url,**kwargs):
        calls.append((url,kwargs))
        raise Unavailable('transporte_Timeout')
    monkeypatch.setattr(planalto,'connector_fetch',fetch)
    with pytest.raises(Unavailable):planalto.PlanaltoConnector().fetch(Candidate('planalto','x','x','https://www.planalto.gov.br/ccivil_03/test.htm'))
    assert len(calls)==1
    assert calls[0][1]['timeout']==180 and calls[0][1]['min_bytes_per_second']==256


def test_planalto_challenge_not_retried(monkeypatch):
    from freoa_verifica.connectors import planalto
    from freoa_verifica.connectors.base import Candidate,Unavailable
    calls=[]
    def fetch(*args,**kwargs):
        calls.append(1);raise Unavailable('desafio_captcha')
    monkeypatch.setattr(planalto,'connector_fetch',fetch)
    with pytest.raises(Unavailable):planalto.PlanaltoConnector().fetch(Candidate('planalto','x','x','https://www.planalto.gov.br/ccivil_03/test.htm'))
    assert len(calls)==1


def test_tcu_session_year_and_organ(tmp_path,monkeypatch):
    from freoa_verifica.service import Verifica
    from freoa_verifica.citation import DecisionKey
    with Verifica(tmp_path) as s:
        s.conn.execute("INSERT INTO decision(id,court,class,number,kind,official_id,identity_status,judgment_date,organ) VALUES ('x','TCU',NULL,'765','acordao_tcu','ACORDAO-COMPLETO-123','confirmed','2024-03-07','Plenário')")
        s.conn.commit()
        # Sem documento capturado: ligação identifica a linha mas não confirma julgamento.
        assert s._decision_evidence(DecisionKey('tcu','Acordao','765',year=2024,organ='Plenário'))[0]=='indisponivel'
        assert s._decision_evidence(DecisionKey('tcu','Acordao','765',year=2023,organ='Plenário'))[0]=='nao_confirmado_no_acervo'
        assert s._decision_evidence(DecisionKey('tcu','Acordao','765',year=2024,organ='2ª Câmara'))[0]=='nao_confirmado_no_acervo'

def test_negative_source_markers():
    from freoa_verifica.connectors.cvm_normas import _parse_list_html
    from freoa_verifica.connectors.cvm_colegiado import _parse_search
    from freoa_verifica.connectors.base import Unavailable
    empty=b'<html><form class="orderResults"><span>Nenhum resultado encontrado</span></form></html>'
    assert _parse_list_html(empty,source_id='cvm_normas',tipo='resolucoes',limite=5,q='synthetic')==[]
    with pytest.raises(Unavailable):_parse_list_html(b'<html>Unexpected page</html>',source_id='cvm_normas',tipo='resolucoes',limite=5,q='synthetic')
    assert _parse_search(b'<html>0 resultados encontrados</html>',base='https://conteudo.cvm.gov.br/decisoes/',source_id='cvm_colegiado',limite=5)==[]
    with pytest.raises(Unavailable):_parse_search(b'<html>Unexpected page</html>',base='https://conteudo.cvm.gov.br/decisoes/',source_id='cvm_colegiado',limite=5)


def test_work_year_zero_repair_and_resolution(tmp_path):
    from freoa_verifica.service import Verifica
    with Verifica(tmp_path) as s:
        for year in [0,2001]:
            s.indexar_obra(source_id='test',work_key=WorkKey('federal','lei','7654',year),document=ParsedDocument('test','1','test',None,''),body=str(year).encode(),url='https://example.org/'+str(year))
        assert s.reparar_identidades()==[]
        assert len(s._rebuild_from_db(WorkKey('federal','lei','7654',0)))==2


def test_cnj_invalid_never_fetches(tmp_path,monkeypatch):
    from freoa_verifica.service import Verifica
    from freoa_verifica.citation import Citation
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s,'_get',lambda *args:pytest.fail('network for invalid number'))
        c=Citation('processo','1234567-00.2022.8.26.0001',(0,25),flags=['cnj_dv_invalido'])
        assert s._confirm_cnj(c)==('formato_invalido',None)

@pytest.mark.parametrize('symbol',['Nº','N°','No','no','n.'])
def test_captured_number_symbols(symbol):
    d=ParsedDocument('test','1',f'Resolução CMN {symbol} 9.876',None,'[tipo=Resolução CMN; numero=9876.0; data=1999-05-07; situacao=vigente]')
    assert validate_identity(WorkKey('cmn','resolucao','9876',1999),d)


def test_senado_metadata_identity():
    import json
    payload={'identificacao':{'tipo':'LEI-n','numero':'8765','dataassinatura':'07/05/1999'}}
    d=ParsedDocument('senado_norma','1','Lei 8.765 de 07/05/1999',None,json.dumps(payload))
    assert validate_identity(WorkKey('federal','lei','8765',1999),d,'1999-05-07')
    with pytest.raises(IdentityMismatch): validate_identity(WorkKey('federal','lei','8765',2000),d)


def test_numeric_epigraph_date():
    c=parse_one('Lei 8.765 de 07/05/1999, art. 87')
    assert c.work.year==1999 and c.path=='art87'

@pytest.mark.parametrize('has_docs,expected',[(True,'encontrada'),(False,'processo_confirmado')])
def test_stf_demand_capture_states(tmp_path,has_docs,expected,monkeypatch):
    from freoa_verifica.service import Verifica
    from freoa_verifica.citation import DecisionKey
    from freoa_verifica.connectors.base import Candidate,ParsedDecision
    from freoa_verifica.transport import Response
    import hashlib
    body=b'official decision listing'
    class Connector:
        id='stf';authority='STF';hosts=frozenset({'portal.stf.jus.br'})
        def resolve(self,key): return Candidate('stf','process','Process','https://portal.stf.jus.br/processos/test',metadata={'incidente':'765432'})
        def fetch(self,c):return Response(c.url,c.url,200,{},body,hashlib.sha256(body).hexdigest(),'2026-01-01T00:00:00+00:00',[],'text/html')
        def parse(self,r):return ParsedDecision('stf_decisoes','decisao','STF','listing',metadata={'items':[{'data_iso':'2024-03-07','julgador':'Tribunal Pleno','docs':[{'url':'official.pdf'}] if has_docs else []}]})
    with Verifica(tmp_path) as s:
        monkeypatch.delenv('FV_OFFLINE',raising=False)
        monkeypatch.setattr(s,'_get',lambda name:Connector())
        status,evidence=s._confirm_decision(DecisionKey('stf','ADI','7654'))
        assert status==expected and evidence['capture_id']
        assert evidence['sha256']==hashlib.sha256(body).hexdigest()
        assert s.conn.execute('SELECT COUNT(*) FROM capture').fetchone()[0]==1

@pytest.mark.parametrize('branch,court',[('826','tjsp'),('807','tjdft'),('413','none'),('406','trf6'),('524','trt24'),('500','tst'),('300','stj'),('100','none')])
def test_cnj_routing(branch,court):
    from freoa_verifica.connectors.datajud import court_from_cnj
    digits='1234567002022'+branch+'0001'
    assert court_from_cnj(digits)==(None if court=='none' else court)


def test_stj_index_exact_identity_and_registration(tmp_path):
    import sqlite3,json
    from freoa_verifica.connectors.stj import StjConnector
    path=tmp_path/'stj.sqlite'
    c=sqlite3.connect(path)
    c.execute('CREATE VIRTUAL TABLE fts_stj USING fts5(key UNINDEXED,title,ementa,organ,rapporteur,decision_date,class_name,payload UNINDEXED)')
    item={'id':'doc-765','numeroRegistro':'202400000765','siglaClasse':'REsp','numeroProcesso':'765432','siglaUF':'MG'}
    c.execute('INSERT INTO fts_stj(key,title,ementa,payload) VALUES (?,?,?,?)',('doc-765','REsp 765432','Ementa sintética',json.dumps(item)))
    c.commit();c.close()
    s=StjConnector(db_path=path)
    assert s.resolve({'classe':'REsp','numero':'765432','uf':'MG'}).key=='doc-765'
    assert s.resolve({'classe':'REsp','numero':'765432','uf':'RS'}) is None
    assert s.resolve({'numeroRegistro':'202400000765'}).key=='doc-765'

@pytest.mark.parametrize('value,expected',[('Relator X, j. 7.3.2024.','2024-03-07'),('sessão de 07/03/2024','2024-03-07'),('reunião de 7/3/2024','2024-03-07'),('j. 31/02/2024',None),('registro 7/3/2024',None)])
def test_decision_date_context(value,expected):
    from freoa_verifica.service import Verifica
    assert Verifica._decision_context_date(value)==expected


def test_snapshot_stj_absence_is_coverage_not_nonexistence(tmp_path,monkeypatch):
    from freoa_verifica.service import Verifica
    from freoa_verifica.citation import DecisionKey
    with Verifica(tmp_path) as s:
        monkeypatch.delenv('FV_OFFLINE',raising=False)
        status,evidence=s._confirm_decision(DecisionKey('stj','REsp','765432'))
        assert status=='nao_confirmado_no_acervo'
        assert evidence['cobertura']['registros']==0


def test_date_mismatch_before_index(tmp_path,monkeypatch):
    from freoa_verifica.service import Verifica
    from freoa_verifica.connectors.base import Candidate
    from freoa_verifica.transport import Response
    import hashlib
    body=b'captured epigraph'
    class Connector:
        def resolve(self,key):return Candidate('planalto','x','x','https://www.planalto.gov.br/test')
        def fetch(self,c):return Response(c.url,c.url,200,{},body,hashlib.sha256(body).hexdigest(),'2026-01-01T00:00:00+00:00',[],'text/html')
        def parse(self,r):return ParsedDocument('test','1','Lei 8765, de 7 de maio de 1999',None,'')
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s,'_get',lambda name:Connector())
        v=s.verificar_citacao('Lei 8765, de 8 de maio de 1999, art. 87')
        assert v['identity']['status']=='not_found' and v['identity']['reason_code']=='IDENTIDADE_DIVERGENTE'
        assert s.conn.execute('select count(*) from work').fetchone()[0]==0

@pytest.mark.parametrize('value',['1ª Câmara','1a Câmara','Primeira Câmara','1 Câmara'])
def test_tcu_organ_general(value):
    from freoa_verifica.service import Verifica
    assert Verifica._organ_key(value)=='1camara'


def test_receipt_reuse_authenticates_changed_bytes(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import hashlib
    from freoa_verifica.service import Verifica
    from freoa_verifica.transport import Response
    from freoa_verifica.store import repo
    body=b'official resource'
    response=Response('https://example.org/resource','https://example.org/resource',200,{},body,hashlib.sha256(body).hexdigest(),'2026-01-01T00:00:00+00:00',[],'application/json')
    with Verifica(tmp_path) as s:
        s.conn.execute("INSERT INTO source(id,authority,profile,hosts_json) VALUES ('test','test','test','[]')");s.conn.commit()
        connector=SimpleNamespace(id='test')
        calls=[];original=repo.save_capture
        def save(*a,**kw):calls.append(1);return original(*a,**kw)
        monkeypatch.setattr(repo,'save_capture',save)
        first=s._save_juris_capture(connector,response)
        assert s._save_juris_capture(connector,response)==first and len(calls)==1
        from dataclasses import replace
        changed = replace(response,body=b'changed resource')
        with pytest.raises(ValueError):s._save_juris_capture(connector,changed)
        assert len(calls)==2


def test_repair_removes_only_invalidated_fts(tmp_path):
    from freoa_verifica.service import Verifica
    from freoa_verifica.parsers.model import Provision,Redaction
    with Verifica(tmp_path) as s:
        d=ParsedDocument('test','1','Lei 8765/1999',None,'',provisions=[Provision('art87','Art. 87','',redactions=[Redaction('Texto sintético.',False,0)])])
        rw=s.indexar_obra(source_id='test',work_key=WorkKey('federal','lei','8765',1999),document=d,body=b'receipt',url='https://example.org/',label='Lei fictícia')
        assert s.conn.execute('SELECT count(*) FROM fts_redaction').fetchone()[0]==1
        s.conn.execute('UPDATE work SET year=2000 WHERE id=?',(rw.work_id,));s.conn.commit()
        assert len(s.reparar_identidades())==1
        assert s.conn.execute('SELECT count(*) FROM fts_redaction').fetchone()[0]==0
        assert s.conn.execute('SELECT count(*) FROM capture').fetchone()[0]==1


def test_cvm_pdf_epigraph_year_from_captured_text():
    d=ParsedDocument('cvm_pdf','1','resol912.pdf',None,'COMISSÃO DE VALORES MOBILIÁRIOS\nRESOLUÇÃO CVM Nº 912, DE 7 DE MAIO DE 1999\nArt. 1 A Resolução CVM 913, de 2000, é mencionada no corpo.')
    assert validate_identity(WorkKey('cvm','resolucao','912',1999),d,'1999-05-07')
    with pytest.raises(IdentityMismatch):validate_identity(WorkKey('cvm','resolucao','912',2000),d)

@pytest.mark.parametrize('alias,year,number',[('CDC',1990,'8078'),('CPC',2015,'13105'),('Código Civil',2002,'10406')])
def test_dated_alias_general(alias,year,number):
    c=parse_one(f'Conforme {alias}/{year}, artigo 87, § 3º')
    assert c is None
    c=parse_one(f'Conforme {alias}, artigo 87, § 3º')
    assert c.path=='art87.par3' and c.work.number==number and c.work.year==year


def test_recovery_long_alias_variant():
    c=parse_one('artigo 87, § 3º, da Lei de Recuperação de Empresas e Falências')
    assert c.path=='art87.par3' and c.work.number=='11101'


def test_tcu_fetch_reuses_official_page_and_selects_identity(monkeypatch):
    import json,hashlib
    from freoa_verifica.connectors import tcu
    from freoa_verifica.transport import Response
    from freoa_verifica.connectors.base import Unavailable,Candidate
    body=json.dumps([{'key':'record-765','numeroAcordao':'765','dataSessao':'07/03/2024','sumario':'Primeiro'},{'key':'record-766','numeroAcordao':'766','dataSessao':'07/03/2024','sumario':'Segundo'}]).encode()
    receipt=Response('https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos?inicio=0','https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos?inicio=0',200,{},body,hashlib.sha256(body).hexdigest(),'2026-01-01T00:00:00+00:00',[],'application/json')
    calls=[]
    def fetch(*a,**kw):calls.append(1);return receipt
    monkeypatch.setattr(tcu,'connector_fetch',fetch)
    connector=tcu.TcuConnector();found=connector.search('',quantidade=2)
    assert connector.fetch(found[1]) is receipt and len(calls)==1
    assert connector.parse_candidate(receipt,found[1]).official_id=='record-766'
    assert connector.parse_candidate(receipt,found[1]).text=='Segundo'
    with pytest.raises(Unavailable):connector.parse_candidate(receipt,Candidate('tcu','missing','missing'))


def test_cvm_process_number_punctuation_symmetric(tmp_path):
    from freoa_verifica.service import Verifica
    from freoa_verifica.citation import DecisionKey
    with Verifica(tmp_path) as s:
        s.conn.execute("INSERT INTO decision(id,court,class,number,kind,official_id,identity_status,judgment_date) VALUES ('x','CVM','PAS','12345.654321/2024-12','decisao_colegiado_cvm','official-page','confirmed','2024-03-07')")
        s.conn.commit()
        assert s._decision_evidence(DecisionKey('cvm','PAS','12345.654321/2024-12'))[0]=='indisponivel'
        assert s._decision_evidence(DecisionKey('cvm','PAS','12345.654321/2023-12'))[0]=='nao_confirmado_no_acervo'


def test_issuer_is_part_of_identity():
    d=ParsedDocument('test','1','Resolução CVM nº 912, de 7 de maio de 1999',None,'')
    with pytest.raises(IdentityMismatch):validate_identity(WorkKey('cmn','resolucao','912',1999),d)


def test_tcu_summary_is_not_full_text_and_repair(tmp_path,monkeypatch):
    import json,hashlib
    from freoa_verifica.connectors import tcu
    from freoa_verifica.transport import Response
    from freoa_verifica.service import Verifica
    body=json.dumps([{'key':'record-765','numeroAcordao':'765','dataSessao':'07/03/2024','sumario':'Resumo sintético. '*100}]).encode()
    receipt=Response('https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos','https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos',200,{},body,hashlib.sha256(body).hexdigest(),'2026-01-01T00:00:00+00:00',[],'application/json')
    monkeypatch.setattr(tcu,'connector_fetch',lambda *a,**kw:receipt)
    connector=tcu.TcuConnector();candidate=connector.search('',quantidade=1)[0]
    with Verifica(tmp_path) as s:
        s._index_candidate_juris(connector,candidate)
        assert s.conn.execute('select kind from decision_document').fetchone()[0]=='ementa'
        s.conn.execute("update decision_document set kind='inteiro_teor',nivel_prova='inteiro_teor_capturado'");s.conn.commit()
        s.reparar_identidades()
        assert s.conn.execute('select kind,nivel_prova from decision_document').fetchone()[:]==('ementa','ementa_capturada')


def test_stf_multiple_leading_cases_are_preserved(monkeypatch):
    import json,hashlib
    from freoa_verifica.connectors import stf
    from freoa_verifica.transport import Response
    records=[{'numeroTema':741,'tituloTema':'Tema sintético','seqObjetoIncidente':7650+i,'siglaClasse':'RE','numeroProcesso':87650+i} for i in range(2)]
    body=json.dumps({'package':{'repercussaoGeral':{'processoLeadingCase':records}}}).encode()
    receipt=Response('https://sistemas.stf.jus.br/repgeral/votacao?tema=741','https://sistemas.stf.jus.br/repgeral/votacao?tema=741',200,{},body,hashlib.sha256(body).hexdigest(),'2026-01-01T00:00:00+00:00',[],'application/json')
    monkeypatch.setattr(stf,'connector_fetch',lambda *a,**kw:receipt)
    connector=stf.StfConnector()
    candidates=connector.resolve_tema(741)
    assert len(candidates)==2 and {c.metadata['incidente'] for c in candidates}=={7650,7651}
    parsed=connector.parse(receipt)
    assert parsed.official_id=='741' and len(parsed.metadata['leading_cases'])==2
    assert parsed.class_name is None


def test_stf_explicit_negative_only(monkeypatch):
    import hashlib
    from freoa_verifica.connectors import stf
    from freoa_verifica.connectors.base import Unavailable
    from freoa_verifica.transport import Response
    def receipt(body):return Response('https://portal.stf.jus.br/processos/listarProcessos.asp','https://portal.stf.jus.br/processos/listarProcessos.asp',200,{},body,hashlib.sha256(body).hexdigest(),'2026-01-01T00:00:00+00:00',[],'text/html')
    negative=receipt('<html><meta charset="utf-8">Processo não encontrado</html>'.encode())
    monkeypatch.setattr(stf,'connector_fetch',lambda *a,**kw:negative)
    connector=stf.StfConnector()
    assert connector.resolve({'classe':'ADI','numero':765432}) is None
    assert connector.last_not_found_response is negative
    monkeypatch.setattr(stf,'connector_fetch',lambda *a,**kw:receipt(b'<html>Unexpected page</html>'))
    with pytest.raises(Unavailable):connector.resolve({'classe':'ADI','numero':765432})
    assert connector.last_not_found_response is None

@pytest.mark.parametrize('separator',[',','—','–'])
def test_general_device_separators(separator):
    c=parse_one(f'Lei 8.765/1999 {separator} artigo 87, § 3º')
    assert c.path == ('art87.par3' if separator == ',' else None)

@pytest.mark.parametrize('separator',['-',':',';','.','\n\n'])
def test_general_device_clause_boundaries(separator):
    c=parse_one(f'Lei 8.765/1999 {separator} artigo 87, § 3º')
    assert c.path == ('art87.par3' if separator in {':', ';', '\n\n'} else None)
    if c.path:
        assert c.confidence == 'provavel'

@pytest.mark.parametrize('marker',['Parte Geral','PARTE GERAL'])
def test_general_part_marker(marker):
    c=parse_one(f'Resolução CVM 912, {marker}, artigo 87, inciso XIV')
    assert c.path is None


def test_stf_official_rtf_link_and_unicode():
    from freoa_verifica.connectors.stf import _parse_aba_decisoes
    body='<div class="andamento-item"><div class="andamento-data">07/03/2024</div><div class="andamento-nome">Decisão</div><span class="andamento-julgador">ÓRGÃO COLEGIADO</span><a href="downloadTexto.asp?id=765&amp;ext=RTF">Decisão de julgamento</a></div>'.encode()
    items=_parse_aba_decisoes(body,base='https://portal.stf.jus.br/processos/abaDecisoes.asp')
    assert items[0]['julgador']=='ÓRGÃO COLEGIADO'
    assert items[0]['docs'][0]['url']=='https://portal.stf.jus.br/processos/downloadTexto.asp?id=765&ext=RTF'


def test_datajud_source_court_case_does_not_change_endpoint(monkeypatch):
    from freoa_verifica.connectors import datajud
    captured=[]
    marker=object()
    def fetch(url,**kw):captured.append(url);return marker
    monkeypatch.setattr(datajud,'connector_fetch',fetch)
    assert datajud.DatajudConnector()._post('TJSP',{'query':{}}) is marker
    assert captured==['https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search']


def test_legacy_completed_context_retries_pending_children(tmp_path,monkeypatch):
    from freoa_verifica.service import Verifica
    from freoa_verifica.semente import SementeSync
    with Verifica(tmp_path) as s:
        sync=SementeSync(s,rate_delay=0)
        sync.corpus={'planalto':[{'tipo':'LEI','numero':'8765','ano':1999}], 'leis_principais_alteradores':[{'tipo':'LEI','numero':'8765','ano':1999}]}
        sync.state.set('alterador_contexto','LEI:8765:1999','concluido')
        sync.state.set('alterador','LEI:8766:2000','indisponivel',motivo='transporte_Timeout')
        monkeypatch.setattr(sync,'_index_legis',lambda *a,**kw:('pulado',None))
        calls=[]
        def resolve(*a,**kw):
            calls.append(1);sync.state.set('alterador','LEI:8766:2000','parseado');return True
        monkeypatch.setattr(sync,'_resolve_alteradores',resolve)
        sync.sync_planalto();sync.sync_planalto()
        assert calls==[1]
        assert sync.state.get('alterador_contexto','LEI:8765:1999')['status']=='concluido'

@pytest.mark.parametrize('status',[404,410])
def test_expected_http_absence_does_not_poison_circuit(monkeypatch,status):
    import hashlib
    from freoa_verifica import transport as tr
    tr.reset_guards();calls=[]
    monkeypatch.setattr(tr,'_rate_limiter',lambda host:tr.TokenBucket(rate=100000,capacity=100000))
    def once(url,**kw):
        calls.append(1)
        if len(calls)<=6:raise tr.HTTPStatusError(status)
        return tr.Response(url,url,200,{},b'ok',hashlib.sha256(b'ok').hexdigest(),'2026-01-01T00:00:00+00:00',[],'text/plain')
    monkeypatch.setattr(tr,'_fetch_once',once)
    try:
        for i in range(6):
            with pytest.raises(tr.HTTPStatusError):tr.fetch('https://example.org/test',allowed_hosts=frozenset({'example.org'}))
        assert tr.fetch('https://example.org/test',allowed_hosts=frozenset({'example.org'})).body==b'ok'
        assert len(calls)==7 and tr._circuit_breaker('example.org').failures==0
    finally:tr.reset_guards()


def test_orphan_pending_checkpoint_is_retried_without_current_reference(tmp_path,monkeypatch):
    from freoa_verifica.service import Verifica
    from freoa_verifica.semente import SementeSync
    with Verifica(tmp_path) as s:
        sync=SementeSync(s,rate_delay=0);sync.corpus={'planalto':[]}
        sync.state.set('alterador','LEI:8766:2000','indisponivel',motivo='transporte_Timeout')
        calls=[]
        def index(fonte,key,**kw):
            calls.append((key,kw['work_key']));sync.state.set(fonte,key,'parseado');return 'parseado',None
        monkeypatch.setattr(sync,'_index_legis',index)
        sync.sync_planalto();sync.sync_planalto()
        assert calls==[('LEI:8766:2000',WorkKey('federal','lei','8766',2000))]
