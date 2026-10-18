# Publicação de versão

Antes da publicação, execute a suíte offline contra o wheel instalado com os
extras `test,server`, confira a versão e obtenha parecer independente sem bloqueador.
O snapshot contém somente fontes públicas e deve ser conferido separadamente.

1. Atualize versão e changelog. Crie e envie a tag correspondente (por exemplo,
   `v1.0.0`) após a autorização de publicação.
2. O workflow `release.yml`, disparado pela tag `v*`, constrói wheel e sdist,
   gera checksums, executa o smoke test, produz attestation de proveniência dos
   pacotes e os publica na release GitHub da mesma tag.
3. Gere o corpus com o pacote dessa versão e um diretório de dados dedicado:

   ```sh
   fv sync --semente
   fv snapshot export --arquivo-unico --saida freoa-verifica-snapshot-20261018.tar.gz
   ```

   A exportação produz o tar.gz único e seu arquivo `.tar.gz.sha256`. Preserve os
   motivos de indisponibilidade e confira cobertura, integridade, anos pendentes
   e resultados do bench antes de distribuir.
4. Instale o arquivo em um diretório de dados vazio com
   `fv snapshot install --arquivo freoa-verifica-snapshot-20261018.tar.gz`, execute
   `fv doctor --offline` e repita o bench. Confira o checksum externo.
5. Anexe os dois arquivos à mesma release do pacote:

   ```sh
   gh release upload v1.0.0 freoa-verifica-snapshot-20261018.tar.gz freoa-verifica-snapshot-20261018.tar.gz.sha256
   ```

   Não substitua silenciosamente um asset já publicado. Registre a identidade e
   os resultados de validação dos arquivos efetivamente anexados.

`fv snapshot install` sem argumentos consulta a última release, procura o asset
`freoa-verifica-snapshot-*.tar.gz` e baixa seu `.sha256` antes de validar o conteúdo.
A ausência de snapshot ou checksum é uma falha explícita. A attestation gerada pelo
workflow cobre wheel/sdist; o snapshot gerado separadamente não herda essa prova.
Checksums provam integridade, e a origem depende do canal da release.
