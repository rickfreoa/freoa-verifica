"""Oráculos textuais: caput completo vs fixture bruto (semente 20261017)."""

from __future__ import annotations

import re

from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.parsers.planalto import parse_planalto
from tests.fixture_util import load_fixture

# Semente 20261017 — dez caputs por instrumento (auditoria M2).
_LSA_ARTS = [159, 24, 245, 109, 76, 272, 293, 296, 292, 186]
_CC_ARTS = [1204, 362, 980, 1905, 2015, 1052, 814, 1128, 1155, 177]
_RCVM160_ARTS = [32, 100, 33, 30, 42, 50, 67, 82, 27, 10]

# Texto completo do caput (sem notas), colapsado — copiado do fixture bruto.
_LSA_EXPECTED = {
    159: (
        "Compete à companhia, mediante prévia deliberação da assembléia-geral, "
        "a ação de responsabilidade civil contra o administrador, pelos "
        "prejuízos causados ao seu patrimônio."
    ),
    24: (
        "Os certificados das ações serão escritos em vernáculo e conterão "
        "as seguintes declarações:"
    ),
    245: (
        "Os administradores não podem, em prejuízo da companhia, favorecer "
        "sociedade coligada, controladora ou controlada, cumprindo-lhes zelar "
        "para que as operações entre as sociedades, se houver, observem "
        "condições estritamente comutativas, ou com pagamento compensatório "
        "adequado; e respondem perante a companhia pelas perdas e danos "
        "resultantes de atos praticados com infração ao disposto neste artigo."
    ),
    109: (
        "Nem o estatuto social nem a assembléia-geral poderão privar o "
        "acionista dos direitos de:"
    ),
    76: (
        "A deliberação sobre emissão de bônus de subscrição compete à "
        "assembléia-geral, se o estatuto não a atribuir ao conselho de "
        "administração."
    ),
    272: (
        "A convenção deve definir a estrutura administrativa do grupo de "
        "sociedades, podendo criar órgãos de deliberação colegiada e cargos "
        "de direção-geral."
    ),
    293: (
        "A Comissão de Valores Mobiliários poderá autorizar as bolsas de "
        "valores e outras entidades, que sejam ou não instituições "
        "financeiras, a prestar os serviços previstos nos seguintes "
        "dispositivos desta Lei:"
    ),
    296: (
        "As companhias existentes deverão proceder à adaptação do seu "
        "estatuto aos preceitos desta Lei no prazo de 1 (um) ano a contar "
        "da data em que ela entrar em vigor, devendo para esse fim ser "
        "convocada assembléia-geral dos acionistas."
    ),
    292: (
        "As sociedades de que trata o artigo 62 da Lei n. 4.728, de 14 de "
        "julho de 1965, podem ter suas ações ao portador."
    ),
    186: "A demonstração de lucros ou prejuízos acumulados discriminará:",
}

_CC_EXPECTED = {
    1204: (
        "Adquire-se a posse desde o momento em que se torna possível o "
        "exercício, em nome próprio, de qualquer dos poderes inerentes à "
        "propriedade."
    ),
    362: (
        "A novação por substituição do devedor pode ser efetuada "
        "independentemente de consentimento deste."
    ),
    980: (
        "A sentença que decretar ou homologar a separação judicial do "
        "empresário e o ato de reconciliação não podem ser opostos a "
        "terceiros, antes de arquivados e averbados no Registro Público de "
        "Empresas Mercantis."
    ),
    1905: (
        "Se o testador nomear certos herdeiros individualmente e outros "
        "coletivamente, a herança será dividida em tantas quotas quantos "
        "forem os indivíduos e os grupos designados."
    ),
    2015: (
        "Se os herdeiros forem capazes, poderão fazer partilha amigável, "
        "por escritura pública, termo nos autos do inventário, ou escrito "
        "particular, homologado pelo juiz."
    ),
    1052: (
        "Na sociedade limitada, a responsabilidade de cada sócio é restrita "
        "ao valor de suas quotas, mas todos respondem solidariamente pela "
        "integralização do capital social."
    ),
    814: (
        "As dívidas de jogo ou de aposta não obrigam a pagamento; mas não se "
        "pode recobrar a quantia, que voluntariamente se pagou, salvo se foi "
        "ganha por dolo, ou se o perdente é menor ou interdito."
    ),
    1128: (
        "O requerimento de autorização de sociedade nacional deve ser "
        "acompanhado de cópia do contrato, assinada por todos os sócios, "
        "ou, tratando-se de sociedade anônima, de cópia, autenticada pelos "
        "fundadores, dos documentos exigidos pela lei especial."
    ),
    1155: (
        "Considera-se nome empresarial a firma ou a denominação adotada, "
        "de conformidade com este Capítulo, para o exercício de empresa."
    ),
    177: (
        "A anulabilidade não tem efeito antes de julgada por sentença, nem "
        "se pronuncia de ofício; só os interessados a podem alegar, e "
        "aproveita exclusivamente aos que a alegarem, salvo o caso de "
        "solidariedade ou indivisibilidade."
    ),
}

_RCVM160_EXPECTED = {
    32: (
        "A condução da análise reservada prevista no art. 31 somente é "
        "possível se solicitada simultaneamente com o protocolo inicial do "
        "requerimento de registro da oferta pública de distribuição."
    ),
    100: (
        "Esta Resolução entra em vigor em 2 de janeiro de 2023, observado, "
        "em relação às revogações referidas nos arts. 98 e 99, o disposto "
        "no parágrafo único deste artigo."
    ),
    33: (
        "As entidades administradoras de mercados organizados em que são "
        "admitidas à negociação os valores mobiliários objeto da oferta "
        "pública de distribuição também devem adotar procedimentos para "
        "garantir o sigilo do pedido de análise de registro da oferta pública."
    ),
    30: "A SRE pode, a qualquer tempo:",
    42: (
        "A aprovação do prospecto e do registro da oferta pública de "
        "distribuição não implica, por parte da CVM, garantia quanto ao "
        "conteúdo das informações prestadas ou julgamento sobre a qualidade "
        "do emissor, sua viabilidade, sua administração e sua situação "
        "econômico-financeira, bem como quanto à qualidade dos ativos a "
        "serem distribuídos, e é concedido segundo critérios formais de "
        "legalidade."
    ),
    50: (
        "A quantidade de valores mobiliários a ser distribuída pode, a "
        "critério do ofertante e sem a necessidade de novo requerimento de "
        "registro ou de modificação dos termos da oferta, ser aumentada, "
        "até um montante que não exceda em 25% (vinte e cinco por cento) a "
        "quantidade inicialmente requerida (lote adicional), excluído o "
        "eventual lote suplementar de que trata o art. 51."
    ),
    67: (
        "Havendo, a juízo da CVM, alteração substancial, posterior e "
        "imprevisível nas circunstâncias de fato existentes quando do "
        "protocolo do requerimento de registro de oferta pública de "
        "distribuição, ou que o fundamentem, a SRE pode:"
    ),
    82: (
        "O coordenador líder, os demais coordenadores e as demais "
        "instituições participantes do consórcio de distribuição devem "
        "zelar para que as informações divulgadas e a alocação da oferta "
        "não privilegiem pessoas vinculadas, em detrimento de pessoas não "
        "vinculadas."
    ),
    27: (
        "Os seguintes documentos e condições são exigidos para requerimento "
        "e concessão do registro da oferta pública de distribuição que "
        "siga o rito automático:"
    ),
    10: (
        "Considera-se que foi dada publicidade a uma oferta quando for "
        "promovido, por qualquer meio ou forma, ato de comunicação que "
        "busque despertar interesse na subscrição ou na aquisição de "
        "determinados valores mobiliários ofertados ou a serem ofertados."
    ),
}


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def test_oracle_lsa_caputs():
    doc = parse_planalto(load_fixture("planalto_lei_6404_1976"))
    for n in _LSA_ARTS:
        got = _collapse(doc.current_text(f"art{n}") or "")
        assert got == _collapse(_LSA_EXPECTED[n]), (n, got[:80], _LSA_EXPECTED[n][:80])


def test_oracle_cc_caputs():
    doc = parse_planalto(load_fixture("planalto_lei_10406_2002"))
    for n in _CC_ARTS:
        got = _collapse(doc.current_text(f"art{n}") or "")
        assert got == _collapse(_CC_EXPECTED[n]), (n, got[:80], _CC_EXPECTED[n][:80])


def test_oracle_rcvm160_caputs():
    doc = parse_cvm_docx(load_fixture("cvm_resol_160_consolid_docx"))
    for n in _RCVM160_ARTS:
        got = _collapse(doc.current_text(f"art{n}") or "")
        assert not got.startswith("."), (n, got[:40])
        assert got == _collapse(_RCVM160_EXPECTED[n]), (
            n,
            got[:80],
            _RCVM160_EXPECTED[n][:80],
        )
