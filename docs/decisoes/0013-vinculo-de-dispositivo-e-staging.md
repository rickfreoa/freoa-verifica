# Vínculo explícito de dispositivo e staging configurável

Um dispositivo posterior só se associa à norma quando separado dela por vírgula ou travessão, na mesma oração. Ponto final, ponto e vírgula, quebra de parágrafo e conjunção que inicia outra oração impedem a associação. Uma quebra simples de linha após a vírgula continua permitida. Listas explícitas de dispositivos conservam seus caminhos individuais.

O complemento `do`, `da` ou `de` seguido de contrato, contrato social, estatuto, estatuto social, acordo de acionistas, edital, regulamento interno, termo, ata, parecer, petição, voto ou instrumento identifica um dispositivo desse instrumento. Ele não recebe identidade normativa por proximidade, antes ou depois de uma norma. As formas `Instr. CVM`, `Inst. CVM` e `IN CVM` identificam Instrução CVM.

O corpus independente de 80 frases é preservado literalmente como fixture. As regressões exigem zero falso positivo de identidade completa e recall explícito mínimo de 98%. Esses controles não alteram os requisitos de evidência nem os critérios de `verified`.

Exportação, download, extração e instalação de snapshots usam staging sob o diretório de dados, na subpasta `staging`. A variável `FV_STAGING_DIR` permite configurar outra raiz; a função de exportação também aceita `staging_dir`. Para manter as trocas atômicas na instalação, a raiz configurada deve ficar no mesmo volume do acervo. Cada operação cria uma subpasta exclusiva e a remove ao encerrar, inclusive em falhas.

Os testes direcionam staging para `tmp_path`. No Windows, a fábrica desse fixture cria diretórios com ACL herdada da raiz de testes, evitando a ACL privada de `mode=0700` incompatível com certos tokens restritos. Nenhum staging depende do temporário global do sistema.
