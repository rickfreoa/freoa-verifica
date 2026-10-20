# Publicação de versão

Antes da publicação, execute a suíte offline contra o wheel instalado com os
extras `test,server`, confira a versão e obtenha parecer independente sem bloqueador.
O snapshot contém somente fontes públicas e deve ser conferido separadamente.

1. Atualize versão e changelog. Crie e envie a tag correspondente (por exemplo,
   `v1.0.0`) após a autorização de publicação.
2. O workflow `release.yml`, disparado pela tag `v*`, constrói wheel e sdist,
   gera checksums, executa o smoke test, produz attestation de proveniência dos
   pacotes e os anexa a uma release GitHub da mesma tag criada como **rascunho**
   (ver "Sequência de release").
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

## Sequência de release

1. Congelar código funcional e versão na integração; registrar o commit.
2. Instalar a wheel local em ambiente limpo; reconstruir o acervo sobre cópia do corpus candidato, exportar o
   snapshot e instalá-lo de forma **experimental** (`--aceitar-nao-vinculado`) em home descartável; conferir
   integridade, `fv doctor --offline` e bench. Bateria S4 (decisão 0057, somente leitura): no corpus candidato,
   `fv acervo conferir --home <candidato> --recorte-desde AAAA-MM-DD --recorte-ate AAAA-MM-DD --estrito
   --gravar-manifesto manifesto.json` (sem defeito nem pendência); na instalação experimental,
   `fv acervo conferir --home <descartável> --manifesto manifesto.json --estrito`, que deve sair com 0.
3. Congelar os bytes exportados, gravar o digest em `freoa_verifica/data/snapshots-oficiais.json` e commitar.
   Repetir a instalação, agora vinculada, em home vazio.
4. Auditoria independente sobre esse commit (manifesto, instalador, digest, código).
5. PR para `main` com CI verde nas oito combinações (Python 3.11–3.14 × Ubuntu e Windows), merge e tag `vX.Y.Z`
   sobre o commit auditado. `release.yml` constrói com dependências travadas e cria a release como **rascunho**
   (`gh release create --draft`) com wheel, sdist, lock, `SHA256SUMS` e attestation. Ele não publica na PyPI.
6. Auditoria dos bytes da CI: baixar os assets do rascunho, conferir `SHA256SUMS` e a attestation
   (`gh attestation verify <arquivo> --repo rickfreoa/freoa-verifica`), o conteúdo da wheel (sem `tests/`,
   digest do snapshot embutido igual ao auditado) e instalar a wheel baixada em ambiente limpo, com o snapshot
   auditado; repetir `fv acervo conferir --manifesto manifesto.json --estrito` sobre esse home. Anexar ao rascunho
   exatamente o snapshot auditado e seu `.sha256` (`gh release upload`, sem substituir asset) e só então publicar
   (`gh release edit vX.Y.Z --draft=false`).
7. A publicação dispara `pypi.yml` (`release: published`): ele baixa os assets da própria release, confere
   `SHA256SUMS` e a attestation, exige uma wheel e um sdist (sem `tests/` na wheel) e publica esses bytes por
   Trusted Publishing, com `environment: pypi`. Roda só com `vars.PYPI_PUBLICAR == 'true'` e com o publicador
   cadastrado em pypi.org (projeto `freoa-verifica`, workflow `pypi.yml`, ambiente `pypi`); sem isso é pulado.
8. Instalar pelo instalador oficial e conferir attestation, digest, vínculo, `doctor` e um smoke de pesquisa.

O `requirements-lock.txt` da release é cópia de `requirements/ci.lock` (instalado com `--require-hashes` no smoke
test), não uma resolução posterior.

Locks: `scripts/atualizar_lock.ps1` (ou `.sh`) regera `requirements/*.lock`; commitar o resultado.
