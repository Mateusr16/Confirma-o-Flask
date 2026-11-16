---
recurso: Banco SQLite
tipo: infraestrutura
gatilho: "dados/*.db"
arquivo: app/db.py, app/tabelas.py, app/migracoes/
versao_base: n8n v28
atualizado: 2026-11-16
tags: [infra]
---
# Banco SQLite

Tabelas com os mesmos nomes e colunas das Data Tables da v28: **AGUARDANDO_ENTREGA**, **MENSAGENS_CLIENTE**, **SEM_CONFIRMACAO_DIARIO**, **HISTORICO_PEDIDOS**, **BASE_CONHECIMENTO**, **FLUXO_STATUS**; mais `execucoes` (cada webhook/agendamento), `envios_simulados` e `esperas`.

- Modo WAL; mudanças novas entram por arquivos em `app/migracoes/`.
- **Não abrir o `.db` no DB Browser com o servidor rodando** (trava o banco: "database is locked"). Use "somente leitura" ou a [[API Pendências]].
- Mensagens guardadas só de contatos atendidos; mais de 30 dias são apagadas na limpeza diária.

## Ligações
[[Glossário de status]] · [[Rodar o servidor]]
