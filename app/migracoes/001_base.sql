-- Base do servidor. As 6 tabelas do negócio (AGUARDANDO_ENTREGA, FLUXO_STATUS,
-- HISTORICO_PEDIDOS, MENSAGENS_CLIENTE, SEM_CONFIRMACAO_DIARIO, BASE_CONHECIMENTO)
-- entram na migração 002, montada a partir das colunas usadas na v28.

-- Registro de cada execução (substitui a tela Executions do n8n)
CREATE TABLE IF NOT EXISTS execucoes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    gatilho   TEXT NOT NULL,
    status    TEXT NOT NULL,          -- ok | erro | ignorado | teste
    inicio    TEXT NOT NULL,
    fim       TEXT,
    detalhe   TEXT,                   -- JSON
    erro      TEXT
);
CREATE INDEX IF NOT EXISTS ix_execucoes_inicio ON execucoes(inicio);

-- Tudo que o MODO_TESTE deixou de enviar para fora (DigiSac, e-mail, intranet, planilha)
CREATE TABLE IF NOT EXISTS envios_simulados (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TEXT NOT NULL,
    destino   TEXT NOT NULL,          -- digisac | email | intranet | planilha
    acao      TEXT NOT NULL,
    payload   TEXT                    -- JSON
);

-- Substitui os nós Wait: o que ficou parado esperando alguém/algo
CREATE TABLE IF NOT EXISTS esperas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo        TEXT NOT NULL,
    chave       TEXT NOT NULL,        -- ex.: número do pedido
    dados       TEXT,                 -- JSON com o estado para retomar
    criado_em   TEXT NOT NULL,
    retomar_em  TEXT,                 -- quando a espera é por tempo
    resolvido_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_esperas_aberta ON esperas(tipo, resolvido_em);
