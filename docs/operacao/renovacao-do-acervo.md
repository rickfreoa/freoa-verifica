# Renovação agendada do acervo legislativo (decisão 0091)

A vigência de um dispositivo só sai `verified` ou `vigente_na_fonte` com captura de até 30 dias
(`CAPTURA_DESATUALIZADA` acima disso). Instalação de snapshot não se renova sozinha: sem agendamento, todo o acervo
legislativo passa da janela cerca de um mês depois da data do snapshot.

`fv acervo renovar` recaptura as obras legislativas federais cuja captura canônica mais recente passou de `--dias`
(padrão 21), e também as obras marcadas `renovacao_pendente` pela revalidação (qualquer idade), pelas rotas de nova
captura admitidas (Câmara e `normas_leg`; o Planalto recusa o cliente identificado, decisão 0048). Cada obra tem
resultado próprio. Sai com código 1 se alguma falhar, para que o agendador acuse.

`fv acervo revalidar` lê os metadados de normas.leg.br (sem alterar o critério de `verified`). Metadados diferentes do
último lido marcam a obra para renovação; o estado não entra em verificação nem em resposta ao cliente.

`fv acervo abrir-normas-leg --decisao TEXTO` grava `normas_leg/escopo.json` e registra a reabertura do host. Com o
escopo `metadados_e_renovacao`, consultas sob demanda declaram `fora_do_escopo_do_home`; revalidar e renovar usam a
rota.

`fv acervo manter` executa revalidar e depois renovar, gravando `manutencao.json` no home. `fv acervo agendar` instala
tarefa diária no agendador do usuário (Windows: `schtasks`; Linux: systemd user) para `fv acervo manter --json`,
com repetição a cada 2 horas (`--intervalo-horas`, padrão 2) para percorrer o acervo em lotes dentro do teto do portão.

```bash
fv acervo revalidar --json
fv acervo renovar --json            # todas as obras com mais de 21 dias ou pendentes
fv acervo renovar --dias 14 --limite 40
fv acervo manter --json             # revalidar + renovar + manutencao.json
fv acervo agendar --instalar --hora 05:43
fv acervo abrir-normas-leg --decisao "texto da decisão"
fv doctor --offline --json          # acervo_idade e acervo_manutencao
```

O servidor MCP também avisa no início (`[aviso] acervo_envelhecendo`, em stderr).

## Depois de atualizar para o parser 1.2.4 (derivados 6)

Homes com derivados 5 respondem `indisponivel/ACERVO_DESATUALIZADO` até a reconstrução. Uma vez, antes de reabrir o
servidor:

```bash
fv acervo reconstruir --json        # ~10 min no snapshot da 1.4.0a5; preserva o banco anterior ao lado
```

## Manutenção diária (emenda A)

Preferível a renovar isolado: `fv acervo agendar --instalar` registra `fv acervo manter --json` no usuário corrente,
sem administrador. O `doctor` alerta se `manutencao.json` está ausente, falhou ou terminou há mais de 48 horas.
Desde a decisão 0092, os instaladores (`instalar-freoa-verifica.ps1` e `instalar-freoa-verifica.sh`) fazem isso ao
final; `-SemAgendamento` / `--sem-agendamento` dispensam. Mecanismo por plataforma:

| Plataforma | Mecanismo | Onde fica | Remover |
|---|---|---|---|
| Windows | Agendador de Tarefas, "FREOA Verifica - manter acervo" | tarefa do usuário | `fv acervo agendar --remover` |
| Linux com systemd de usuário | timer `fv-manter` | `~/.config/systemd/user/` | idem |
| Linux sem systemd de usuário (WSL, contêiner) | crontab do usuário, linhas marcadas `# freoa-verifica` (a cada 2 h e `@reboot`) | `crontab -l` | idem |
| macOS | LaunchAgent `br.freoa.verifica.manter` (horário diário e intervalo; o launchd roda ao acordar o que perdeu) | `~/Library/LaunchAgents/` | idem |

Teto de chamadas atingido não é falha: o restante da rodada fica adiado para a próxima execução, o resultado é
`parcial` e `fv acervo manter` sai com 0; o doctor só alerta quando houve falha real. Execução que não concluiu nada
(`adiado`) sai com 1. No Linux com systemd, o timer de usuário só roda sem sessão
aberta com lingering; `fv acervo agendar` tenta `loginctl enable-linger` e, se a política do sistema recusar, avisa
o comando que um administrador deve executar.

## Linux (systemd, ex.: contêiner LXC)

Com `fv acervo agendar --instalar`, a unidade fica em `~/.config/systemd/user/` (`fv-manter.service` e
`fv-manter.timer`). Para instalação de sistema, exemplo semanal só com renovar:

`/etc/systemd/system/fv-renovar.service`:

```ini
[Unit]
Description=FREOA Verifica - renovação do acervo legislativo
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=fv
Environment=FV_HOME=/var/lib/freoa-verifica
ExecStart=/opt/freoa-verifica/.venv/bin/fv acervo renovar --json
Nice=10
```

`/etc/systemd/system/fv-renovar.timer`:

```ini
[Unit]
Description=Renovação semanal do acervo do FREOA Verifica

[Timer]
OnCalendar=Sun *-*-* 03:17:00
RandomizedDelaySec=30min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl daemon-reload && systemctl enable --now fv-renovar.timer
systemctl list-timers fv-renovar.timer
journalctl -u fv-renovar.service -n 50
```

Caminhos, usuário e horário são exemplos; ajuste à instalação.

## Windows (Agendador de Tarefas)

```powershell
$fv = "$env:USERPROFILE\freoa-verifica\.venv\Scripts\fv.exe"
schtasks /Create /TN "FREOA Verifica - renovar acervo" /SC WEEKLY /D SUN /ST 03:17 `
  /TR "`"$fv`" acervo renovar --json" /F
```

## Leitura do resultado

- `renovadas`: obra, fonte e instante da nova captura.
- `falhas`: obra e motivo (`especie_busca_nao_demonstrada`, `tipo_nao_suportado`, barreira da fonte, rede). Falha
  não apaga a captura anterior; a resposta continua declarando a idade dela.
- `envelhecimento_restante`: o que ainda passa de `--dias` depois da execução.
