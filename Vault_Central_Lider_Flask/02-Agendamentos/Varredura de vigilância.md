---
recurso: Varredura de vigilância
tipo: agendamento
gatilho: "a cada 10 min"
arquivo: app/fluxos/ag_rotinas.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [agendamento]
---
# Varredura de vigilância

## Para que serve
Fecha os chamados depois que a conversa terminou e cobra o consultor das consultas paradas.

## O que o sistema faz
- **CONCLUIDO com vigilância vencida** → fecha o chamado no DigiSac (falhou: e-mail de alerta).
- **Vigilância vencida em outro status** (ex.: transferido) → só limpa a vigilância; o chamado fica aberto.
- **AGUARDANDO_CONSULTOR** há mais de 1 h → e-mail de lembrete; repete a cada 3 h, no máximo 4 vezes.
Tudo é anotado no chat da consulta.

## Como usar
Só roda com `AGENDADOR_ATIVO=true`. Para rodar na hora: `Invoke-RestMethod -Method Post http://127.0.0.1:6050/api/rodar/varredura_vigilancia`.

## Ligações
[[Consultas da IA (consultor)]] · [[Resposta do cliente (DigiSac)]] · [[Logs e alertas]]
