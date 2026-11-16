---
recurso: Status do disparo
tipo: webhook
gatilho: "GET /webhook/status-fluxo-lider?disparoId="
arquivo: app/fluxos/painel.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [webhook, painel]
---
# Status do disparo

## Para que serve
Barra de progresso do disparo no painel (percentual, etapa atual, log e erro).

## O que o sistema faz
Lê os eventos da tabela FLUXO_STATUS daquele `disparoId`. Marca **erro** se houver evento de erro depois do início; marca **concluído** por inatividade (60 s depois de 96 %, senão 7 min).

## Status e tabelas
Lê [[Banco SQLite|FLUXO_STATUS]].

## Ligações
[[Disparo do fluxo]] · [[Painel Central Líder]]
