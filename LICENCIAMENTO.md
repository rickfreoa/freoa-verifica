# Licenciamento

O FREOA Verifica adota três regimes, porque código, dados e textos oficiais não se submetem à mesma disciplina jurídica.

## 1. Código: AGPL-3.0-or-later, com licença comercial alternativa

O código-fonte é distribuído sob a GNU Affero General Public License, versão 3 ou posterior (arquivo `LICENSE`). Qualquer pessoa pode usar, estudar, modificar e redistribuir o programa sem custo. Quem o oferecer a terceiros por rede, inclusive como API ou servidor MCP hospedado, deve disponibilizar o código-fonte correspondente, com as modificações (AGPL, § 13).

O titular oferece **licença comercial** a quem não puder ou não quiser cumprir essas condições, por exemplo para integrar o motor a produto fechado ou prestar serviço hospedado sem abrir modificações. Contato: rickfreoa@gmail.com.

A dupla licença pressupõe titularidade concentrada. Por isso, contribuições externas exigem a aceitação prévia do `CLA.md`.

## 2. Dados derivados (snapshots de corpus): regime por fonte

| Fonte | Regime aplicável ao conjunto derivado |
|---|---|
| Textos de leis, decretos, atos normativos e decisões judiciais ou administrativas | Domínio público quanto ao texto (Lei 9.610/1998, art. 8º, IV) |
| CVM, dados abertos (ex.: processo sancionador) | ODbL 1.0, com compartilhamento pela mesma licença do banco derivado que os contenha |
| STJ, dados abertos | CC BY, com atribuição obrigatória ao Superior Tribunal de Justiça |
| Metadados, índices, relações e eventos temporais produzidos pelo projeto | ODbL 1.0 (banco) e CC BY 4.0 (conteúdos individuais), na medida em que exista direito a licenciar |

Cada snapshot publicado traz `MANIFEST.json` com origem, data de captura e hash de cada documento, além das atribuições exigidas.

## 3. Dependências

Dependências obrigatórias de licença permissiva compatível: lxml (BSD), pypdf (BSD), mcp (MIT). Extras opcionais: FastAPI e Uvicorn (MIT/BSD), PyMuPDF (AGPL-3.0, com licença comercial própria da Artifex, por isso fora do núcleo).

## 4. Dados pessoais

Decisões publicadas contêm dados pessoais. O projeto não indexa processos sob segredo, preserva a forma oficial de publicação e atende pedidos de remoção de cópias derivadas nos termos da LGPD.

Este documento descreve a política do projeto e não constitui parecer jurídico.
