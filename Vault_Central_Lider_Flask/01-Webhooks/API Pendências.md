---
recurso: API Pendências
tipo: webhook
gatilho: "GET /webhook/central-lider-pendencias"
arquivo: app/fluxos/painel.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [webhook, painel]
---
# API Pendências

## Para que serve
Alimenta todas as telas do painel com os pedidos da AGUARDANDO_ENTREGA.

## O que o sistema faz
Devolve todas as linhas com pedido e status, com `criadoEm` e a marca `statusConhecido`. Também serve para conferir o estado de um pedido sem abrir o banco (ex.: no navegador).

## Diferenças da v28
Nenhuma.

## Ligações
[[Painel Central Líder]] · [[Glossário de status]]
