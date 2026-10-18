# 0010 — Normalização mínima da busca local

Implementa a especificação de flexão mínima para consultas FTS5 de legislação e jurisprudência: termos livres normalizados, stopwords removidas e prefixos com no mínimo quatro letras; frases exatas; AND seguido de OR apenas na ausência de correspondência, com modo ampliado explícito. A decisão de ampliação precede a paginação e preserva os filtros. A semântica completa e os limites estão na seção Busca da arquitetura.

A regra melhora a recuperação de singular e plural sem inferência semântica. Prefixos podem aumentar o ruído e raízes curtas não são expandidas. Não altera critérios de verificação. Testes unitários e integração sintética cobrem ambos os caminhos de busca.
