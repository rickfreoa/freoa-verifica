-- Checkpoint de sincronização do corpus semente (M6).
-- Não entra no inventário público do snapshot.

CREATE TABLE sync_state (
    id TEXT PRIMARY KEY,
    fonte TEXT NOT NULL,
    chave TEXT NOT NULL,
    status TEXT NOT NULL,
    motivo TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    payload_json TEXT,
    UNIQUE (fonte, chave)
);

CREATE INDEX idx_sync_state_fonte_status ON sync_state(fonte, status);
