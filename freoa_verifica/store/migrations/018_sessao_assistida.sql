-- 0089: modalidade sobrevive à procedência snapshot; recibo sem cookie/headers de pedido.
ALTER TABLE capture ADD COLUMN modalidade_acesso TEXT;
ALTER TABLE capture ADD COLUMN assistida_json TEXT;
CREATE TABLE tentativa_assistida (
    fonte TEXT NOT NULL,
    operacao TEXT NOT NULL,
    em TEXT NOT NULL,
    prova TEXT,
    alvo TEXT,
    PRIMARY KEY(fonte, operacao)
);
