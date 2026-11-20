"""Provas offline dos guardiões do harness; não abrem navegador nem sockets."""

from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

from tests.gerar_0089_wire import BODY, gerar
from tests.harness_assistida_0089_cenarios import (
    SondaEventos,
    conferir_recusa_streaming,
    exigir_recusa,
    varrer_artefatos,
)


def test_fixtures_wire_reproduziveis():
    fixtures = Path(__file__).parent / "fixtures"
    for encoding, data in gerar().items():
        assert (fixtures / f"0089_wire_{encoding}.bin").read_bytes() == data


def test_zstd_decodificado_independentemente():
    zstd = pytest.importorskip(
        "compression.zstd",
        reason="decoder da biblioteca padrão só existe a partir do Python 3.14; nenhuma dependência opcional exigida",
    )
    assert zstd.decompress(gerar()["zstd"]) == BODY


@pytest.mark.parametrize("codec", ["utf-8", "utf-16-le", "utf-16-be"])
def test_varredura_detecta_segredo_inclusive_em_wal(tmp_path, codec):
    pasta = tmp_path / "subdiretorio"
    pasta.mkdir()
    (pasta / "verifica.sqlite3-wal").write_bytes(
        b"prefixo" + "SEGREDO_SINTETICO".encode(codec)
    )
    with pytest.raises(AssertionError):
        varrer_artefatos(tmp_path, ["SEGREDO_SINTETICO"])


def test_varredura_nao_aceita_diretorio_vazio(tmp_path):
    with pytest.raises(AssertionError, match="varredura vazia"):
        varrer_artefatos(tmp_path, ["SEGREDO_SINTETICO"])


@pytest.mark.parametrize("registros", [[], [("publico", "STREAMING_ASSISTIDO_TARDIO")]])
def test_negativo_nao_passa_no_vazio_ou_por_causa_alheia(registros):
    ad = SimpleNamespace(motivos_recusas=registros, pedidos={})
    with pytest.raises(AssertionError):
        exigir_recusa(ad, "publico", {"COOKIE_ASSISTIDO_RECUSADO"})


@pytest.mark.parametrize("valor", [None, "0", "true", "1"])
def test_gesto_humano_exige_opt_in_exato(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("FV_0089_GESTO_HUMANO", raising=False)
    else:
        monkeypatch.setenv("FV_0089_GESTO_HUMANO", valor)
    modulo = runpy.run_path(
        str(Path(__file__).with_name("test_assistida_0089_navegador_cenarios.py"))
    )
    for nome in (
        "test_item2_recarga_forcada_humana_vem_da_rede",
        "test_item1_item8_instalacao_manual_desempacotada_recusa",
    ):
        marca = next(m for m in modulo[nome].pytestmark if m.name == "skipif")
        assert marca.args == (valor != "1",)
        assert "FV_0089_GESTO_HUMANO=1" in marca.kwargs["reason"]


@pytest.mark.parametrize(
    "ordem,aceita",
    [
        (["fim", "resposta"], True),
        (["fim"], True),
        (["resposta", "fim"], False),
        (["resposta"], False),
        ([], False),
    ],
)
def test_recusa_tardia_exige_fim_antes_da_resposta(ordem, aceita):
    ad = SimpleNamespace(
        alvos={}, processar=lambda _: None, canal=SimpleNamespace(enviar=lambda _: None)
    )
    sonda = SondaEventos(ad)
    sonda.processar(
        {
            "method": "Network.requestWillBeSent",
            "sessionId": "sid",
            "params": {
                "requestId": "rid",
                "request": {"url": "publico"},
            },
        }
    )
    sonda.enviar(
        {
            "id": 1,
            "method": "Network.streamResourceContent",
            "sessionId": "sid",
            "params": {"requestId": "rid"},
        }
    )
    for passo in ordem:
        sonda.processar(
            {"id": 1, "result": {"bufferedData": ""}}
            if passo == "resposta"
            else {
                "method": "Network.loadingFinished",
                "sessionId": "sid",
                "params": {"requestId": "rid"},
            }
        )
    if aceita:
        conferir_recusa_streaming(sonda, "publico", "STREAMING_ASSISTIDO_TARDIO")
    else:
        with pytest.raises(AssertionError):
            conferir_recusa_streaming(sonda, "publico", "STREAMING_ASSISTIDO_TARDIO")


def test_erro_streaming_exige_erro_do_proprio_comando():
    eventos = [{"url": "outro", "stream_resposta": True, "stream_erro": True}]
    sonda = SimpleNamespace(eventos=eventos)
    with pytest.raises(AssertionError):
        conferir_recusa_streaming(sonda, "publico", "COMANDO_STREAMING_RECUSADO")
    eventos[0]["url"] = "publico"
    conferir_recusa_streaming(sonda, "publico", "COMANDO_STREAMING_RECUSADO")


def test_early_hints_http2_em_memoria():
    pytest.importorskip(
        "h2",
        reason="prova HTTP/2 requer extra .[test-navegador]; não exercitada sem a dependência",
    )
    from h2.config import H2Configuration
    from h2.connection import H2Connection
    from h2.events import (
        InformationalResponseReceived,
        ResponseReceived,
        StreamEnded,
        DataReceived,
    )
    from tests.harness_assistida_0089_h2 import responder_h2

    servidor = H2Connection(config=H2Configuration(client_side=False))
    cliente = H2Connection(config=H2Configuration(header_encoding="utf-8"))
    cliente.initiate_connection()
    servidor.initiate_connection()
    servidor.receive_data(cliente.data_to_send())
    cliente.receive_data(servidor.data_to_send())
    cliente.send_headers(
        1,
        [
            (":method", "GET"),
            (":scheme", "https"),
            (":authority", "127.0.0.1"),
            (":path", "/case/early_hints"),
        ],
        end_stream=True,
    )
    servidor.receive_data(cliente.data_to_send())
    estado = {"marcas": [], "erros": []}
    assert responder_h2(servidor, "/case/early_hints", 1, estado, hints=True) is None
    eventos = cliente.receive_data(servidor.data_to_send())
    hints = next(e for e in eventos if isinstance(e, InformationalResponseReceived))
    assert dict(hints.headers) == {
        ":status": "103",
        "link": "</case/hinted>; rel=preload; as=script",
    }
    assert not any(isinstance(e, (ResponseReceived, StreamEnded)) for e in eventos)
    corpo = responder_h2(servidor, "/case/early_hints", 1, estado)
    servidor.send_data(1, corpo, end_stream=True)
    eventos = cliente.receive_data(servidor.data_to_send())
    final = next(e for e in eventos if isinstance(e, ResponseReceived))
    assert dict(final.headers)[":status"] == "200"
    assert b"".join(e.data for e in eventos if isinstance(e, DataReceived)) == corpo
    assert any(isinstance(e, StreamEnded) for e in eventos)
