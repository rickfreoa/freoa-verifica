#!/usr/bin/env bash
# Instalador do FREOA Verifica para Linux e macOS (decisão 0092), equivalente a instalar-freoa-verifica.ps1.
# A attestation é obrigatória; --sem-attestation pula a verificação e grava attestation_verificada: false.
# Ao final agenda a manutenção do acervo (systemd de usuário ou cron no Linux; LaunchAgent no macOS);
# --sem-agendamento dispensa.
set -euo pipefail

VERSAO="1.4.0a6"
SEM_ATTESTATION=0
SEM_AGENDAMENTO=0
while [ $# -gt 0 ]; do
    case "$1" in
        --versao) VERSAO="$2"; shift 2 ;;
        --versao=*) VERSAO="${1#*=}"; shift ;;
        --sem-attestation) SEM_ATTESTATION=1; shift ;;
        --sem-agendamento) SEM_AGENDAMENTO=1; shift ;;
        -h|--help) sed -n '2,5p' "$0"; echo "uso: $0 [--versao X] [--sem-attestation] [--sem-agendamento]"; exit 0 ;;
        *) echo "argumento desconhecido: $1" >&2; exit 2 ;;
    esac
done

# O aviso de versão nova do pip não é falha (0092).
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1
# Ambiente, registro e acervo sem escrita de grupo ou outros: o comando agendado sai daqui (0092).
umask 077

ETAPA="preparar"
falhou() { echo "FALHOU na etapa: $ETAPA${1:+ - $1}" >&2; exit 1; }
trap 'falhou "comando com erro (linha $LINENO)"' ERR

if [ "$(id -u)" = 0 ]; then
    echo "FALHOU na etapa: preparar - execute como usuario comum, nao como root" >&2; exit 1
fi

REPO="rickfreoa/freoa-verifica"
BASE="https://github.com/$REPO/releases/download/v$VERSAO"
DESTINO="$HOME/freoa-verifica"
# Mesmo local que `fv doctor` consulta para o registro do instalador (acervo.attestation_instalacao).
REGISTRO_DIR="$HOME/.local/share/freoa-verifica"
REGISTRO="$REGISTRO_DIR/instalacao.json"
mkdir -p "$DESTINO" "$REGISTRO_DIR"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ETAPA="localizar python"
PY=""
for candidato in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidato" >/dev/null 2>&1 &&
        "$candidato" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$(command -v "$candidato")"; break
    fi
done
[ -n "$PY" ] || falhou "Python 3.11 ou superior ausente"

# Diretórios reutilizados (instalação anterior) não podem ser trocáveis por terceiros: o comando agendado e o acervo
# saem deles. Link simbólico, dono alheio ou escrita de grupo/outros nos ancestrais interrompem; nos próprios
# diretórios do usuário a escrita de grupo/outros é removida (0092).
ETAPA="conferir permissoes"
"$PY" - "$DESTINO" "$REGISTRO_DIR" <<'PY' || falhou "caminho inseguro"
import os, stat, sys
from pathlib import Path
uid = os.geteuid()
for alvo in map(Path, sys.argv[1:]):
    if alvo.is_symlink():
        sys.exit(f"{alvo}: link simbolico")
    for parte in [alvo, *alvo.parents]:
        st = parte.lstat()
        if st.st_uid not in (uid, 0):
            sys.exit(f"{parte}: de outro usuario")
        if parte != alvo and st.st_mode & 0o022 and not (stat.S_ISDIR(st.st_mode) and st.st_mode & stat.S_ISVTX):
            sys.exit(f"{parte}: gravavel por grupo ou outros")
    for raiz, dirs, arquivos in os.walk(alvo):
        for nome in [*dirs, *arquivos]:
            p = Path(raiz, nome)
            st = p.lstat()
            if st.st_uid != uid:
                sys.exit(f"{p}: de outro usuario")
            if not stat.S_ISLNK(st.st_mode) and st.st_mode & 0o022:
                p.chmod(st.st_mode & ~0o022)
    alvo.chmod(alvo.stat().st_mode & ~0o022)
PY

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
    else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# Registro em JSON pelo próprio Python (sem montar JSON à mão no shell).
gravar_registro() {  # versao sha_wheel digest proveniencia verificada commit agendamento concluida
    "$PY" - "$REGISTRO" "$@" <<'PY'
import json, sys
destino, versao, sha, digest, prov, verif, commit, agend, concl = sys.argv[1:10]
dados = {"versao": versao, "sha256_wheel": sha, "digest_snapshot": digest or None, "proveniencia": prov,
         "attestation_verificada": verif == "1", "commit": commit or None, "concluida": concl == "1"}
if agend:
    dados["agendamento"] = agend
with open(destino, "w", encoding="utf-8") as f:
    json.dump(dados, f, ensure_ascii=False, indent=4)
PY
}

json_campo() {  # lê um campo (a.b.c) do JSON na entrada padrão
    "$PY" -c 'import json,sys
v=json.load(sys.stdin)
for k in sys.argv[1].split("."):
    v = v.get(k) if isinstance(v, dict) else None
print("" if v is None else (json.dumps(v) if isinstance(v,(dict,list)) else v))' "$1"
}

WHEEL_NOME="freoa_verifica-$VERSAO-py3-none-any.whl"
WHEEL="$DESTINO/$WHEEL_NOME"
ETAPA="baixar wheel"
if [ -f "$SCRIPT_DIR/$WHEEL_NOME" ]; then cp "$SCRIPT_DIR/$WHEEL_NOME" "$WHEEL"
else curl -fsSL "$BASE/$WHEEL_NOME" -o "$WHEEL"; fi

ETAPA="verificar proveniencia"
VERIFICADA=0
COMMIT=""
ATTEST=(--repo "$REPO" --signer-workflow "$REPO/.github/workflows/release.yml" --source-ref "refs/tags/v$VERSAO"
        --deny-self-hosted-runners)
if [ "$SEM_ATTESTATION" = 1 ]; then
    PROVENIENCIA="PROVENIENCIA NAO VERIFICADA (--sem-attestation)"
    echo "AVISO: $PROVENIENCIA" >&2
else
    command -v gh >/dev/null 2>&1 ||
        falhou "GitHub CLI (gh) ausente: attestation obrigatoria (use --sem-attestation para prosseguir sem verificar)"
    ATT="$(gh attestation verify "$WHEEL" "${ATTEST[@]}" --format json)" || falhou "attestation recusada"
    VERIFICADA=1
    PROVENIENCIA="VERIFICADA: gh attestation verify"
    COMMIT="$(printf '%s' "$ATT" | "$PY" -c 'import json,sys
try: print(json.load(sys.stdin)[0]["verificationResult"]["signature"]["certificate"]["sourceRepositoryDigest"])
except Exception: print("")')"
fi
SHA_WHEEL="$(sha256 "$WHEEL")"
gravar_registro "$VERSAO" "$SHA_WHEEL" "" "$PROVENIENCIA" "$VERIFICADA" "$COMMIT" "" 0

ETAPA="baixar lock"
LOCK="$DESTINO/requirements-lock.txt"
TEM_LOCK=1
CODIGO="$(curl -sSL -w '%{http_code}' -o "$LOCK" "$BASE/requirements-lock.txt")" || falhou "rede"
if [ "$CODIGO" = 404 ]; then
    # Sem lock não há hashes das dependências: só com a renúncia explícita à proveniência (0092).
    [ "$SEM_ATTESTATION" = 1 ] || falhou "requirements-lock.txt ausente nesta release: dependencias sem hash"
    TEM_LOCK=0; rm -f "$LOCK"; echo "AVISO: requirements-lock.txt ausente nesta release" >&2
elif [ "$CODIGO" != 200 ]; then
    falhou "HTTP $CODIGO"  # só 404 é asset opcional ausente; outra falha não é ausência
fi
if [ "$VERIFICADA" = 1 ] && [ "$TEM_LOCK" = 1 ]; then
    ETAPA="verificar lock"
    gh attestation verify "$LOCK" "${ATTEST[@]}" >/dev/null
fi

ETAPA="criar venv"
[ -x "$DESTINO/.venv/bin/python" ] || "$PY" -m venv "$DESTINO/.venv"
PYV="$DESTINO/.venv/bin/python"
FV="$DESTINO/.venv/bin/fv"

ETAPA="instalar wheel"
if [ "$TEM_LOCK" = 1 ]; then
    # O lock tem hashes, o que liga --require-hashes; o próprio wheel entra com o hash já conferido.
    REQ="$DESTINO/requirements-wheel.txt"
    URI="$("$PY" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve().as_uri())' "$WHEEL")"
    printf 'freoa-verifica[server] @ %s --hash=sha256:%s\n' "$URI" "$SHA_WHEEL" > "$REQ"
    "$PYV" -m pip install -r "$REQ" -c "$LOCK"
else
    "$PYV" -m pip install "${WHEEL}[server]"
fi

ETAPA="validar versao"
"$FV" --version | grep -Eq "(^|[^0-9.])${VERSAO//./\\.}([^0-9.]|$)" || falhou "versao inesperada"

# Instalação de snapshot é anexação: acervo anterior sem vínculo comprovado contaminaria o novo; ele é
# preservado ao lado e o snapshot vai para home limpo.
ETAPA="preservar acervo anterior"
PRE="$("$FV" snapshot info --json)"
TEM_DADOS="$(printf '%s' "$PRE" | "$PY" -c 'import json,sys
d=json.load(sys.stdin)
print(1 if d.get("instalado") or any(int(d.get(k) or 0) > 0 for k in ("obras","capturas","decisoes")) else 0)')"
if [ "$TEM_DADOS" = 1 ] && [ "$(printf '%s' "$PRE" | json_campo vinculado)" != "True" ]; then
    HOME_ATUAL="$(printf '%s' "$PRE" | json_campo home)"
    BAK="$HOME_ATUAL.pre-$VERSAO-$(date +%Y%m%d%H%M%S)"
    N=0; while [ -e "$BAK" ]; do N=$((N+1)); BAK="$HOME_ATUAL.pre-$VERSAO-$(date +%Y%m%d%H%M%S)-$N"; done
    mv "$HOME_ATUAL" "$BAK"; mkdir -p "$HOME_ATUAL"
    echo "Acervo anterior sem vinculo preservado em $BAK"
fi

ETAPA="instalar snapshot"
INST="$("$FV" snapshot install --json)"
[ "$(printf '%s' "$INST" | json_campo status)" = ok ] || falhou "snapshot recusado: $(printf '%s' "$INST" | json_campo motivo)"

ETAPA="validar acervo"
INFO="$("$FV" snapshot info --json)"
ler() { printf '%s' "$INFO" | json_campo "$1"; }
if [ "$(ler instalado)" != True ] || [ "$(ler vinculado)" != True ] || [ -z "$(ler derived_version_atual)" ]; then
    falhou "acervo nao instalado/vinculado"
fi
if [ -z "$(ler derived_version)" ] || [ "$(ler derived_version)" -lt "$(ler derived_version_atual)" ]; then
    ETAPA="reconstruir acervo"
    REB="$("$FV" acervo reconstruir --json)"
    [ "$(printf '%s' "$REB" | json_campo status)" = ok ] || falhou "reconstrucao recusada"
    INFO="$("$FV" snapshot info --json)"
fi
[ "$(ler derived_version)" = "$(ler derived_version_atual)" ] || falhou "derivados incompativeis"

ETAPA="doctor offline"
DOC="$("$FV" doctor --offline --json)"
printf '%s' "$DOC" | "$PY" -c 'import json,sys
d=json.load(sys.stdin)
ruins=[v for v in d.get("verificacoes") or [] if v.get("status") not in ("ok","alerta")]
sys.exit(0 if d.get("status")=="ok" and d.get("verificacoes") and not ruins and not d.get("acervo_incompleto") else 1)' ||
    falhou "diagnostico bloqueante"

# Manutenção periódica do acervo (decisões 0091-A e 0092): tarefa do usuário, sem administrador.
if [ "$SEM_AGENDAMENTO" = 1 ]; then
    AGENDAMENTO="dispensado (--sem-agendamento)"
    echo "AVISO: manutencao automatica do acervo nao agendada: rode 'fv acervo manter' periodicamente." >&2
else
    ETAPA="agendar manutencao"
    AG="$("$FV" acervo agendar --instalar --json)"
    [ "$(printf '%s' "$AG" | json_campo status)" = ok ] || falhou "agendamento recusado: $(printf '%s' "$AG" | json_campo erro)"
    AGENDAMENTO="instalado: $(printf '%s' "$AG" | json_campo plataforma) $(printf '%s' "$AG" | json_campo mecanismo) $(printf '%s' "$AG" | json_campo hora), a cada 2 h"
fi

gravar_registro "$VERSAO" "$SHA_WHEEL" "$(ler proveniencia.snapshot_sha256)" "$PROVENIENCIA" "$VERIFICADA" "$COMMIT" \
    "$AGENDAMENTO" 1
echo "Pronto. Comandos em: $DESTINO/.venv/bin (fv e freoa-verifica-mcp)."
