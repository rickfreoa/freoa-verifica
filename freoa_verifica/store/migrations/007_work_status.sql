-- C2: situação cadastral da obra lida de evidência própria capturada (decisão 0021).
CREATE TABLE work_status (
    work_id TEXT PRIMARY KEY REFERENCES work(id),
    situacao TEXT NOT NULL CHECK (situacao IN ('revogada','cancelada','vigente_declarada','ilegivel','nao_aplicavel')),
    texto_oficial TEXT,
    ato_revogador TEXT,
    data_efeito TEXT,
    captura_id TEXT REFERENCES capture(id),
    sha256 TEXT,
    lido_em TEXT NOT NULL
);
