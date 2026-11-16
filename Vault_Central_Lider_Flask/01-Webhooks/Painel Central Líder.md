---
recurso: Painel Central Líder
tipo: webhook
gatilho: "GET /webhook/central-lider"
arquivo: app/fluxos/status.py + app/static/index.html
versao_base: n8n v28
atualizado: 2026-11-16
tags: [webhook, painel]
---
# Painel Central Líder

## Para que serve
Tela única de operação: disparar o fluxo, acompanhar o progresso, resolver pendências, revisar e enviar mensagens, responder as Consultas da IA, tratar respostas tardias e recomeçar pedidos.

## Como usar
Abra http://127.0.0.1:6050/webhook/central-lider (no PC) ou pelo endereço do zrok. A raiz `/` dá 404 — é normal.

## O que o sistema faz
Devolve o HTML do painel da v28 sem mudanças (`app/static/index.html`). O painel chama os outros webhooks pelo mesmo endereço em que foi aberto.

## Diferenças da v28
Nenhuma.

## Como testar
Abrir o endereço e ver os cartões carregarem (eles vêm da [[API Pendências]]).

## Ligações
[[API Pendências]] · [[Status do disparo]] · [[Disparo do fluxo]] · [[Revisão de envio]] · [[Consultas da IA (consultor)]] · [[Recomeçar pedido]]
