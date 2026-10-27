"""A consulta paginada do acervo STJ mantém o valor exato da 1.3.0 (troca de ignore por noqa, plano 1.4.0, I1.3)."""

from freoa_verifica.connectors import stj

_SQL_130 = (
    "\n                SELECT key, title, ementa, organ, rapporteur, decision_date, class_name, payload"
    "\n                FROM fts_stj WHERE __WHERE__ LIMIT ?\n                "
)


def test_sql_paginada_identica_a_130():
    assert stj._SQL_PAGINA_PREFIXO + "__WHERE__" + stj._SQL_PAGINA_SUFIXO == _SQL_130
