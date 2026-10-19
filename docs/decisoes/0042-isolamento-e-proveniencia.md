# 0042 — Isolamento de parsers e vínculo de proveniência

Data: 2026-10-18. Escopo: A6, A9 e A10 do plano 1.2.0.
Implementação para revisão independente; não altera o critério de `verified`.

## Decisão

1. Todos os perfis são limitados pelo filho antes de ler stdin ou importar parsers.
   PDF: 1024 MiB/60 s CPU; demais: 2048 MiB/120 s. Windows instala Job Object
   via ctypes com PROCESS_MEMORY, PROCESS_TIME, ACTIVE_PROCESS=1, KILL_ON_JOB_CLOSE
   e DIE_ON_UNHANDLED_EXCEPTION. O handle permanece aberto até o fim do filho;
   breakaway não é autorizado. POSIX instala AS/CPU e NPROC=0 quando suportado,
   para UID não root. Falha ao instalar limites encerra com exit 78 sem ler entrada.
2. Pai limita entrada a 200 MiB (também após codificar string UTF-8), stdout a
   64 MiB e stderr a 64 KiB. Threads drenam ambos os pipes durante envio de stdin;
   excesso/timeout mata o filho. Falha nunca entrega texto parcial como válido.
3. Só arquivos cujo SHA-256 esteja na lista embutida são vinculados. A lista inclui
   snapshot 1.1.0, digest `adaeca748fba9e3ad97f4459fad754f61ba337305383677b3655c7ea20c27119`,
   derived_version 3 e pacote mínimo 1.1.0. Autenticidade não implica compatibilidade:
   derivados anteriores exigem reconstrução no staging antes de publicar (C6).
4. Diretórios não têm digest oficial de tar. Exigem a mesma autorização explícita
   dos arquivos não listados: CLI `--aceitar-nao-vinculado`, fachada
   `aceitar_nao_vinculado=True`. Não criamos digest canônico alternativo, pois ele
   não corresponderia aos bytes publicados. Recusa: `SNAPSHOT_NAO_VINCULADO`.
   Nenhum campo do manifesto de origem pode autodeclarar vínculo. Manifesto local,
   resultado, `snapshot info` e `doctor` expõem o estado; reabrir mantém a informação.
   A versão efetiva dos derivados é a do banco, com a versão original separada.
5. `latest` procura releases estáveis em ordem da API, ignora assets sem nome na
   lista ou com digest declarado divergente, e verifica SHA-256 dos bytes baixados
   antes de extrair. Pacote mínimo limita as entradas elegíveis. A flag não torna
   `latest` arbitrário: permite somente origem/URL não vinculada explícita.
6. Release atesta wheel, sdist, requirements-lock.txt e SHA256SUMS. Actions
   continuam fixadas por SHA. Constraints limitam versões; não autenticam por si
   só artefatos transitivos. Instalador verifica attestation do wheel e do lock
   disponível quando tem gh; falha interrompe. Sem gh, aviso e registro persistente.
7. Toda chamada nativa do instalador passa por Invoke-NativeChecked, que captura
   LASTEXITCODE imediatamente. Falhas nomeiam a etapa e saem com código não zero.
   Aceite exige versão 1.2.0, snapshot instalado/vinculado, derivados atuais e
   doctor offline sem falha nem acervo incompleto. Só então imprime Pronto e grava
   concluida=true. Se necessário, reconstrói e confere novamente.

## Limites e operação remota

Não contemos rede, FS nem privilégios do filho. NPROC é por UID, aplicado ao filho;
root/capabilities podem ignorá-lo. Job Object não é sandbox. Serviço remoto exige
contêiner sem rede, FS somente leitura, usuário sem privilégios, capabilities
removidas e no-new-privileges. Exemplo de configuração em SECURITY.md.

## Evidência e testes

Os testes de isolamento usam lançador próprio que chama o _main real e injeta só
no processo de teste uma função hostil; nenhum perfil, variável de ambiente ou
chave de ativação hostil é aceito no produto. Exercitam memória, CPU, stdout,
stderr, descendentes (skip POSIX quando inaplicável), entrada e falha de limites.
Testes de proveniência exercitam recusa, exceção explícita, persistência/reabertura,
vínculo positivo, seleção latest e recusa antes da extração. PowerShell real no
Windows executa gh.cmd falso com exit 37 e prova interrupção sem Pronto; análise
AST confere que toda chamada nativa passa pela função de checagem.

Testes anteriores de exportação/importação local declaram a exceção explicitamente
para continuar exercitando integridade, rollback, anexação e migração. Mocks de
latest fixam seus próprios pins sintéticos, sem substituir a política em produção.
A factory temporária herdável existente no Windows passa também a atender o
controlador xdist, que pede seu diretório antes das fixtures.

Contratos técnicos: [Job Object / limites](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)
e [resource](https://docs.python.org/3.11/library/resource.html).

Linux, integração de release publicada e instalação completa via rede: NOT RUN
nesta worktree Windows. Parecer adversarial independente permanece necessário para
avançar o marco, conforme AGENTS.md.


## Inventário das alterações e justificativa dos testes existentes

- Produto: `freoa_verifica/parsers/isolated.py` (limites e I/O),
  `freoa_verifica/snapshot.py` (vínculo/seleção), `freoa_verifica/acervo.py`
  (persistência), `freoa_verifica/service.py` (fachada/doctor),
  `freoa_verifica/cli.py` (flag), `freoa_verifica/data/snapshots-oficiais.json` (pin).
- Operação: `scripts/instalar-freoa-verifica.ps1`, `.github/workflows/release.yml`
  (sujeitos atestados), `.github/workflows/ci.yml` (leva o instalador para testar
  fora do checkout), `SECURITY.md` e esta decisão.
- Novos: `tests/test_isolamento_120.py`, `tests/test_proveniencia_120.py` e
  `tests/test_instalador_120.py`. O último também prova registro do aviso sem gh e
  interrupção por python.cmd com exit 23, usando downloads sintéticos.
- `tests/conftest.py`: factory Windows herdável também no controlador xdist.
- Exceção explícita nas instalações de snapshots sintéticos, mantendo as asserções
  preexistentes de integridade, migração, rollback, anexação e recusa:
  `tests/test_c6_derivados.py`, `tests/test_m5_audit_fixes.py`,
  `tests/test_m6_completion.py`, `tests/test_m6_semente_bench.py`,
  `tests/test_r13.py`, `tests/test_r3_regressions.py`, `tests/test_r9.py`,
  `tests/test_rodada3_auditor.py`, `tests/test_rodada5_auditor.py` e
  `tests/test_rodada7_monotonia.py`.
- `tests/test_r5.py`, `tests/test_r6.py`, `tests/test_r11.py`: exceção local e pins
  sintéticos no transporte de releases para alcançar os controles originais.
- `tests/test_r7.py`, `tests/test_r12.py`: pins sintéticos para manter os testes
  de seleção/fallback de latest sob a nova política.
- `tests/test_fronteiras_103.py`: exceção explícita no teste de exclusividade;
  no teste de release, exige os quatro sujeitos atestados e actions por SHA.


## Validação local final

Windows real, Python 3.14.6, comando solicitado:
`.\.venv\Scripts\python.exe -m pytest -q -m "not live" -n 8 -p no:cacheprovider`

`5330 passed, 1 skipped in 118.15s (0:01:58)`.
O skip pertence à suíte preexistente; os 20 casos novos executaram no Windows.
`git diff --check`: sem erro de whitespace. Não executamos fontes live nem release.
