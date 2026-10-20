import hashlib
import http.client
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from freoa_verifica import transport as tr
from freoa_verifica.connectors.challenge import detect_challenge
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.stj import StjConnector
from freoa_verifica.semente import SementeSync, SyncState
from freoa_verifica.service import Verifica
from tests.fixture_util import load_fixture
from tests.test_m6_completion import LegisConnector


def test_cvm_real_recaptcha_is_not_challenge():
    body = load_fixture('cvm_index_recaptcha_real')
    assert b'recaptcha/api.js' in body
    assert detect_challenge(status=200, body=body) is None
    assert detect_challenge(status=200, body=body, expected_content=r'/legislacao/resolucoes/resol') is None


def test_challenge_requires_missing_expected_content():
    challenge = '<html><form class="g-recaptcha">Confirme captcha</form></html>'
    assert detect_challenge(status=200, body=challenge, expected_content=r'<article id="normas"') is not None
    assert detect_challenge(status=200, body=challenge + '<article id="normas">conteudo</article>', expected_content=r'<article id="normas"') is None
    # Cabeçalhos de mitigação/status prevalecem sobre conteúdo suspeito.
    assert detect_challenge(status=403, body=challenge) is not None


@pytest.mark.parametrize('mode', ['deadline', 'slow', 'chunked', 'headers'])
def test_drip_closes_socket_and_releases_worker(monkeypatch, mode):
    stop = threading.Event()
    closed = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            try:
                if mode == 'headers':
                    self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Drip: ')
                    self.wfile.flush()
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain')
                    self.send_header('Transfer-Encoding' if mode == 'chunked' else 'Content-Length', 'chunked' if mode == 'chunked' else '100')
                    self.end_headers()
                while not stop.is_set():
                    self.wfile.write(b'1\r\nx\r\n' if mode == 'chunked' else b'x')
                    self.wfile.flush()
                    stop.wait(1.0)  # servidor real: 1 byte/s
            except (OSError, ValueError):
                closed.set()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    class Local(http.client.HTTPConnection):
        def __init__(self, host, ip, *, timeout):
            super().__init__('127.0.0.1', server.server_port, timeout=timeout)
    monkeypatch.setattr(tr, 'PinnedHTTPSConnection', Local)
    monkeypatch.setattr(tr, 'validate_url', lambda *args, **kwargs: ('example.com', '/', '127.0.0.1'))
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(tr, '_CAPTURE_SLOTS', slots)
    monkeypatch.setattr(tr, 'SLOW_WINDOW', 2.2)
    tr.reset_guards()
    started = time.monotonic()
    try:
        # B3-01: prazo vencido depois do status 200 é resposta inválida; sem status segue Timeout.
        error = {'slow': tr.TransporteLento, 'chunked': tr.TransporteLento, 'deadline': tr.RespostaInvalida}.get(mode, tr.Timeout)
        with pytest.raises(error):
            tr.fetch('https://example.com/', allowed_hosts=frozenset({'example.com'}), timeout=6 if mode in {'slow', 'chunked'} else 2.2)
        assert time.monotonic() - started < 4
        assert slots.acquire(timeout=1), 'worker continua preso apos prazo externo'
        slots.release()
        assert closed.wait(3), 'conexao de gotejamento continua ativa'
    finally:
        stop.set(); server.shutdown(); server.server_close(); thread.join(2)


def test_transient_requeued_after_other_items(tmp_path, monkeypatch):
    monkeypatch.delenv('FV_OFFLINE', raising=False)
    calls = []
    class Connector(LegisConnector):
        def fetch(self, cand):
            calls.append(cand.key)
            if cand.key == '99991' and calls.count(cand.key) == 1:
                raise Unavailable('transporte_Timeout')
            self.failed = False
            return super().fetch(cand)
    with Verifica(tmp_path) as svc:
        svc._connectors['planalto'] = Connector()
        engine = SementeSync(svc, fontes=['planalto'], rate_delay=0)
        engine.corpus['planalto'] = [{'tipo':'LEI','numero':n,'ano':2000} for n in ['99991','99992']]
        result = engine.run()
        assert calls == ['99991', '99992', '99991']
        assert result['fontes'][0]['indisponiveis'] == 0
        assert result['fontes'][0]['parseados'] == 2


def test_stj_monthly_resource_limit_cache_and_proof(tmp_path, monkeypatch):
    import freoa_verifica.connectors.stj as stj
    from tests.test_m6_completion import LegisConnector
    from freoa_verifica.transport import Response
    from datetime import datetime, timezone
    resources = [{'id':str(i),'name':f'{202300+i if i <= 12 else 202400+i-12:06d}28.json','format':'JSON','url':f'https://dadosabertos.web.stj.jus.br/dataset/{i}'} for i in range(1,15)]
    resources += [{'name':'historico.zip','format':'ZIP','url':'https://dadosabertos.web.stj.jus.br/dataset/archive'}]
    calls=[]
    def response(url, **kwargs):
        calls.append(url)
        body = json.dumps({'success':True, 'result':{'resources':resources}}).encode() if 'package_show' in url else json.dumps([{'id':url.rsplit('/',1)[-1]+'-'+str(i),'ementa':'EMENTA '+str(i)} for i in range(3)]).encode()
        return Response(url,url,200,{},body,hashlib.sha256(body).hexdigest(),datetime.now(timezone.utc).isoformat(),[],'application/json')
    monkeypatch.setattr(stj, 'connector_fetch', response)
    with Verifica(tmp_path) as svc:
        c=svc._get('stj'); c.sync_state=SyncState(svc.conn)
        assert c.sync(orgaos=['pkg'],max_itens=2) == 24
        assert len(calls) == 13
        assert not any('archive' in u for u in calls)
        before=len(calls)
        assert c.sync(orgaos=['pkg'],max_itens=2) == 0
        assert len(calls) == before + 2  # decisão 0039: os 2 meses mais recentes são sempre revalidados (sha igual: nada reprocessado)
        cand=c.search('EMENTA',limite=1)[0]
        raw=c.fetch(cand)
        parsed=c.parse_candidate(raw,cand)
        assert parsed.official_id == cand.key
        assert len(json.loads(raw.body)) == 3
        assert raw.final_url.startswith('https://dadosabertos.web.stj.jus.br/')


def test_bench_supports_false_decision_without_changing_gold(tmp_path):
    from freoa_verifica.bench import run_bench
    path = tmp_path / 'gold.jsonl'
    path.write_text(json.dumps({'id':'f','tipo':'decisao_falsa','citacao':'STF, ADI 9877','tribunal':'STF'}), encoding='utf-8')
    before = path.read_bytes()
    class Svc:
        def verificar_texto(self, text):
            return {'citacoes':[{'status':'indisponivel','parseada':{'decision':{'court':'STF'}}}]}
    result = run_bench(Svc(),path)
    assert path.read_bytes() == before
    assert result['metricas']['decisoes']['falsas'] == {'total':1,'acertos':0}
    assert result['metricas']['indisponibilidade_por_fonte'] == {'STF':1}
    assert result['casos'][0]['resultado']['citacoes'][0]['status'] == 'indisponivel'


def test_stj_cache_reopens_and_expires(tmp_path, monkeypatch):
    import freoa_verifica.connectors.stj as stj
    from freoa_verifica.transport import Response
    from datetime import datetime, timezone
    calls=[]
    def response(url, **kwargs):
        calls.append(url)
        body=b'{"success":true,"result":{"resources":[]}}'
        return Response(url,url,200,{},body,hashlib.sha256(body).hexdigest(),datetime.now(timezone.utc).isoformat(),[],'application/json')
    monkeypatch.setattr(stj,'connector_fetch',response)
    with Verifica(tmp_path) as svc:
        c=svc._get('stj'); c.sync_state=SyncState(svc.conn)
        c.package_show('pkg')
    with Verifica(tmp_path) as svc:
        c=svc._get('stj'); c.sync_state=SyncState(svc.conn)
        c.package_show('pkg')
        assert len(calls)==1
        svc.conn.execute("UPDATE sync_state SET updated_at='2000-01-01T00:00:00+00:00'")
        svc.conn.commit()
        c.package_show('pkg')
        assert len(calls)==2


def test_retry_waits_for_breaker_and_preserves_terminal_reason(tmp_path, monkeypatch):
    import freoa_verifica.semente as seed
    times=[100.0]
    waits=[]
    monkeypatch.setattr(seed.time,'monotonic',lambda:times[0])
    def sleep(seconds):
        waits.append(seconds); times[0]+=seconds
    monkeypatch.setattr(seed.time,'sleep',sleep)
    monkeypatch.setattr(tr,'circuit_retry_after',lambda:3.0)
    monkeypatch.delenv('FV_OFFLINE',raising=False)
    with Verifica(tmp_path) as svc:
        svc._connectors['planalto']=LegisConnector()
        engine=SementeSync(svc,fontes=['planalto'],rate_delay=0)
        engine.corpus['planalto']=[{'tipo':'LEI','numero':'99991','ano':2000}]
        result=engine.run()
        assert svc._connectors['planalto'].calls == 3
        assert sum(waits)==6.0
        assert result['fontes'][0]['motivos']=={'transitorio':1}
        assert engine.state.get('planalto','LEI:99991:2000')['motivo']=='transitorio'


def test_bcb_http_400_stays_unavailable(monkeypatch):
    from freoa_verifica.connectors.bcb import BcbConnector
    import freoa_verifica.connectors.httputil as http
    def fail(*args,**kwargs): raise tr.HTTPStatusError(400)
    monkeypatch.setattr(http,'transport_fetch',fail)
    with pytest.raises(Unavailable,match='http_400'):
        BcbConnector().search('',tipo='Resolução CMN',numero=4966)


def test_long_stj_mirror_is_not_full_judgment(tmp_path, monkeypatch):
    import freoa_verifica.connectors.stj as stj
    from freoa_verifica.connectors.base import Candidate
    from freoa_verifica.transport import Response
    from datetime import datetime,timezone
    body=json.dumps([{'id':'1','ementa':'Ementa','decisao':'texto do espelho '*100}]).encode()
    url='https://dadosabertos.web.stj.jus.br/dataset/test.json'
    resp=Response(url,url,200,{},body,hashlib.sha256(body).hexdigest(),datetime.now(timezone.utc).isoformat(),[],'application/json')
    with Verifica(tmp_path) as svc:
        c=svc._get('stj')
        monkeypatch.setattr(c,'fetch',lambda cand:resp)
        item=svc._index_candidate_juris(c,Candidate('stj','1','Acórdão',url,metadata={'court':'STJ'}))
        assert item['nivel_prova']=='ementa_capturada'


def test_amending_context_failure_does_not_discard_remaining_queue(tmp_path, monkeypatch):
    monkeypatch.delenv('FV_OFFLINE', raising=False)
    calls=[]
    with Verifica(tmp_path) as svc:
        c=LegisConnector();c.failed=False;svc._connectors['planalto']=c
        engine=SementeSync(svc,fontes=['planalto'],rate_delay=0)
        engine.corpus['planalto']=[{'tipo':'LEI','numero':n,'ano':2000} for n in ['99991','99992']]
        engine.corpus['leis_principais_alteradores']=engine.corpus['planalto'][:1]
        def context(key,**kwargs):
            calls.append(key)
            if len(calls)==1: raise Unavailable('transporte_Timeout')
        monkeypatch.setattr(engine,'_resolve_alteradores',context)
        result=engine.run()
        assert c.calls==2
        assert len(calls)==2
        assert engine.state.done('planalto','LEI:99992:2000')
        assert engine.state.get('alterador_contexto','LEI:99991:2000')['status']=='concluido'
        assert result['fontes'][0]['indisponiveis']==0


def test_recovered_source_is_not_requeued_again(tmp_path, monkeypatch):
    monkeypatch.delenv('FV_OFFLINE',raising=False)
    with Verifica(tmp_path) as svc:
        engine=SementeSync(svc,fontes=['planalto'],rate_delay=0)
        calls=[]
        def source():
            calls.append(1)
            if len(calls)==1: raise Unavailable('transporte_Timeout')
        monkeypatch.setattr(engine,'sync_planalto',source)
        result=engine.run()
        assert len(calls)==2
        assert result['fontes'][0]['indisponiveis']==0


def test_successful_bcb_discovery_replaces_old_failure(tmp_path, monkeypatch):
    with Verifica(tmp_path) as svc:
        class Connector:
            def search(self,*args,**kwargs):return []
        svc._connectors['bcb']=Connector()
        engine=SementeSync(svc,rate_delay=0)
        engine.corpus['bcb_cmn']={'recentes':{'tipos':['Resolução CMN'],'quantidade':200}}
        engine.state.set('bcb','recentes:Resolução CMN','indisponivel',motivo='http_400')
        engine.sync_bcb()
        row=engine.state.get('bcb','recentes:Resolução CMN')
        assert row['status']=='metadados'
        assert row['motivo'] is None


@pytest.mark.parametrize('src',['"https://www.google.com/recaptcha/api.js"','https://www.google.com/recaptcha/api.js'])
def test_script_inclusion_alone_is_not_challenge(src):
    assert detect_challenge(status=200,body=f'<html><script src={src}></script></html>') is None


def test_stj_without_monthly_json_is_unavailable_not_zero(tmp_path,monkeypatch):
    c=StjConnector(tmp_path/'stj.sqlite')
    monkeypatch.setattr(c,'package_show',lambda pkg:{'resources':[{'name':'historico.zip','format':'ZIP','url':'https://dadosabertos.web.stj.jus.br/dataset/archive'}]})
    with pytest.raises(Unavailable,match='stj_sem_recursos_json_mensais_no_recorte'):
        c.sync(orgaos=['pkg'])
