-- As 6 Data Tables do n8n (v28), com os MESMOS nomes de coluna,
-- para a tradução dos nós Code ficar 1:1.
-- id / createdAt / updatedAt imitam as colunas automáticas do n8n.
-- Colunas de texto livre com JSON (dadosPedido, chatConsultor, dados) continuam TEXT.

CREATE TABLE IF NOT EXISTS AGUARDANDO_ENTREGA (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pedidoLider   TEXT NOT NULL UNIQUE,
    cliente       TEXT,
    responsavel   TEXT,
    status        TEXT,
    mensagem      TEXT,
    tipoMensagem  TEXT,
    template      TEXT,
    anexoUrl      TEXT,
    contactId     TEXT,
    phone         TEXT,
    serviceId     TEXT,
    enviadoEm     TEXT,
    respondidoEm  TEXT,
    resposta      TEXT,
    respostaData  TEXT,
    categoria     TEXT,
    resumoIA      TEXT,
    chatConsultor TEXT,
    vigiaAte      TEXT,
    dadosPedido   TEXT,
    createdAt     TEXT NOT NULL,
    updatedAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ae_status    ON AGUARDANDO_ENTREGA(status);
CREATE INDEX IF NOT EXISTS ix_ae_contactId ON AGUARDANDO_ENTREGA(contactId);

CREATE TABLE IF NOT EXISTS FLUXO_STATUS (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    disparoId TEXT,
    tipo      TEXT,
    no        TEXT,
    msg       TEXT,
    pct       TEXT,
    ts        REAL,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fs_disparo ON FLUXO_STATUS(disparoId);

CREATE TABLE IF NOT EXISTS HISTORICO_PEDIDOS (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    idOriginal     TEXT UNIQUE,
    dataReferencia TEXT,
    pedidoLider    TEXT,
    cliente        TEXT,
    responsavel    TEXT,
    status         TEXT,
    criadoEm       TEXT,
    atualizadoEm   TEXT,
    arquivadoEm    TEXT,
    dados          TEXT,
    createdAt      TEXT NOT NULL,
    updatedAt      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_hp_pedido ON HISTORICO_PEDIDOS(pedidoLider);

CREATE TABLE IF NOT EXISTS MENSAGENS_CLIENTE (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    contactId  TEXT,
    messageId  TEXT,
    papel      TEXT,          -- CLIENTE | Líder | BOT | RECOMECO
    texto      TEXT,
    recebidoEm TEXT,
    ts         REAL,
    createdAt  TEXT NOT NULL,
    updatedAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mc_contact ON MENSAGENS_CLIENTE(contactId, ts);

CREATE TABLE IF NOT EXISTS SEM_CONFIRMACAO_DIARIO (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pedidoLider  TEXT,
    cliente      TEXT,
    responsavel  TEXT,
    contactId    TEXT,
    dataRef      TEXT,
    status       TEXT,
    registradoEm TEXT,
    createdAt    TEXT NOT NULL,
    updatedAt    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sc_pedido ON SEM_CONFIRMACAO_DIARIO(pedidoLider, dataRef);

CREATE TABLE IF NOT EXISTS BASE_CONHECIMENTO (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pergunta     TEXT,
    resposta     TEXT,
    usos         INTEGER DEFAULT 0,
    ultimoUso    TEXT,
    criadoEm     TEXT,
    atualizadoEm TEXT,
    createdAt    TEXT NOT NULL,
    updatedAt    TEXT NOT NULL
);
