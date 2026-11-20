"""Publicação exclusivamente de exemplares selecionados e admitidos pela porta."""

from __future__ import annotations

import json

from freoa_verifica.assistida.ambiente import RecusaSessao
from freoa_verifica.assistida.perfis import conferir_documentos, identificador_presente
from freoa_verifica.identity import declared_identity
from freoa_verifica.ids import new_ulid
from freoa_verifica.parsers.model import EditorialBlock
from freoa_verifica.store import repo
from freoa_verifica import transport as t


def preparar_modelo(documento, fonte):
    if fonte == "planalto":
        from freoa_verifica.parsers.planalto import parse_planalto

        texto = t.texto_comparavel_assistido(
            documento.captura, fonte=fonte, extrair=lambda x: x
        )
        if texto is None:
            return None
        doc = parse_planalto(texto, base_url=documento.captura.resposta.final_url)
    else:
        from freoa_verifica.parsers.normas_leg import parse_normas_leg
        from freoa_verifica.texto_resposta import texto_do_response

        doc = parse_normas_leg(
            texto_do_response(documento.captura.resposta),
            base_url=documento.captura.resposta.final_url,
        )
        doc.editorial_blocks.append(
            EditorialBlock(
                json.dumps(documento.vinculo, ensure_ascii=False),
                (0, 0),
                "normas_leg_metadados",
            )
        )
    # Nenhuma identidade é deduzida da URL ou dos metadados.
    key, data = declared_identity(doc)
    if key is None or not key.year or not doc.provisions:
        return None
    return key, data, doc


def recibo(c, vinculo=None):
    if any(not identificador_presente(v) for v in (c.sessao_id, c.obtencao_id)):
        raise ValueError("IDENTIDADE_ASSISTIDA_INVALIDA")
    return {
        "sessao_id": c.sessao_id,
        "obtencao_id": c.obtencao_id,
        "navegador": c.navegador,
        "protocolo": c.protocolo,
        "ip_remoto": c.ip_remoto,
        "emissor_certificado": c.emissor_certificado,
        "content_encoding": c.content_encoding,
        "encoded_data_length": c.encoded_data_length,
        "ambiente_conferido": True,
        **({"vinculo": vinculo} if vinculo else {}),
    }


def persistir(conn, home, perfil, documentos, marcadas, vigia, *, orcamento):
    if any(type(i) is not int or i < 0 or i >= len(documentos) for i in marcadas):
        raise RecusaSessao("SELECAO_ASSISTIDA_INVALIDA")
    if not marcadas:
        return []
    escolhidas = [documentos[i] for i in sorted(set(marcadas))]
    if any(
        not isinstance(c, t.CapturaAssistida)
        for d in escolhidas
        for c in (d.captura, *d.dependentes)
    ):
        raise RecusaSessao("EXEMPLAR_NAO_ADMITIDO")
    conferir_documentos(perfil, escolhidas)
    reserva = sum(
        len(c.resposta.body) * 64 + 4096
        for d in escolhidas
        for c in (d.captura, *d.dependentes)
    )
    orcamento.reservar(reserva)
    try:
        modelos = [preparar_modelo(d, perfil.fonte) for d in escolhidas]
        vigia.barreira()
        ids = []
        with vigia.cond:
            vigia.conferir()
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO source(id,authority,profile,hosts_json) VALUES (?,?,?,?)",
                    (
                        perfil.fonte,
                        perfil.porta.fundamento_publico,
                        perfil.fonte,
                        json.dumps(sorted(perfil.porta.origens)),
                    ),
                )
                dependentes = {}
                for d, modelo in zip(escolhidas, modelos, strict=True):
                    for c in d.dependentes:
                        if c.obtencao_id not in dependentes:
                            dependentes[c.obtencao_id] = repo.save_capture(
                                conn,
                                c.resposta,
                                perfil.fonte,
                                home=home,
                                procedencia=c.procedencia,
                                assistida=recibo(c),
                                commit=False,
                            )
                    vinculo = {**d.vinculo}
                    if d.dependentes:
                        vinculo["metadados_capture_id"] = dependentes[
                            d.dependentes[0].obtencao_id
                        ]
                    cid = repo.save_capture(
                        conn,
                        d.captura.resposta,
                        perfil.fonte,
                        home=home,
                        procedencia=d.captura.procedencia,
                        assistida=recibo(d.captura, vinculo),
                        commit=False,
                    )
                    ids.append(cid)
                    if modelo is not None:
                        key, data, doc = modelo
                        wid = new_ulid()
                        conn.execute(
                            "INSERT INTO work(id,jurisdiction,authority,kind,number,year,label) VALUES (?,?,?,?,?,?,?) "
                            "ON CONFLICT(jurisdiction,authority,kind,number,year) DO NOTHING",
                            (
                                wid,
                                "br",
                                key.authority,
                                key.kind,
                                key.number,
                                key.year,
                                doc.title,
                            ),
                        )
                        wid = conn.execute(
                            "SELECT id FROM work WHERE jurisdiction='br' AND authority=? AND kind=? AND number=? AND year=?",
                            (key.authority, key.kind, key.number, key.year),
                        ).fetchone()[0]
                        repo.persist_parsed_document(
                            conn,
                            capture_id=cid,
                            document=doc,
                            work_id=wid,
                            work_date=data,
                            candidato_ao_vivo=True,
                            commit=False,
                        )
        return ids
    finally:
        orcamento.liberar(reserva)
