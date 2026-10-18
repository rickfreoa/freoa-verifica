"""API REST /v1 (extra `server`: fastapi + uvicorn)."""

from __future__ import annotations

import hmac
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr

from freoa_verifica.limites import MAX_CORPO_HTTP, EntradaInvalida, Sobrecarga
from freoa_verifica.service import Verifica

try:
    from fastapi import Depends, FastAPI, HTTPException, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from starlette.exceptions import HTTPException as StarletteHTTPException
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore

_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _problem(status: int, title: str, detail: str, type_: str = "about:blank") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": type_, "title": title, "status": status, "detail": detail},
        media_type="application/problem+json",
    )


class _CorpoGrande(Exception):
    pass


class _LimiteCorpo:
    """Recusa corpo acima do teto: por Content-Length e cortando a leitura em streaming."""

    def __init__(self, app: Any, limite: int = MAX_CORPO_HTTP) -> None:
        self.app, self.limite = app, limite

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        resp = _problem(413, "erro", "corpo da requisição excede o limite")
        declared = dict(scope["headers"]).get(b"content-length")
        try:
            if declared is not None and int(declared) > self.limite:
                return await resp(scope, receive, send)
        except ValueError:
            return await _problem(400, "erro", "Content-Length inválido")(scope, receive, send)
        total = 0
        excedeu = False
        respondeu = False

        async def counted() -> Any:
            nonlocal total, excedeu
            msg = await receive()
            if msg["type"] == "http.request":
                total += len(msg.get("body", b""))
                if total > self.limite:
                    excedeu = True
                    raise _CorpoGrande
            return msg

        async def watch(msg: Any) -> None:
            # O framework pode traduzir a leitura cortada em 400: troca por 413.
            nonlocal respondeu
            if excedeu:
                if not respondeu:
                    respondeu = True
                    await resp(scope, receive, send)
                return
            await send(msg)

        try:
            await self.app(scope, counted, watch)
        except _CorpoGrande:
            if not respondeu:
                await resp(scope, receive, send)


class _VerificacaoIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    citacao: StrictStr = ""
    trecho: StrictStr | None = None
    data: StrictStr | None = None
    modo: StrictStr | None = None
    proposicao: StrictStr | None = None


class _TextoIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    texto: StrictStr = ""
    data: StrictStr | None = None


def create_app(
    home: str | None = None,
    token: str | None = None,
    *,
    modo: str = "local",
    registro: str | None = None,
) -> Any:
    """Fábrica ASGI. `modo`: "local" (sem token só aceita origem loopback) ou
    "remoto" (token obrigatório). Sem token em modo remoto, a fábrica recusa subir."""
    if FastAPI is None:
        raise RuntimeError(
            "fastapi não instalado; instale o extra: pip install 'freoa-verifica[server]'"
        )
    if modo not in ("local", "remoto"):
        raise ValueError("modo deve ser 'local' ou 'remoto'")
    expected = token if token is not None else os.environ.get("FV_API_TOKEN")
    if modo == "remoto" and not expected:
        raise RuntimeError("recusado: modo remoto exige token (--token ou FV_API_TOKEN)")

    svc = Verifica(home=home, registro=registro, exigir_acervo=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        svc.close()

    app = FastAPI(
        title="FREOA Verifica",
        version="1.0.0.dev0",
        description="Verificação de citações jurídicas contra fontes oficiais",
        lifespan=lifespan,
    )
    app.state.verifica = svc
    bearer = HTTPBearer(auto_error=False)

    def require_auth(
        creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> None:
        if not expected:
            return
        if creds is None or creds.scheme.lower() != "bearer" or creds.credentials != expected:
            raise HTTPException(status_code=401, detail="token inválido ou ausente")

    @app.middleware("http")
    async def fronteira(request: Request, call_next):
        # Vale para toda rota (inclusive as desconhecidas), não só as com Depends.
        if expected:
            auth = request.headers.get("authorization", "")
            scheme, _, cred = auth.partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(cred.strip(), expected):
                return _problem(401, "erro", "token inválido ou ausente")
        else:
            host = request.client.host if request.client else None
            proxied = "x-forwarded-for" in request.headers or "forwarded" in request.headers
            if host not in _LOCAL_HOSTS or proxied:
                return _problem(401, "erro", "sem token, apenas origem local direta é aceita")
        return await call_next(request)

    @app.exception_handler(EntradaInvalida)
    async def entrada_invalida(request: Request, exc: EntradaInvalida):
        return _problem(422, "entrada_invalida", str(exc))

    @app.exception_handler(Sobrecarga)
    async def sobrecarga(request: Request, exc: Sobrecarga):
        return _problem(503, "sobrecarga", "serviço ocupado; tente novamente")

    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        detail = "não encontrado" if exc.status_code == 404 else "erro na requisição"
        if exc.status_code == 401:
            detail = "token inválido ou ausente"
        elif exc.status_code == 422:
            detail = "parâmetros inválidos"
        return _problem(exc.status_code, "erro", detail)

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _problem(404, "erro", "não encontrado")
        if exc.status_code == 422:
            return _problem(422, "erro", "parâmetros inválidos")
        return _problem(exc.status_code, "erro", "erro na requisição")

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return _problem(422, "erro", "parâmetros inválidos")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        return _problem(500, "erro_interno", "erro interno")

    @app.get("/v1/legislacao")
    def get_legislacao(
        q: str,
        fonte: str | None = None,
        data: str | None = None,
        limite: int = 10,
        cursor: str | None = None,
        _: None = Depends(require_auth),
    ):
        return svc.buscar_legislacao(q, fonte=fonte, data=data, limite=limite, cursor=cursor)

    @app.get("/v1/citacoes/resolver")
    def get_resolver(citacao: str, _: None = Depends(require_auth)):
        return svc.resolver_citacao(citacao)

    @app.get("/v1/dispositivos")
    def get_dispositivo(
        citacao: str | None = None,
        work_id: str | None = None,
        caminho: str | None = None,
        data: str | None = None,
        _: None = Depends(require_auth),
    ):
        return svc.obter_dispositivo(
            citacao=citacao, work_id=work_id, caminho=caminho, data=data
        )

    @app.get("/v1/dispositivos/historico")
    def get_historico(citacao: str, _: None = Depends(require_auth)):
        return svc.historico_dispositivo(citacao)

    @app.post("/v1/verificacoes")
    def post_verificacao(body: _VerificacaoIn, _: None = Depends(require_auth)):
        return svc.verificar_citacao(
            body.citacao,
            trecho=body.trecho,
            data=body.data,
            modo=body.modo or "literal",
            proposicao=body.proposicao,
        )

    @app.post("/v1/verificacoes/texto")
    def post_verificacao_texto(body: _TextoIn, _: None = Depends(require_auth)):
        return svc.verificar_texto(body.texto, data=body.data)

    @app.get("/v1/jurisprudencia")
    def get_juris(
        q: str,
        tribunais: str | None = None,
        desde: str | None = None,
        ate: str | None = None,
        autoridade_min: str | None = None,
        limite: int = 10,
        cursor: str | None = None,
        _: None = Depends(require_auth),
    ):
        trib = [t.strip() for t in tribunais.split(",")] if tribunais else None
        return svc.pesquisar_jurisprudencia(
            q,
            tribunais=trib,
            desde=desde,
            ate=ate,
            autoridade_min=autoridade_min,
            limite=limite,
            cursor=cursor,
        )

    @app.get("/v1/decisoes/{id}")
    def get_decisao(
        id: str,
        parte: str = "ementa",
        max_chars: int = 8000,
        offset: int = 0,
        _: None = Depends(require_auth),
    ):
        return svc.obter_decisao(id, parte=parte, max_chars=max_chars, offset=offset)

    @app.get("/v1/normas/cvm")
    def get_cvm(q: str, tipo: str | None = None, _: None = Depends(require_auth)):
        return svc.buscar_normas_cvm(q, tipo=tipo)

    @app.get("/v1/normas/bcb")
    def get_bcb(q: str, tipo: str | None = None, _: None = Depends(require_auth)):
        return svc.buscar_normas_bcb(q, tipo=tipo)

    @app.get("/v1/evidencias/{capture_id}")
    def get_evidencia(
        capture_id: str,
        offset: int = 0,
        max_chars: int = 4000,
        _: None = Depends(require_auth),
    ):
        return svc.obter_evidencia(capture_id, offset=offset, max_chars=max_chars)

    @app.get("/v1/fontes")
    def get_fontes(_: None = Depends(require_auth)):
        return svc.listar_fontes()

    app.add_middleware(_LimiteCorpo)
    return app


def run_api(
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    token: str | None = None,
    home: str | None = None,
    registro: str | None = None,
) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "uvicorn não instalado; instale o extra: pip install 'freoa-verifica[server]'"
        ) from exc
    effective = token if token is not None else os.environ.get("FV_API_TOKEN")
    if host not in _LOCAL_HOSTS and not effective:
        raise RuntimeError(
            "recusado: host não local exige token (--token ou FV_API_TOKEN)"
        )
    if token:
        os.environ["FV_API_TOKEN"] = token
    app = create_app(
        home=home,
        token=token if token is not None else effective,
        modo="local" if host in _LOCAL_HOSTS else "remoto",
        registro=registro,
    )
    aviso = app.state.verifica.acervo_status()
    if aviso:
        print(f"[aviso] acervo_incompleto: {aviso}", file=sys.stderr, flush=True)
    uvicorn.run(app, host=host, port=port)
