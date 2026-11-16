---
recurso: Chamados ocupados
tipo: agendamento
gatilho: "a cada 30 min"
arquivo: app/fluxos/ag_chamados_ocupados.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [agendamento]
---
# Chamados ocupados

## Para que serve
Envia o template dos pedidos que ficaram em **AGUARDANDO_CHAMADO_LIVRE** assim que o chamado do cliente fica livre.

## O que o sistema faz
Em horário comercial (seg-sex 08:00–17:30), confere de novo cada chamado no DigiSac (~5 s entre contatos). Livre → template + transferência → AGUARDANDO. Ocupado → anota a verificação.

## Como usar
Só roda com `AGENDADOR_ATIVO=true`. Para rodar na hora: `Invoke-RestMethod -Method Post http://127.0.0.1:6050/api/rodar/chamados_ocupados`. Use `?forcar=1` para ignorar o horário comercial.

## Diferenças da v28
Nenhuma. Testado real em 13/11.

## Ligações
[[Revisão de envio]] · [[Encerramento sem retorno]]
