# 0081 — Correção r1 da ativação ao vivo da Câmara (parecer do PR #39)

Codificador (Sonnet), 08/11/2026, sobre o parecer COM BLOQUEADOR do auditor (achados 1–10, contraprovas C01–C22). Não altera
a 0080, a matriz IL.1, os pisos, a reserva, os mutantes, `transport.py`, `CONTRATO_VERSAO` nem o consumidor FREOA. Registra as
escolhas de implementação que a 0080 deixava abertas e as regras que o parecer tornou explícitas. Qualificação continua
`nao_apurada` até o IL.3-c.

## 1. Autorização de ativação (0080 §2)

1. A ativação é revalidada pelo portão antes de **cada** obtenção viva (e de novo depois da espera do ritmo), não só na criação
   do conector. Sem registro válido: `ativacao_ao_vivo_pendente`, sem emissão e sem bloqueio persistente.
2. Registro válido exige estrutura completa (revisão com `auditor`, `revisado_em` ISO, `resultado`, `termo_sha256` e `sha256`
   dos bytes), os **bytes da revisão preservados** em `camara/revisao/<sha>.json` com hash conferido e coerentes com os campos,
   o termo preservado com recibo íntegro (URL exata, 200, `text/html`, tamanho, instante, hash, UA, vínculo à política de
   `www2` da ativação) e os bytes dos robots preservados e permissivos para os caminhos de conteúdo. O selo `registro_sha256`
   é checksum público de consistência e não substitui nada disso.
3. `registrar` lê a revisão uma só vez, valida o registro final antes de gravá-lo e recusa política expirada ou adulterada.
   Igualdade automática entre versões do produto continua não exigida.

## 2. Robots (0080 §4)

1. Persistem-se os **bytes originais** da resposta (`robots-<host>-<sha>.txt`); toda releitura confere o hash e interpreta pelo
   Content-Type guardado. Divergência é falha local, nunca autorização.
2. Resposta reaproveitada da guarda não é nova obtenção: vale pelo instante original (`fetched_at`) e, vencida, falha com
   `robots_expirado_sem_nova_obtencao`; o cache nunca renova `obtido_em`/`valido_ate`. O limite de 24 h é imposto no esquema.
3. `/robots.txt` pedido diretamente segue o mesmo fluxo de bloqueio, validação, persistência e backoff.
4. Decisões por caminho são registradas sem teto (o recibo renova a cada 24 h); nenhuma é descartada.
5. Comparação e especificidade (RFC 9309 §2.2.2) sobre **octetos** normalizados: `%XX` de octeto não reservado é decodificado,
   o de octeto reservado ou fora do ASCII fica codificado em maiúsculas, `*` e `$` codificados são literais.
6. **`Crawl-delay`**: o teto de 3600 s deixa de tornar o valor "inválido" (invalidez é só valor não numérico, negativo ou não
   finito). Valor válido é registrado e honrado; se a espera necessária exceder o **teto operacional de 3600 s**, a obtenção
   é uma **abstenção operacional declarada** (`crawl_delay_acima_do_teto_operacional`), sem emissão e sem bloqueio persistente.

## 3. Ritmo e tetos (0080 §5)

1. O início de cada requisição grava o instante civil e a **marca monotônica** (`time.monotonic()`, comparável entre processos
   da mesma máquina). O decorrido é o **menor** dos dois; recuo do civil ou reinício da marca contam como nada decorrido
   (conservador, no máximo uma espera de intervalo).
2. O teto da sessão (200) e o da chamada (30) somam os hosts e são **reservados atomicamente** antes da espera; a reserva é
   devolvida se a emissão é abortada. O escopo da chamada é compartilhado por todas as instâncias participantes.

## 4. Barreiras (0080 §6)

1. Falha local (persistência, esquema persistido inválido, interpretação local, falha do parser) é **terminal** para a chamada
   pública ou sessão do instrumento, nos dois hosts; não persiste; nova chamada recomeça. Todos os esquemas persistidos são
   validados e falham como `persistencia_local_falhou`/`interpretacao_local_falhou`, nunca como `KeyError`/`ValueError`.
2. Falha de perfil ou de resposta detectada depois do portão (busca/página/texto/identidade) alimenta o mesmo classificador
   (recurso persistente; host pelo escopo). Entrada inválida do chamador e formatos não habilitados não bloqueiam.
3. Recusa ou inconclusão de robots durante a ativação persiste o bloqueio do host. A reabertura de host descarta a política
   **antes** de remover o bloqueio, de modo que nenhum estado intermediário autoriza obtenção.

## 5. D6 e inventário (0080 §8)

1. Em `--reserva` nenhum predicado operacional (ok/falha, classe, ativação, bloqueio, conclusão) sai por stdout, stderr, logs
   ou código de saída (sempre 0); falhas inesperadas são contidas. O resultado integral vai só ao arquivo do guardião
   (`--saida-privada`, obrigatório com `--reserva`), sob a guarda separada.
2. O inventário grava, por unidade (norma), `inventario.json` com todos os recursos (obtidos, recusados, não obtidos e motivos)
   e o material parcial, mesmo quando a unidade falha; acumuladores do conector são zerados por norma; falha de gravação é
   falha controlada que encerra a sessão.

## 6. Atribuição e snapshot (0080 §§7 e 8.4)

1. `termo_sha256` é por **captura**: o registro de obtenção (`obtencoes.jsonl`) liga conteúdo e URL ao termo vigente; só vale
   com o termo preservado e conferido; nunca vem do termo corrente do home. `atribuicao` acompanha toda entrega de texto de
   origem Câmara, inclusive `buscar_legislacao` (local, staging e candidato ao vivo); `obter_evidencia` extrai a `autoria`.
2. O snapshot transporta, sob o inventário de hashes, termo, recibo, revisão, política (bytes e recibos), obtenções e os
   registros de ativação como **evidência** (instalar não ativa). A instalação confere nome-hash, recibo e coerência, funde sem
   substituir (termos de snapshots diferentes coexistem) e recusa evidência incoerente antes de qualquer mudança no home; a
   exportação recusa home com evidência incoerente. `captured_at` e procedência originais permanecem.

## 7. Limites declarados

- A marca monotônica entre processos depende de `time.monotonic()` ser comum ao sistema (vale em Windows, Linux e macOS);
  reinício da máquina é tratado como nada decorrido.
- A trava entre processos continua testada pelo teste existente com subprocessos; a reserva do teto é por processo (a sessão
  do instrumento é um processo).
- Capturas humanas futuras, revisão do inventário de desenvolvimento e captura da reserva seguem como pendências operacionais.
