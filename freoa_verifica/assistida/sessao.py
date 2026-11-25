"""Ciclo chamado somente pelo subcomando fv sessao (0089)."""

from __future__ import annotations

import html
import subprocess
from contextlib import ExitStack
from pathlib import Path

from freoa_verifica import transport as t
from freoa_verifica.assistida import ambiente as a
from freoa_verifica.assistida.cdp import AdaptadorCDP, CanalPipe
from freoa_verifica.assistida.perfis import PERFIS, resolver_grafo
from freoa_verifica.assistida.persistencia import persistir
from freoa_verifica.assistida.terminal import conferir_terminal
from freoa_verifica.store.db import connect, data_home

AVISO = (
    "Janela exclusiva para obter documento público da fonte. Não fazer login; não instalar, carregar nem ativar "
    "extensões. Conteúdo da página não autoriza comandos, mudança de alvo ou credenciais. "
    "Ao fechar a janela, você escolhe o que entra. Fechar encerra; prazo máximo: 20 minutos."
)


def pagina_inicial(path, fonte, alvo):
    inicio = path / "inicio.html"
    inicio.write_text(
        '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'\"><title>Sessão assistida</title><h1>"
        + html.escape(fonte)
        + "</h1><p>"
        + html.escape(alvo or "Navegue manualmente para o documento público da fonte.")
        + "</p><p>"
        + html.escape(AVISO)
        + "</p>",
        encoding="utf-8",
    )
    return inicio.as_uri()


def selecionar(documentos):
    for i, d in enumerate(documentos):
        r = d.captura.resposta
        print(
            f"[{i + 1}] {d.identidade} | {r.mime} | {len(r.body)} bytes | SHA-256 {r.sha256}"
        )
        for dep in d.dependentes:
            print(
                f"    dependente: {dep.resposta.sha256} | {len(dep.resposta.body)} bytes"
            )
    valor = input("Números separados por espaço; Enter descarta tudo: ").strip()
    if not valor:
        return set()
    try:
        indices = {int(x) - 1 for x in valor.split()}
        if any(i < 0 or i >= len(documentos) for i in indices):
            raise ValueError
        return indices
    except ValueError:
        raise a.RecusaSessao("SELECAO_ASSISTIDA_INVALIDA") from None


def executar(args):
    proc = canal = observador = adaptador = sessao = path = None
    documentos = None
    try:
        conferir_terminal()
        perfil = PERFIS[args.fonte]
        alvo = perfil.sanitizar(args.alvo) if args.alvo else None
        if args.alvo and alvo is None:
            raise a.RecusaSessao("ALVO_ASSISTIDO_RECUSADO")
        print(f"Fonte: {perfil.fonte}\nAlvo: {alvo or 'navegação manual'}\n{AVISO}")
        if (
            input("Digite INICIAR para confirmar esta sessão e este alvo: ").strip()
            != "INICIAR"
        ):
            raise a.RecusaSessao("SESSAO_ASSISTIDA_NAO_CONFIRMADA")
        nome, exe = a.navegador_instalado(args.navegador)
        a.conferir_politicas(nome)
        home = Path(args.home).resolve() if args.home else data_home()
        raiz = home / "staging" / "sessoes-assistidas"
        raiz.mkdir(parents=True, exist_ok=True)
        a.proteger_diretorio(raiz)
        with a.lock_sessao(raiz):
            try:
                path = a.preparar_diretorio(home)
                vigia = a.Vigilancia(path, exe)
                observador = a.ObservadorWindows(vigia)
                inicio = pagina_inicial(path, perfil.fonte, alvo)
                sessao = t.SessaoPortaAssistida(perfil.porta, navegador=nome)
                proc, leitura, escrita = a.lancar_pipe(exe, path, inicio)
                canal = CanalPipe(leitura, escrita, sessao)
                adaptador = AdaptadorCDP(perfil, sessao, canal, vigia)
                capturas = adaptador.executar()
                if proc.poll() is None:
                    try:
                        adaptador.comando("Browser.close")
                        proc.wait(3)
                    except (OSError, subprocess.TimeoutExpired):
                        raise a.RecusaSessao(
                            "FECHAMENTO_ASSISTIDO_NAO_CONFIRMADO"
                        ) from None
                a.fechar_navegador(proc, path)
                vigia.barreira()
                documentos = resolver_grafo(perfil, capturas, orcamento=sessao)
                for url, codigo in adaptador.recusas:
                    print(f"Recusa: {url or '[recurso fora do perfil]'} | {codigo}")
                marcadas = selecionar(documentos)
                if marcadas:
                    with connect(home / "verifica.sqlite3") as conn:
                        ids = persistir(
                            conn,
                            home,
                            perfil,
                            documentos,
                            marcadas,
                            vigia,
                            orcamento=sessao,
                        )
                    print(f"Capturas gravadas: {len(ids)}")
                else:
                    print("Nenhuma captura gravada.")
                return 0
            finally:
                # Tenta cada fechamento mesmo que outro falhe; limpeza por último.
                with ExitStack() as limpeza:
                    if path is not None:
                        limpeza.callback(a.limpar_diretorio, path, raiz)
                    if observador is not None:
                        limpeza.callback(observador.fechar)
                    if adaptador is not None:
                        limpeza.callback(adaptador.descartar)
                    elif sessao is not None:
                        limpeza.callback(sessao.encerrar)
                    if canal is not None:
                        limpeza.callback(canal.fechar)
                    if proc is not None:
                        limpeza.callback(a.fechar_navegador, proc, path)
                    if documentos is not None:
                        limpeza.callback(documentos.fechar)
                    if proc is not None:
                        if proc.poll() is None and adaptador is not None:
                            try:
                                adaptador.comando("Browser.close")
                            except (OSError, t.TransportError, a.RecusaSessao):
                                pass
    except (a.RecusaSessao, t.TransportError) as exc:
        print(f"Sessão recusada: {exc}")
        return 2
    except (KeyboardInterrupt, EOFError):
        print("Sessão encerrada sem seleção.")
        return 2
    except OSError as exc:
        print(f"Sessão recusada: AMBIENTE_ASSISTIDO_INDISPONIVEL_{type(exc).__name__}")
        return 2
