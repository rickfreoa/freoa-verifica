# Plano 1.2.0: fidelidade da prova, atualização e cobertura medida

Base: `main` em 3ea937f (v1.1.0). Origem: avaliação externa de 18/10/2026 (achados A1–A12),
conferida linha a linha contra o código nesta data. Critério de conclusão da rodada:
suíte verde, parecer do auditor sem bloqueador e comparativo com o JusRatio em que o
FREOA empata ou supera dentro do acervo disponível, com zero `verified` indevido.

## Aplicabilidade dos achados

| ID | Conferido no código | Aplicável | Decisão |
|---|---|---|---|
| A1 parte trocada | `service.py:2272-2283`: sem a parte pedida, devolve qualquer documento com `parte` = pedida | sim | P0 |
| A2 official_id sem tribunal | `service.py:2262-2267`: `fetchone()` sem tribunal | sim | P0 |
| A3 `inexistente` local | `service.py:2268-2269` | sim | P0 |
| A4 checkpoint STJ congela | `connectors/stj.py:452-475`: chave = id+max_itens; reaproveita bytes antigos | sim | P1 |
| A5 espécie monocrática | `_species_from_meta` ignora `parsed.kind`; resíduo `acordao` | sim | P0 |
| A6 isolamento | `parsers/isolated.py`: limites só POSIX e só PDF; saída inteira em memória | parcial | P1: Job Object no Windows, limites em todos os perfis, teto de saída. Restrição de rede/FS e queda de privilégio do filho: não implementável de forma portátil num pacote local; documentar e exigir contêiner para serviço remoto |
| A7 Host/Origin | `rest.py:146-160`: sem token só confere IP de origem | sim | P1: lista de Host permitidos e recusa de `Origin` externo no modo local |
| A8 registro completo | `registro.py:18,22`: padrão `completo` | sim | P1: padrão `sem_conteudo`; HMAC com segredo por home no lugar de hash puro |
| A9 proveniência | snapshot e checksum no mesmo canal; instalador sem attestation | sim | P1: digest do snapshot oficial embutido no wheel (o wheel tem attestation); instalador usa `gh attestation verify` quando há `gh` e declara quando não verificou; `-c requirements-lock.txt` |
| A10 instalador | `scripts/instalar-freoa-verifica.ps1`: sem `$LASTEXITCODE` | sim | P1 |
| A11 injeção | `sanitizacao.py` é triagem | sim (texto) | P2: documentação descreve triagem e delimitação; sem promessa de resistência |
| A12 cobertura | contagens de FONTES; inteiro teor por comprimento (`service.py:2169`) | sim | P1: conector TJDFT (API oficial), inteiro teor por declaração do perfil, documentação consolidada; íntegras STJ bloqueadas enquanto o portal não responde |

Não aplicável nesta rodada: fornecedores pagos (JUIT, Judex, Escavador, Jusbrasil) e
coletores TJMG/TJRS sem API documentada. O relatório não os recomenda antes de STJ/TJDFT.

## Arquitetura das correções

### P0 contrato de evidência (decisão 0037)

- `obter_decisao(id, parte, tribunal=None)`: busca por id interno; senão por
  `official_id` filtrado por tribunal quando informado; 0 linhas →
  `nao_encontrado_no_acervo` com `escopo: acervo_local`; >1 → `ambiguous` com a lista
  (tribunal, id). Parte ausente → `parte_indisponivel` com `partes_disponiveis`; nunca
  outro documento sob o rótulo pedido. Resposta passa a ter `parte_solicitada` e
  `parte_entregue` (iguais no sucesso).
- `inexistente` fica reservado a negativa oficial delimitada (regra já vigente para
  normas, decisão 0023).
- Espécie: `_species_from_meta(court, class, organ, kind=None)`; `kind` explícito da
  fonte (`decisao_monocratica`, `sumula`, `repercussao_geral`, `tema`) prevalece; conflito
  com a inferência fica em `attrs.conflito_especie`. Monocrática nunca recebe rótulo de
  acórdão ou órgão de cúpula.
- Tipo de documento: `inteiro_teor` só quando o perfil declara texto integral
  (`ParsedDecision.metadata["documento"] == "inteiro_teor"` ou perfil na lista
  `_PERFIS_INTEIRO_TEOR`); comprimento deixa de decidir.
- `DERIVED_VERSION` 4 (classificação recalculada); `fv acervo reconstruir` refaz.

### P1 atualização (decisão 0038)

- Checkpoint STJ passa a incluir `last_modified`/`metadata_modified`/`size` do CKAN.
  Mudança de metadado invalida o checkpoint. Os dois meses mais recentes são
  sempre rebaixados e comparados por sha256 (revalidação), independentemente do
  checkpoint. Bytes anteriores ficam preservados (arquivos por sha256). Estado expõe
  `ultima_tentativa`, `ultima_captura_ok`, `atraso_dias`.
- Súmulas STF: mesma política (metadado/hash da página), sem limpar checkpoint.

### P1 segurança e operação

- `isolated.py`: limites para todos os perfis; Windows via Job Object (ctypes,
  `JOB_OBJECT_LIMIT_PROCESS_MEMORY` + `KILL_ON_JOB_CLOSE`); leitura de stdout com teto
  (64 MiB) e morte do filho ao exceder.
- REST local: `Host` ∈ {127.0.0.1, localhost, ::1}[:porta]; `Origin` presente e não local
  → 403. Token continua opcional em loopback (MCP stdio é o caminho preferido).
- Registro: padrão `sem_conteudo`; digest HMAC-SHA256 com segredo aleatório em
  `<home>/registro.key` (0600).
- Snapshot: `freoa_verifica/data/snapshots-oficiais.json` com sha256 dos snapshots
  publicados; `fv snapshot install` recusa digest fora da lista salvo
  `--aceitar-nao-vinculado` (caminho explícito e registrado no resultado).
- Instalador: falha de qualquer etapa interrompe com a etapa nomeada; verificação final
  de versão, `snapshot info` e `doctor`; attestation conferida com `gh` quando presente.

### P1 cobertura: TJDFT

- Conector `tjdft` sobre `POST https://jurisdf.tjdft.jus.br/api/v1/pesquisa`
  (documentação oficial do tribunal). Busca ao vivo devolve candidatos com ementa
  oficial; o registro é a captura (bytes do JSON + sha256). Inteiro teor só quando o
  registro o traz ou quando o documento oficial associado é capturado; `possuiInteiroTeor`
  sozinho não promove. Espécie de `base`/`subbase` (`decisoes-monocraticas` →
  monocrática). Transporte central, host na lista branca, 1 req/s.
- Semente TJDFT temática (societário, mercado de capitais, empresarial) no snapshot.

### P2

- README e FONTES: uma tabela única do estado atual; histórico vai para o CHANGELOG.
- `sanitizacao`: documentação como triagem.

## Avaliação comparativa com o JusRatio

Conjunto-ouro montado sem leitura do código (Haiku, pesquisador de fontes), com a
resposta fixada pela fonte oficial e não pelo JusRatio. Estratos: dispositivos de lei
federal, normas CVM/BCB, súmulas STF/STJ, decisões STJ dentro do recorte do acervo,
TJDFT, TCU, CVM colegiado e itens inexistentes plantados. Métrica por caso: item
correto entre os 5 primeiros (localização), identidade correta, texto oficial
disponível, confirmação indevida. Critério: dentro do acervo, taxa de localização do
FREOA ≥ a do JusRatio (tolerância de um caso por estrato) e zero confirmação indevida;
fora do acervo, abstenção declarada conta como correta para o FREOA e não como
localização.

## Papéis e modelos

| Tarefa | Modelo | Motivo |
|---|---|---|
| Orquestração, P0, integração | Opus | contrato de evidência é o núcleo do produto |
| Debate de arquitetura e auditoria adversarial | Codex | auditor independente das rodadas anteriores |
| TJDFT, STJ revalidação, REST, registro | Sonnet | implementação delimitada por especificação |
| Isolamento Windows e instalador PowerShell | Codex no notebook | exige Windows real |
| Conjunto-ouro e coleta JusRatio | Haiku | volume, sem ler o código |
| Segunda leitura adversarial | Antigravity | perspectiva de outro fornecedor, se houver cota |
