# 0092 - Agendamento da manutenção do acervo pelo instalador

Status: aprovada pelo titular em 26/11/2026 ("inclua no instalador a configuração de tarefa agendada (no Windows,
Linux e MacOS) que faça as atualizações do acervo automaticamente").

## Problema

A 0091 (emenda A) criou `fv acervo manter` e `fv acervo agendar`, mas deixou o agendamento como passo manual depois da
instalação. Sem ele, o acervo envelhece até `CAPTURA_DESATUALIZADA` (30 dias), que foi o ponto 5 do relato do
colega. O agendamento só existia no Windows e no Linux com systemd de usuário; macOS e Linux sem systemd (WSL,
contêiner) recebiam `nao_suportado`. Não havia instalador para Linux e macOS.

Na instalação da 1.4.0a6, o instalador do Windows parou em "instalar wheel" porque, com a saída redirecionada, o aviso
de versão nova do pip (stderr) virou erro terminante sob `$ErrorActionPreference = "Stop"`.

## Decisão

1. **Instaladores agendam por padrão.** `instalar-freoa-verifica.ps1` e o novo `instalar-freoa-verifica.sh` executam
   `fv acervo agendar --instalar --json` depois do `doctor` e antes de gravar `concluida: true`; falha de agendamento
   interrompe a instalação com o nome da etapa, como as demais. `-SemAgendamento` / `--sem-agendamento` dispensam, com
   aviso, e o registro `instalacao.json` grava `agendamento` (instalado ou dispensado).
2. **Mecanismos.** Windows: Agendador de Tarefas do usuário (sem mudança). Linux: timer do systemd de usuário; se
   `systemctl --user` falhar, crontab do usuário com duas linhas marcadas (a cada N horas no minuto pedido e
   `@reboot`), preservando as linhas alheias. macOS: LaunchAgent `br.freoa.verifica.manter` em
   `~/Library/LaunchAgents`, com `StartCalendarInterval` e `StartInterval`, carregado por `launchctl bootstrap
   gui/<uid>`. Nenhum exige administrador.
3. **Stderr não é falha.** No instalador do Windows, `Invoke-NativeChecked` roda o programa nativo com
   `$ErrorActionPreference = "Continue"` e decide pelo código de saída; o aviso de versão do pip é desligado
   (`PIP_DISABLE_PIP_VERSION_CHECK=1`) nos dois instaladores.
4. **Instalador de Linux e macOS** replica as etapas e garantias do de Windows: attestation obrigatória do wheel e do
   lock (`gh attestation verify` com workflow e tag), lock com hashes, preservação de acervo anterior sem vínculo,
   snapshot vinculado, reconstrução quando os derivados ficarem para trás, `doctor --offline`, registro final só no
   fim. O registro fica em `~/.local/share/freoa-verifica/instalacao.json`, onde `fv doctor` o procura.

## Limites

- Cron não recupera execução perdida com a máquina desligada; o `@reboot` e o intervalo de 2 horas compensam em parte.
- No macOS e no Linux sem systemd o mecanismo foi testado por simulação (comandos e conteúdo gerados), não em máquina
  real; a CI só tem Ubuntu e Windows.
