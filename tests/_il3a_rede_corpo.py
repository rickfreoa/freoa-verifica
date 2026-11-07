"""Corpo dos testes do executor da Porta L que instalam o gancho de auditoria (`sys.addaudithook`).

Não é coletado pela suíte (nome sem prefixo `test_`): roda em UM subprocesso do pytest, disparado por
`test_il3a_rede_subprocesso.py`. O gancho não tem remoção; instalado no processo do pytest contaminaria todos os testes
seguintes. As asserções são as mesmas dos testes que estavam em `test_il3a_executor.py`."""

from __future__ import annotations

import json
import socket

import pytest

from tests.test_il3a_executor import RAIZ, Svc, _conjunto, _montar, caso, ex

def test_bloqueio_de_rede_barra_restaura_e_falha_fechado():
    original = socket.getaddrinfo
    with ex.BloqueioDeRede() as b:
        b.autoteste()
        with pytest.raises(ex.RedeBloqueada):
            socket.create_connection(("example.invalid", 80), timeout=0.1)
        with pytest.raises(ex.RedeBloqueada):
            socket.getaddrinfo("example.invalid", 80)
        with pytest.raises(ex.ViolacaoDeRede):
            b.verificar()
    assert socket.getaddrinfo is original


def test_executar_aborta_se_a_chamada_tentou_rede_mesmo_com_excecao_engolida():
    class S(Svc):
        def obter_dispositivo(self, citacao=None, work_id=None, caminho=None, data=None, versao="vigente", fonte=None):
            try:
                socket.create_connection(("example.invalid", 80), timeout=0.1)
            except OSError:
                pass  # o serviço engole a falha; o executor não
            return {"status": "indisponivel", "motivo": "rede"}
    with ex.BloqueioDeRede() as b:
        with pytest.raises(ex.ViolacaoDeRede):
            ex.executar([caso("L-a-001", "a")], [], S(), "local", bloqueio=b)


def test_cli_modo_local_falha_fechada_em_tentativa_de_rede(tmp_path):
    d, dm, md = _montar(tmp_path, _conjunto("a", 2))

    class S(Svc):
        def obter_dispositivo(self, citacao=None, work_id=None, caminho=None, data=None, versao="vigente", fonte=None):
            try:
                socket.getaddrinfo("example.invalid", 443)
            except OSError:
                pass
            return {"status": "indisponivel"}
    rc = ex.main(["--conjunto", str(d), "--mutantes", str(dm), "--home", str(tmp_path), "--modo", "local",
                  "--saida", str(tmp_path / "s.json"), "--congelamento", str(md), "--sintetico"], _servico=S())
    assert rc == 3 and not (tmp_path / "s.json").exists()


@pytest.mark.repositorio
def test_b4_execucao_qualificante_sobre_o_desenvolvimento_com_a_fachada_real(tmp_path):
    pl = RAIZ / "tests" / "porta_l"
    saida = tmp_path / "rel.json"
    rc = ex.main(["--conjunto", str(pl / "desenvolvimento.jsonl"), "--mutantes", str(pl / "mutantes.jsonl"), "--home",
                  str(tmp_path / "home"), "--modo", "local", "--saida", str(saida)])
    rel = json.loads(saida.read_text(encoding="utf-8"))
    assert rc == 1  # home vazio: nada capturado, tudo indisponível
    assert rel["qualificante"] is True and rel["congelamento"]["normativo"] is True and "aviso" not in rel
    assert rel["rede_bloqueada"] is True and rel["tentativas_de_rede"] == []
    assert rel["confirmacoes_indevidas_total"] == 0
    assert all(c["acertos"] == 0 for c in rel["capacidades"].values())


def test_b5_barra_envio_conexao_e_resolucao_inclusive_em_socket_criado_antes_da_guarda():
    # nenhum soquete do sistema: `__new__` sem `__init__` não cria descritor; os endereços são inválidos
    u = socket.socket.__new__(socket.socket)  # sem descritor: não há o que fechar
    with ex.BloqueioDeRede() as bl:
        acoes = (lambda: u.sendto(b"x", ("127.0.0.1", 9)), lambda: u.connect(("127.0.0.1", 9)),
                 lambda: u.connect_ex(("127.0.0.1", 9)), lambda: u.send(b"x"), lambda: u.sendall(b"x"),
                 lambda: socket.gethostbyname("example.invalid"), lambda: socket.gethostbyaddr("127.0.0.1"),
                 lambda: socket.getnameinfo(("127.0.0.1", 9), 0))
        for acao in acoes:
            with pytest.raises(ex.RedeBloqueada):
                acao()
        assert len(bl.tentativas) >= 8
        with pytest.raises(ex.ViolacaoDeRede):
            bl.verificar()


def test_r2_4_tipo_c_socket_do_modulo__socket_esta_sob_a_guarda():
    import _socket
    original = _socket.socket
    metodos = [m for m in ("connect", "connect_ex", "send", "sendall", "sendto") if hasattr(original, m)]
    assert metodos == ["connect", "connect_ex", "send", "sendall", "sendto"]
    with ex.BloqueioDeRede() as bl:
        assert _socket.socket is not original
        s = _socket.socket.__new__(_socket.socket)  # sem `__init__`: nenhum soquete do sistema
        try:
            # o controle do auditor: endereço inválido faria a primitiva C falhar com TypeError, sem a guarda
            with pytest.raises(ex.RedeBloqueada):
                s.sendto(b"x", object())
            for m in ("connect", "connect_ex"):
                with pytest.raises(ex.RedeBloqueada):
                    getattr(s, m)(object())
            for m in ("send", "sendall"):
                with pytest.raises(ex.RedeBloqueada):
                    getattr(s, m)(b"x")
        finally:
            s.close()
        assert len(bl.tentativas) == 5 and all(t.startswith("_socket.socket.") for t in bl.tentativas)
        with pytest.raises(ex.ViolacaoDeRede):
            bl.verificar()
    assert _socket.socket is original  # restaurado
    s = _socket.socket.__new__(_socket.socket)
    with pytest.raises((TypeError, OSError)) as exc:  # fora da guarda a primitiva C é a de verdade (falha antes de enviar)
        s.sendto(b"x", object())
    assert not isinstance(exc.value, ex.RedeBloqueada)


def test_b5_restaura_o_que_herdava_do_tipo_base_sem_fixar_copia():
    antes = "sendto" in vars(socket.socket)
    envio = socket.socket.send
    with ex.BloqueioDeRede():
        pass
    assert ("sendto" in vars(socket.socket)) == antes
    assert socket.socket.send is envio and socket.getaddrinfo.__module__ != ex.__name__


PRIMITIVAS = [("socket", n) for n in ("sendto", "send", "sendall", "connect", "connect_ex")] + [
    ("modulo", n) for n in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr",
                             "getnameinfo")] + [
    ("_socket_tipo", n) for n in ("sendto", "send", "sendall", "connect", "connect_ex", "sendmsg")] + [
    ("_socket_modulo", n) for n in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")]


def _alvo_da_primitiva(onde):
    import _socket
    return {"socket": socket.socket, "modulo": socket, "_socket_tipo": _socket.socket, "_socket_modulo": _socket}[onde]


@pytest.mark.parametrize("onde,nome", PRIMITIVAS)
def test_b5_autoteste_falha_se_qualquer_primitiva_escapar(onde, nome):
    """Cada entrada protegida, uma a uma, volta a escapar (sentinela em memória): o autoteste falha e a nomeia."""
    def escapou(*a, **k):
        raise OSError("escapou do bloqueio")  # sentinela em memória: nenhuma saída real
    with ex.BloqueioDeRede() as b:
        b.autoteste()  # íntegro
        alvo = _alvo_da_primitiva(onde)  # dentro da guarda: `_socket.socket` é o tipo guardado (mutável)
        if not hasattr(alvo, nome):
            pytest.skip("primitiva inexistente nesta plataforma")
        setattr(alvo, nome, escapou)  # a primitiva volta a escapar da barreira
        with pytest.raises(ex.ViolacaoDeRede) as exc:
            b.autoteste()
        assert nome in str(exc.value)
        if onde.startswith("_socket"):
            assert "_socket" in str(exc.value)


def test_b5_autoteste_falha_se_a_primitiva_nao_levanta_nada():
    with ex.BloqueioDeRede() as b:
        socket.socket.sendto = lambda self, *a, **k: 0  # "enviaria" sem levantar
        with pytest.raises(ex.ViolacaoDeRede):
            b.autoteste()


class _FalsoVerifica:
    """Substituto de `Verifica` que tenta a rede onde o teste mandar (e engole a falha)."""
    onde: str = ""

    def __init__(self, home=None):
        if self.onde == "construcao":
            self._tenta()

    @staticmethod
    def _tenta():
        try:
            socket.getaddrinfo("example.invalid", 443)
        except OSError:
            pass

    def obter_dispositivo(self, citacao=None, work_id=None, caminho=None, data=None, versao="vigente", fonte=None):
        if self.onde == "uso":
            self._tenta()
        return {"status": "indisponivel"}

    def close(self):
        if self.onde == "fechamento":
            self._tenta()


@pytest.mark.parametrize("onde", ["construcao", "uso", "fechamento"])
def test_b5_ciclo_completo_do_servico_esta_sob_o_bloqueio(tmp_path, monkeypatch, onde):
    import freoa_verifica.service as fachada
    d, dm, md = _montar(tmp_path, _conjunto("a", 2))
    monkeypatch.setattr(fachada, "Verifica", type("Falso", (_FalsoVerifica,), {"onde": onde}))
    rc = ex.main(["--conjunto", str(d), "--mutantes", str(dm), "--home", str(tmp_path), "--modo", "local",
                  "--saida", str(tmp_path / "s.json"), "--congelamento", str(md), "--sintetico"])
    assert rc == 3 and not (tmp_path / "s.json").exists()  # falha fechada, sem relatório


def test_b5_modo_local_sem_tentativa_nenhuma_registra_rede_bloqueada(tmp_path, monkeypatch):
    import freoa_verifica.service as fachada
    d, dm, md = _montar(tmp_path, _conjunto("a", 2))
    monkeypatch.setattr(fachada, "Verifica", type("Falso", (_FalsoVerifica,), {"onde": ""}))
    rc = ex.main(["--conjunto", str(d), "--mutantes", str(dm), "--home", str(tmp_path), "--modo", "local",
                  "--saida", str(tmp_path / "s.json"), "--congelamento", str(md), "--sintetico"])
    rel = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert rc == 1 and rel["rede_bloqueada"] is True and rel["tentativas_de_rede"] == []
