# 0034 - Monotonia estrutural das obras de texto compilado

Data: 18/10/2026. Rodada 7 do auditor.

Texto compilado (Planalto, CVM consolidado, BCB) não apaga dispositivos: revogados permanecem, riscados ou anotados. Uma captura nova cujo modelo PERDE caminhos (escopo + caminho) presentes no modelo canônico vigente da mesma obra não é promovida: fica como captura não canônica (`candidato_ao_vivo=1`), com motivo `PERDA_ESTRUTURAL` em `divergentes`, e o modelo canônico anterior permanece. A regra independe da origem da captura, o que fecha a classe (candidato sem marca em home de esquema 8/9, snapshot, reprocessamento).

- Núcleo: `store.repo.avaliar_monotonia` percorre as capturas não candidatas da obra da mais antiga à mais nova; captura que só acrescenta caminhos ou muda textos vira o canônico vigente.
- Aplicação: `service.indexar_obra` (captura nova de obra existente vai ao staging e devolve o canônico), `_rebuild_from_db` (escolhe a captura canônica mais recente, mesmo sem marca persistida), `reprocessar_capturas`/`reconstruir`, `derivados.reindexar_fts` e instalação de snapshot (marcam e informam em `divergentes`).
- Rede de segurança em C1: `pode_negar` devolve `unknown ESTRUTURA_DIVERGENTE_ENTRE_CAPTURAS` se qualquer captura canônica da obra tem o caminho (`ResolvedWork.caminhos_conhecidos`).
- Exceção: primeira captura da obra é promovida normalmente. Limite: um recorte legítimo de dispositivos pela fonte (reforma que realmente exclua artigo do compilado) fica retido como não canônico até decisão humana; nunca se desmarca automaticamente.
