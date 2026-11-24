# Renovação agendada do acervo legislativo (decisão 0091)

A vigência de um dispositivo só sai `verified` ou `vigente_na_fonte` com captura de até 30 dias
(`CAPTURA_DESATUALIZADA` acima disso). Instalação de snapshot não se renova sozinha: sem agendamento, todo o acervo
legislativo passa da janela cerca de um mês depois da data do snapshot.

`fv acervo renovar` recaptura as obras legislativas federais cuja captura canônica mais recente passou de `--dias`
(padrão 21), pelas rotas de nova captura admitidas (Câmara e `normas_leg`; o Planalto recusa o cliente identificado,
decisão 0048). Cada obra tem resultado próprio. Sai com código 1 se alguma falhar, para que o agendador acuse.

```bash
fv acervo renovar --json            # todas as obras com mais de 21 dias
fv acervo renovar --dias 14 --limite 40
fv doctor --offline --json          # verificação "acervo_idade"
```

O servidor MCP também avisa no início (`[aviso] acervo_envelhecendo`, em stderr).

## Depois de atualizar para o parser 1.2.4 (derivados 6)

Homes com derivados 5 respondem `indisponivel/ACERVO_DESATUALIZADO` até a reconstrução. Uma vez, antes de reabrir o
servidor:

```bash
fv acervo reconstruir --json        # ~10 min no snapshot da 1.4.0a5; preserva o banco anterior ao lado
```

## Linux (systemd, ex.: contêiner LXC)

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
