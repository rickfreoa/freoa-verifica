"""API REST /v1 (extra `server`: fastapi + uvicorn)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

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


def create_app(home: str | None = None, token: str | None = None) -> Any:
    if FastAPI is None:
        raise RuntimeError(
            "fastapi não instalado; instale o extra: pip install 'freoa-verifica[server]'"
        )

    svc = Verifica(home=home)

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
    expected = token if token is not None else os.environ.get("FV_API_TOKEN")
    bearer = HTTPBearer(auto_error=False)

    def require_auth(
        creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> None:
        if not expected:
            return
        if creds is None or creds.scheme.lower() != "bearer" or creds.credentials != expected:
            raise HTTPException(status_code=401, detail="token inválido ou ausente")

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
    def post_verificacao(body: dict[str, Any], _: None = Depends(require_auth)):
        return svc.verificar_citacao(
            body.get("citacao") or "",
            trecho=body.get("trecho"),
            data=body.get("data"),
            modo=body.get("modo") or "literal",
            proposicao=body.get("proposicao"),
        )

    @app.post("/v1/verificacoes/texto")
    def post_verificacao_texto(body: dict[str, Any], _: None = Depends(require_auth)):
        return svc.verificar_texto(body.get("texto") or "", data=body.get("data"))

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

    return app


def run_api(
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    token: str | None = None,
    home: str | None = None,
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
    app = create_app(home=home, token=token if token is not None else effective)
    uvicorn.run(app, host=host, port=port)
