"""F14: inventario literal do auditor e regra de classe nas fachadas publicas."""
import re

import pytest

from freoa_verifica.aliases import WorkKey
from tests.test_il2c_r1 import _conteudo
from tests.test_il2c_r2 import NORMS, acervo_r2, cite  # noqa: F401


# Transcricao dos 102 caminhos do parecer r3, independente do parser.
F14 = {
    "lsa": "art15 art16 art17 art17.par1 art17.par1.inc1 art24 art31 art34 art39 art40 art42 art43 art44 art45 art47 art49 art50 art55 art58 art64 art66 art66.par3 art68 art68.par1 art71 art72 art72.par2 art73 art78 art79 art100 art101 art104 art109 art117 art117.par1 art118 art121 art122 art123 art123.parunico art124 art124.par1 art124.par5 art125 art126 art126.par2 art127 art133 art135 art136 art146 art147 art147.par3 art155 art157 art162 art163 art164 art170 art170.par1 art172 art176 art178 art178.par1 art178.par2 art184 art196 art202 art202.inc1 art202.par3 art206 art206.inc1 art215 art223 art226 art229 art243 art247 art248 art250 art252 art256 art256.inc2 art264 art270 art279 art287 art287.inc2 art291",
    "lc": "art6 art7 art7.parunico art8 art18-B art39 art47 art62 art64 art85-A art85-A.par2",
    "lib": "art1",
}
CASES = [(n, p) for n, spec in F14.items() for p in spec.split()]
assert len(CASES) == 102


def sem_inicio(value):
    """Inspecao recursiva: qualquer intervalo/linha deve abster-se do inicio."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "inicio":
                assert item is None, value
            sem_inicio(item)
    elif isinstance(value, list):
        for item in value:
            sem_inicio(item)


@pytest.mark.parametrize("norm,path", CASES)
def test_f14_obtencao_e_historico_publicos(acervo_r2, norm, path):
    citation = cite(norm, path)
    obtained = _conteudo(acervo_r2.obter_dispositivo(citation))
    history = _conteudo(acervo_r2.historico_dispositivo(citation))
    assert obtained["vigencia"]["status"] == "unknown"
    assert obtained["vigencia"]["limites_inferidos"]
    assert obtained["vigencia"]["needs_judgment"]
    assert obtained["redacao_anterior_ausente_na_fonte"] is True
    assert history["status"] == "unknown"
    assert history["linha_do_tempo"] == []
    assert history["needs_judgment"]
    assert history["redacao_anterior_ausente_na_fonte"] is True
    assert obtained["anotacoes"]
    assert history["eventos"]
    for annotation in obtained["anotacoes"] + history["eventos"]:
        # Correção do titular: a nota é preservada, mas não ganha alvo impróprio.
        if re.search(r"\bcaput\W+d[oa]\s+(?:parágrafo|inciso|alínea)\b", annotation["raw"], re.I):
            assert annotation["target_path"] is None
        else:
            assert annotation["target_path"]
    sem_inicio(obtained)
    sem_inicio(history)


@pytest.fixture
def acervo_classe(acervo_r2, monkeypatch):
    # A matriz temporal usa modelos imutaveis ja carregados do banco real.
    # Evita reidratar milhares de vezes o mesmo JSON; mantem a revalidacao
    # documental a cada selecao. Os 102 parametros acima usam releitura integral.
    select = acervo_r2._selecionar_camara
    loaded = {}

    def selecionar(work, versao="vigente", fonte=None):
        key = (str(work), versao, fonte)
        if key not in loaded:
            loaded[key] = select(work, versao, fonte)
        rw = loaded[key]
        if rw is not None:
            acervo_r2._revalidar_camara(rw)
        return rw

    monkeypatch.setattr(acervo_r2, "_selecionar_camara", selecionar)
    return acervo_r2


@pytest.mark.parametrize("norm", NORMS)
def test_classe_todos_dispositivos_atualizados(acervo_classe, norm):
    svc = acervo_classe
    rw = svc._resolve(WorkKey("federal", *NORMS[norm]))
    assert rw.document.profile == "camara_atualizado"
    for path in dict.fromkeys(p.path for p in rw.document.provisions):
        citation = cite(norm, path)
        obtained = svc.obter_dispositivo(work_id=rw.work_id, caminho=path)
        assert obtained["vigencia"]["status"] == "unknown", path
        assert obtained["redacao_anterior_ausente_na_fonte"] is True, path
        sem_inicio(obtained)
        history = svc.historico_dispositivo(citation)
        # Se a gramatica de citacao nao representar o caminho, nao ha timeline.
        assert not history.get("linha_do_tempo"), (path, history)
        sem_inicio(history)
        for data in (None, "2025-01-01", "2099-01-01"):
            verified = svc.verificar_citacao(citation, data=data)
            assert verified["temporal"]["status"] not in {"verified", "vigente_na_fonte"}, (path, data)
            sem_inicio(verified)


@pytest.mark.parametrize("data", [None, "2025-01-01", "2099-01-01"])
def test_classe_verificar_texto_e_obtencao_datada(acervo_r2, data):
    citation = "art. 1, caput da Lei 6404/1976"
    for result in (
        acervo_r2.obter_dispositivo(citation, data=data),
        acervo_r2.verificar_citacao(citation, trecho="A companhia ou sociedade anônima", data=data),
        acervo_r2.verificar_texto('Conforme ' + citation + ', "A companhia ou sociedade anônima".', data=data),
    ):
        sem_inicio(result)
        if "citacoes" in result:
            assert result["citacoes"]
            for item in result["citacoes"]:
                assert item["verificacao"]["temporal"]["status"] == "unknown"
        elif "temporal" in result:
            assert result["temporal"]["status"] == "unknown"
        else:
            assert result["vigencia"]["status"] == "unknown"


@pytest.mark.parametrize("norm,path,target,kind", [
    ("lsa", "art17", "art17.caput", "redacao_dada"),
    ("lsa", "art147.par3", None, "incluido"),
    ("lc", "art39", "art39.caput", "redacao_dada"),
])
def test_notas_componentes_preservam_alvo(acervo_r2, norm, path, target, kind):
    for out, field in (
        (acervo_r2.obter_dispositivo(cite(norm, path)), "anotacoes"),
        (acervo_r2.historico_dispositivo(cite(norm, path)), "eventos"),
    ):
        assert any(a["target_path"] == target and a["kind"] == kind for a in out[field])
