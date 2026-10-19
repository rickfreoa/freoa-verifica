# Segurança

Reporte vulnerabilidades em privado para rickfreoa@gmail.com, com descrição, passos de reprodução e impacto. Não abra issue pública antes da correção.

Escopo prioritário: SSRF ou fuga da allowlist do transporte; resultado `verified` indevido (falso positivo de identidade, texto ou tempo); vazamento de dados locais por snapshot, API ou MCP; execução de conteúdo de documento; negação de serviço por documento hostil.

A API REST recusa bind fora de `localhost` sem token. O servidor MCP não expõe URL arbitrária nem escrita administrativa.

## Isolamento de parsers (1.2.0)

O próprio filho instala limites antes de ler a entrada: PDF 1024 MiB / 60 s CPU;
demais perfis 2048 MiB / 120 s CPU. Falha de instalação encerra o filho (78) e
produz quarentena. Windows usa Job Object (memória comprometida, CPU de usuário,
um processo ativo, encerramento ao fechar o job e em exceção não tratada).
POSIX usa RLIMIT_AS e RLIMIT_CPU; RLIMIT_NPROC=0 quando disponível e UID não root.
Root/capabilities podem ignorar NPROC; não são uma configuração segura de serviço.
RLIMIT_AS mede espaço virtual, não RSS. Tempo de parede continua limitado pelo pai.
Entrada: 200 MiB; stdout: 64 MiB; stderr: 64 KiB; excesso mata o filho e põe o
documento em quarentena. Os limites também se aplicam a não PDFs.

**Não há contenção de rede, sistema de arquivos ou privilégios do filho.** Job Object
não é sandbox de segurança. Serviço remoto exige contêiner com rede desabilitada,
FS somente leitura e usuário sem privilégios. Exemplo (imagem previamente construída,
sem volumes privados, comando de processamento offline):

```sh
docker run --rm --network none --read-only --user 10001:10001 \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 32 \
  --memory 3g --cpus 1 --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  freoa-verifica:1.2.0 fv --home /tmp/acervo doctor --offline --json
```

Um serviço que precise buscar fontes deve separar captura autorizada e parsing offline;
o contêiner de parsing continua sem rede. O exemplo não provisiona um servidor público.

## Vínculo de snapshot e instalação

A lista `freoa_verifica/data/snapshots-oficiais.json` vincula SHA-256 do arquivo
publicado ao pacote. Isso autentica origem apenas quando o pacote foi autenticado;
não prova mérito jurídico. Digest externo no mesmo canal só confere integridade.
Diretórios e arquivos locais recém-exportados exigem `--aceitar-nao-vinculado`;
manifesto local, `snapshot info` e `doctor` conservam `vinculado: false`.
`latest` só seleciona assets conhecidos na lista; o download confere os bytes antes
de extrair. Snapshot com derivados anteriores exige reconstrução no staging antes
de publicar o acervo, mesmo quando seu arquivo é oficial.

O instalador Windows 1.2.0 verifica wheel (e lock, quando presente) por GitHub
attestation se houver `gh`; falha encerra a instalação. Sem `gh`, declara e registra
`PROVENIENCIA NAO VERIFICADA (instale o GitHub CLI para verificar)` em
`%LOCALAPPDATA%\freoa-verifica\instalacao.json`. Constraints limitam versões;
não autenticam por si só os artefatos transitivos baixados pelo pip.
