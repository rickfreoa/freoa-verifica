BLOQUEADORES

Nenhum bloqueador material da **instalação da etapa 7** identificado. Este parecer não conclui o I1 inteiro.

IMPORTANTES

- Em [aceite-i1.md:21](/C:/dev/fv14-aceite/docs/auditoria/1.4.0/aceite-i1.md:21), “mostra a causa” e “Não é falha do produto” excedem a prova. Confirmei suspensão às 09:56, retomada às 10:56, pedido de desligamento às 11:04 e boot às 11:08. O código `1073807364 = 0x40010004` é compatível com término externo; esses elementos sustentam essa explicação, mas não excluem problema anterior de desempenho. Recomendo: **“Interrupção compatível com encerramento externo; não há defeito do produto demonstrado.”**
- O invólucro verifica PID para remover marcadores, mas apaga **todos** os diretórios `staging/fv-snap-*`, sem verificar proprietário, atividade ou adquirir a trava do home. Portanto, “remove só artefatos da tentativa morta” não é uma garantia do código. A limpeza é aceitável como recuperação pontual após o reboot nas circunstâncias relatadas; não encontrei contorno das verificações de autenticidade ou integridade.
- [acceptance_manifest.json:78](/C:/dev/fv14-aceite/release/acceptance_manifest.json:78) ainda registra `7_instalacao` como pendente, sem evidências. A instalação está materialmente comprovada; o fechamento formal do incremento exige incorporar seu registro ao manifesto, conforme a seção 5.

MENORES

- A questão do tempo de anexação está corretamente mantida aberta: não demonstra defeito nem sua ausência. Confirmei a reprodução registrada de **139,0 s**, FTS **47,4 s**, índice **47,8 s**, **zero divergências**. Os logs apresentados não permitem confirmar isoladamente os tempos aproximados de 18 e 6 minutos.
- O log registra início da limpeza às **11:40:36**, início do roteiro às **11:41:04** e término às **12:01:32**. Não há timestamp específico que comprove o término do instalador às 11:59.
- O roteiro usa `ErrorActionPreference = Continue`; sua conclusão não comprova sucesso por si. Neste caso, há registro explícito de `instalador exit=0` e estado final coerente.

VALIDAÇÃO

- **Registro:** cópia e arquivo real coincidem; `concluida: true`, versão `1.4.0a1`, `attestation_verificada: true` e commit `6ac49ee520afcd37c26e2f9e640952dd7ea2da8a`, igual ao commit da tag.
- **Wheel:** SHA-256 calculado `66446a0a265cbd42a5bfea3ff46a20e5f0298445825ce95d38b22e9f17ab4b8f`, igual ao `SHA256SUMS`, ao registro e à wheel ao lado do instalador. Os 92 arquivos comparáveis instalados coincidem; somente `RECORD` difere, como esperado da instalação pelo pip.
- **Snapshot:** SHA-256 calculado `ad090c341b5e95c606309bff84ef9a233e144d223bcb5c6a40a9076dc3d8fafa`, igual ao `.sha256`, ao registro e à lista embutida tanto na tag quanto na wheel. Metadados do manifesto interno são coerentes com o manifesto fornecido.
- **Fluxo oficial:** script do checkout coincide com a tag. Não há `-SemAttestation` nem opção para aceitar snapshot não vinculado. O fluxo exige attestation, verifica o lock, instala com hash e valida vínculo, derivados e doctor antes de gravar conclusão. O lock local também coincide com o hash da release. A attestation foi avaliada pelo código e pelos registros existentes; não reexecutei sua verificação remota.
- **Saneamento:** reproduzi em memória os dois logs a partir dos originais, obtendo correspondência integral após as substituições declaradas e a omissão de 34 linhas do pip em cada um. Não identifiquei caminhos pessoais, credenciais ou identificadores de máquina remanescentes. As omissões retiram detalhes das dependências satisfeitas, mas preservam os elementos necessários a este parecer.
- Nenhum arquivo editado; instalador e suíte não reexecutados.

SEM BLOQUEADOR