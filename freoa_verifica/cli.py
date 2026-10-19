"""CLI `fv` — espelho 1:1 da fachada de serviço."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from freoa_verifica import __version__
from freoa_verifica.service import Verifica


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write((text + "\n").encode(enc, errors="replace"))


def _print_result(data: Any, *, as_json: bool, titulo: str | None = None) -> int:
    if as_json:
        _safe_print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if titulo:
        _safe_print(titulo)
        _safe_print("-" * len(titulo))
    _print_humano(data)
    return 0


def _print_humano(data: Any, indent: int = 0) -> None:
    pad = "  " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                _safe_print(f"{pad}{k}:")
                _print_humano(v, indent + 1)
            else:
                _safe_print(f"{pad}{k}: {v}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _safe_print(f"{pad}- [{i}]")
            _print_humano(item, indent + 1)
    else:
        _safe_print(f"{pad}{data}")


def _read_texto(path: str | None) -> str:
    if path and path != "-":
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def _add_json_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="saída em JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fv",
        description="FREOA Verifica — verificação de citações contra fontes oficiais",
    )
    parser.add_argument("--version", action="version", version=f"freoa-verifica {__version__}")
    parser.add_argument(
        "--home",
        default=None,
        help="diretório de dados (padrão: FV_HOME ou pasta do sistema)",
    )
    parser.add_argument(
        "--sem-registro",
        action="store_true",
        help="registro sem_conteudo (já é o padrão desde a 1.2.0; mantida por compatibilidade)",
    )
    parser.add_argument(
        "--registro-completo",
        action="store_true",
        help="grava citação, trecho e evidência textual nas execuções (padrão: sem_conteudo; também FV_REGISTRO=completo)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("busca", help="buscar legislação")
    p.add_argument("q")
    p.add_argument("--fonte")
    p.add_argument("--data")
    p.add_argument("--limite", type=int, default=10)
    p.add_argument("--cursor")
    _add_json_flag(p)

    p = sub.add_parser("lei", help="obter dispositivo (texto da redação)")
    p.add_argument("citacao", nargs="?")
    p.add_argument("--work-id")
    p.add_argument("--caminho")
    p.add_argument("--data")
    _add_json_flag(p)

    p = sub.add_parser("resolve", help="resolver citação (work_id e caminho)")
    p.add_argument("citacao")
    _add_json_flag(p)

    p = sub.add_parser("historico", help="histórico temporal do dispositivo")
    p.add_argument("citacao")
    _add_json_flag(p)

    p = sub.add_parser("verifica", help="verificar citação")
    p.add_argument("citacao")
    p.add_argument("--trecho")
    p.add_argument("--data")
    p.add_argument("--modo", default="literal")
    p.add_argument("--proposicao")
    _add_json_flag(p)

    p = sub.add_parser("verifica-texto", help="extrair e verificar citações de um texto")
    p.add_argument("arquivo", nargs="?", help="arquivo ou - para stdin")
    p.add_argument("--data")
    _add_json_flag(p)

    p = sub.add_parser("juris", help="pesquisar jurisprudência")
    p.add_argument("q")
    p.add_argument("--tribunais", nargs="*")
    p.add_argument("--desde")
    p.add_argument("--ate")
    p.add_argument("--autoridade-min")
    p.add_argument("--limite", type=int, default=10)
    p.add_argument("--cursor")
    _add_json_flag(p)

    p = sub.add_parser("decisao", help="obter texto de decisão")
    p.add_argument("id")
    p.add_argument("--parte", default="ementa")
    p.add_argument("--max-chars", type=int, default=8000)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--tribunal", default=None, help="tribunal do identificador oficial (desfaz colisões)")
    _add_json_flag(p)

    p = sub.add_parser("cvm", help="buscar normas CVM")
    p.add_argument("q")
    p.add_argument("--tipo")
    _add_json_flag(p)

    p = sub.add_parser("bcb", help="buscar normas BCB/CMN")
    p.add_argument("q")
    p.add_argument("--tipo")
    _add_json_flag(p)

    p = sub.add_parser("evidencia", help="obter evidência de captura")
    p.add_argument("capture_id")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--max-chars", type=int, default=4000)
    _add_json_flag(p)

    p = sub.add_parser("fontes", help="listar fontes e saúde")
    _add_json_flag(p)

    p = sub.add_parser("sync", help="sincronizar índices/listas (não disponível via MCP)")
    p.add_argument("fontes", nargs="*")
    p.add_argument("--desde")
    p.add_argument("--semente", action="store_true", help="sincronizar corpus semente")
    p.add_argument("--fontes", dest="fontes_flag", nargs="*", help="filtrar fontes (semente)")
    p.add_argument("--max-itens", type=int, default=None, help="limite por fonte; STJ: por recurso mensal")
    _add_json_flag(p)

    p = sub.add_parser("bench", help="benchmark contra gold.jsonl")
    p.add_argument("--gold", required=True, help="caminho do gold.jsonl")
    p.add_argument("--saida", default=None, help="diretório para bench-report.json e .md")
    _add_json_flag(p)

    p = sub.add_parser("doctor", help="verificar instalação, banco e rede")
    p.add_argument("--offline", action="store_true")
    _add_json_flag(p)

    p = sub.add_parser("serve-mcp", help="iniciar servidor MCP")
    p.add_argument("--http", action="store_true")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default=None, help="bearer (obrigatório com host não local)")

    p = sub.add_parser("serve-api", help="iniciar API REST")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--token", default=None)

    p = sub.add_parser("snapshot", help="exportar/instalar snapshot de corpus")
    snap = p.add_subparsers(dest="snap_cmd", required=True)
    pe = snap.add_parser("export")
    pe.add_argument("destino", nargs="?", default=None)
    pe.add_argument("--arquivo-unico", action="store_true", help="gerar tar.gz e checksum externo")
    pe.add_argument("--saida", default=None, help="diretório de saída (alternativa ao destino posicional)")
    _add_json_flag(pe)
    pi = snap.add_parser("install")
    pi.add_argument("origem", nargs="?", default=None)
    pi.add_argument("--arquivo", default=None, help="caminho local do snapshot")
    pi.add_argument("--url", default=None, help="URL de asset de release GitHub")
    pi.add_argument("--aceitar-nao-vinculado", action="store_true")
    _add_json_flag(pi)
    pf = snap.add_parser("info")
    pf.add_argument("origem", nargs="?")
    _add_json_flag(pf)

    p = sub.add_parser("acervo", help="manutenção do acervo local")
    ac = p.add_subparsers(dest="acervo_cmd", required=True)
    ps = ac.add_parser("ressincronizar-situacao", help="relê a situação cadastral dos atos CVM/BCB/CMN (C2)")
    _add_json_flag(ps)
    pr = ac.add_parser("reconstruir", help="reconstrói os derivados do home numa cópia e troca o banco (C6)")
    pr.add_argument("--com-situacao", action="store_true", help="relê também a situação das obras (exige rede)")
    _add_json_flag(pr)

    p = sub.add_parser("runs", help="gerenciar execuções registradas")
    runs = p.add_subparsers(dest="runs_cmd", required=True)
    pp = runs.add_parser("purgar", help="reconstruir o banco sem execuções anteriores a DATA")
    pp.add_argument("--antes", required=True, metavar="DATA", help="AAAA-MM-DD")
    pp.add_argument("--apagar-original", action="store_true",
                    help="apaga o banco original (movido para purgados/) após a troca bem-sucedida; sem a opção, o original fica para exclusão manual")
    _add_json_flag(pp)

    return parser


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "json", False))
    if args.sem_registro and args.registro_completo:
        parser.error("--sem-registro e --registro-completo são excludentes")
    registro = "completo" if args.registro_completo else ("sem_conteudo" if args.sem_registro else None)

    if args.cmd == "serve-mcp":
        from freoa_verifica.mcp_server import run_server

        run_server(http=args.http, host=args.host, port=args.port, home=args.home,
                   token=args.token, registro=registro)
        return

    if args.cmd == "serve-api":
        from freoa_verifica.rest import run_api

        run_api(host=args.host, port=args.port, token=args.token, home=args.home, registro=registro)
        return

    with Verifica(home=args.home, registro=registro) as svc:
        if args.cmd == "runs":
            data = svc.purgar_execucoes(args.antes, apagar_original=args.apagar_original)
            _print_result(data, as_json=as_json, titulo="Purga de execuções")
            raise SystemExit(0 if data.get("status") == "ok" else 1)

        if args.cmd == "busca":
            data = svc.buscar_legislacao(
                args.q, fonte=args.fonte, data=args.data, limite=args.limite, cursor=args.cursor
            )
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Busca de legislação"))

        if args.cmd == "lei":
            data = svc.obter_dispositivo(
                citacao=args.citacao,
                work_id=args.work_id,
                caminho=args.caminho,
                data=args.data,
            )
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Dispositivo"))

        if args.cmd == "resolve":
            data = svc.resolver_citacao(args.citacao)
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Resolução"))

        if args.cmd == "historico":
            data = svc.historico_dispositivo(args.citacao)
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Histórico"))

        if args.cmd == "verifica":
            data = svc.verificar_citacao(
                args.citacao,
                trecho=args.trecho,
                data=args.data,
                modo=args.modo,
                proposicao=args.proposicao,
            )
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Verificação"))

        if args.cmd == "verifica-texto":
            texto = _read_texto(args.arquivo)
            data = svc.verificar_texto(texto, data=args.data)
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Verificação de texto"))

        if args.cmd == "juris":
            data = svc.pesquisar_jurisprudencia(
                args.q,
                tribunais=args.tribunais,
                desde=args.desde,
                ate=args.ate,
                autoridade_min=args.autoridade_min,
                limite=args.limite,
                cursor=args.cursor,
            )
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Jurisprudência"))

        if args.cmd == "decisao":
            data = svc.obter_decisao(
                args.id, parte=args.parte, max_chars=args.max_chars, offset=args.offset,
                tribunal=args.tribunal,
            )
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Decisão"))

        if args.cmd == "cvm":
            data = svc.buscar_normas_cvm(args.q, tipo=args.tipo)
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Normas CVM"))

        if args.cmd == "bcb":
            data = svc.buscar_normas_bcb(args.q, tipo=args.tipo)
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Normas BCB"))

        if args.cmd == "evidencia":
            data = svc.obter_evidencia(
                args.capture_id, offset=args.offset, max_chars=args.max_chars
            )
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Evidência"))

        if args.cmd == "fontes":
            data = svc.listar_fontes()
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Fontes"))

        if args.cmd == "sync":
            fontes = getattr(args, "fontes_flag", None) or args.fontes or None
            data = svc.sincronizar(
                fontes=fontes,
                desde=args.desde,
                semente=bool(getattr(args, "semente", False)),
                max_itens=getattr(args, "max_itens", None),
            )
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Sincronização"))

        if args.cmd == "bench":
            from freoa_verifica.bench import markdown_table

            data = svc.bench(args.gold)
            saida = getattr(args, "saida", None)
            if saida:
                out = Path(saida)
                out.mkdir(parents=True, exist_ok=True)
                (out / "bench-report.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                (out / "bench-report.md").write_text(
                    markdown_table(data), encoding="utf-8"
                )
                data = {**data, "relatorios": {"json": str(out / "bench-report.json"), "md": str(out / "bench-report.md")}}
            if as_json:
                raise SystemExit(_print_result(data, as_json=True))
            _safe_print(markdown_table(data))
            raise SystemExit(0 if data.get("status") == "ok" else 1)

        if args.cmd == "doctor":
            data = svc.doctor(offline=args.offline)
            code = 0 if data.get("status") == "ok" else 1
            _print_result(data, as_json=as_json, titulo="Diagnóstico")
            raise SystemExit(code)

        if args.cmd == "snapshot":
            if args.snap_cmd == "export":
                dest = args.saida or args.destino
                if not dest:
                    parser.error("snapshot export exige destino ou --saida")
                if args.arquivo_unico:
                    if not str(dest).endswith(".tar.gz"):
                        parser.error("--arquivo-unico exige destino com extensão .tar.gz")
                data = svc.snapshot_export(dest)
            elif args.snap_cmd == "install":
                arquivo = args.arquivo or args.origem
                data = svc.snapshot_install(arquivo, url=args.url, aceitar_nao_vinculado=args.aceitar_nao_vinculado)
            else:
                data = svc.snapshot_info(args.origem)
            raise SystemExit(_print_result(data, as_json=as_json, titulo="Snapshot"))

        if args.cmd == "acervo":
            if args.acervo_cmd == "ressincronizar-situacao":
                data = svc.ressincronizar_situacao()
                raise SystemExit(_print_result(data, as_json=as_json, titulo="Situação das obras"))
            if args.acervo_cmd == "reconstruir":
                data = svc.reconstruir_acervo(com_situacao=args.com_situacao)
                _print_result(data, as_json=as_json, titulo="Reconstrução do acervo")
                raise SystemExit(0 if data.get("status") == "ok" else 1)

    parser.error(f"comando desconhecido: {args.cmd}")


if __name__ == "__main__":
    main()
