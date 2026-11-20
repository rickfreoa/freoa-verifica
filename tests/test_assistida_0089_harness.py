"""Provas offline dos guardiões do harness; não abrem navegador nem sockets."""

from pathlib import Path

import pytest

from tests.gerar_0089_wire import BODY, gerar
from tests.harness_assistida_0089_cenarios import varrer_artefatos


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
