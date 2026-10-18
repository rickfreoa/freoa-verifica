-- Pendências de identidade preservadas no snapshot, sem modificar capturas.
CREATE TABLE work_year_issue (
    work_id TEXT PRIMARY KEY REFERENCES work(id),
    reason TEXT NOT NULL,
    capture_id TEXT REFERENCES capture(id)
);
