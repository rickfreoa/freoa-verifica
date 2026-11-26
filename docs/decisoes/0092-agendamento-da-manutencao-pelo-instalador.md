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

## Auditoria Codex (r1, BLOQUEADOR) e correções

1. **Crontab ilegível era sobrescrito.** Leitura com erro só vale como tabela vazia quando o `crontab -l` afirma não
   haver crontab; qualquer outra falha aborta sem gravar.
2. **Injeção no comando agendado.** No cron, cada argumento vai entre aspas simples (`shlex.quote`) e `%` é escapado;
   no systemd, aspas, `\`, `%` e `$` são escapados; home com quebra de linha é recusado.
3. **Instalação sem lock verificado.** Lock ausente (404) interrompe os dois instaladores, salvo com
   `-SemAttestation` / `--sem-attestation`, que já é a renúncia explícita à proveniência.
4. **Arquivos do comando agendado.** Unidades systemd e plist com modo 0600, substituindo link simbólico em vez de
   segui-lo; o instalador sh roda com `umask 077`.
5. **Remoção informava sucesso com falha.** O resultado de cada mecanismo removido é propagado.
6. **URI e pipelines.** `file://` gerado por `Path.as_uri()`; saídas do `fv` capturadas antes de examinar o JSON.
7. **Execução elevada.** O sh e `fv acervo agendar` recusam root; o instalador do Windows avisa quando elevado (a
   tarefa roda com o token do usuário e privilégio mínimo de qualquer modo).

## Auditoria Codex (r2, BLOQUEADOR) e correções

1. **Diretórios reutilizados.** O instalador sh confere, antes de usar `~/freoa-verifica` e o diretório do
   registro, que nem eles nem os ancestrais sejam link simbólico, de outro usuário ou graváveis por grupo/outros
   (diretório com sticky bit, como /tmp, é admitido); dentro dos próprios diretórios remove a escrita de grupo/outros.
   `fv acervo agendar` recusa agendar executável cujo caminho seja substituível por terceiros e cria os diretórios
   de unidade e plist com modo 0700.
2. **Remoção.** Unidade systemd presente precisa ser desativada (e só então apagada); crontab ilegível não comprova
   ausência; qualquer falha devolve `erro`.
3. **Windows elevado.** O instalador recusa execução como administrador antes de qualquer escrita, salvo
   `-PermitirAdministrador` (os testes de CI usam a opção, porque os runners Windows são elevados).

## Auditoria Codex (r3, BLOQUEADOR; última rodada pela D5) e correções

1. **Diretório da unidade ou do plist.** Antes de gravar, o diretório próprio aberto a grupo/outros é fechado e o
   caminho inteiro (diretório e ancestrais) passa por `caminho_inseguro`; substituível por terceiros, nada é gravado.
2. **Links internos da instalação reutilizada.** O instalador sh resolve cada link dentro de `~/freoa-verifica` (como
   `.venv/bin/python`) e exige que o destino e os ancestrais também não sejam trocáveis por terceiros.
3. **`fv acervo agendar --mostrar`** distingue `ausente` (unidade inexistente, sem crontab, serviço não encontrado)
   de `indisponivel` (consulta recusada).

**Ajuste pós-CI.** A escrita de grupo só torna um caminho inseguro quando o grupo não é o grupo privado do próprio
usuário (nome igual ao do usuário e nenhum outro membro). Sem isso, o umask 002 padrão das distribuições com grupo
por usuário (Ubuntu, Fedora) recusaria toda instalação. Os testes passaram como root e como usuário comum com umask
002 e 022.

## Teste em Debian 13 (colega, branch c2e4d83) e correções

Instalação limpa, usuário comum, acervo da 1.4.0a6. O timer do usuário foi criado e a manutenção rodou e renovou
obras. Seis achados, todos corrigidos com teste de regressão:

1. **CF nunca renovava pelo normas.leg.br.** A API devolve três manifestações `Current` (pt, en, fr) e `fetch`
   filtrava só por versão, o que dava `versao_ausente_ou_ambigua`. A escolha agora exige idioma português
   (`inLanguage` ausente, `pt` ou `pt-*`), e o idioma fica registrado em `texts`.
2. **Lei com versão única** (ex.: Lei 15.177/2025) traz `encoding` como objeto, não lista, e dava
   `resposta_inesperada`. `normalizar_encoding` aceita objeto único na busca e na revalidação de metadados; outro
   tipo continua `metadados_invalidos`.
3. **Teto de chamadas não é falha.** `teto_de_chamada`, `teto_de_sessao` e `orcamento` passam a adiar o restante da
   rodada (`adiado`/`adiadas`), sem registrar falha. `fv acervo manter` sai com 0 em `ok` e `parcial` e com 1 só em
   falha; o doctor mostra `parcial` como alerta. Assim o timer deixa de ficar `failed` por limite de cortesia.
4. **Lingering.** No systemd de usuário, `fv acervo agendar` consulta `Linger` e tenta `loginctl enable-linger`; se a
   política do sistema recusar, o resultado traz `aviso` com o comando que um administrador deve executar, e o
   instalador o exibe. O timer continua criado.
5. **Motivo da falha no instalador sh.** Toda chamada `fv … --json` passa por `fv_json`, que em falha mostra
   `status`, `motivo`, `erro` ou `reason_code` do JSON, ou as últimas linhas de stderr, em vez de
   "comando com erro (linha N)".
6. **Mensagem do systemd em resultado ok.** Saída informativa (como "Created symlink") vai para `detalhe`; `erro`
   fica vazio quando o agendamento deu certo.

O teste do instalador do começo ao fim no Debian fica para depois da publicação da 1.4.0a7, quando o snapshot
fixado existir na release.
