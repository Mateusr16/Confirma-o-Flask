---
recurso: Lembrete de confirmação 13h
tipo: agendamento
gatilho: "seg-sex 13:00"
arquivo: app/fluxos/ag_rotinas.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [agendamento]
---
# Lembrete de confirmação (13h)

## Para que serve
Cobrar, uma vez, quem aceitou o template, recebeu a mensagem de confirmação e não respondeu.

## O que o sistema faz
1. Seleciona contatos com pedido em **DATA_ENVIADA**, sem resposta, mensagem enviada entre 1 h e 23 h atrás (janela de 24 h do WhatsApp) e sem lembrete anterior. Pula o contato se tiver outro pedido em atendimento.
2. Monta: "Boa tarde, Rafi! Podemos confirmar a data de entrega do pedido nº *97680*?" (1ª confirmação de planejados: pede para confirmar o recebimento). Cita todos os pedidos da mensagem única.
3. Antes de enviar, confere de novo: o chamado tem de estar comigo e o pedido não pode ter mudado.
4. Envia, grava `lembreteConfirmacaoEm` no pedido e o lembrete na conversa (papel BOT).

## Como usar
Só roda com `AGENDADOR_ATIVO=true`. Para rodar na hora: `Invoke-RestMethod -Method Post http://127.0.0.1:6050/api/rodar/lembrete_13h`.

## Ligações
[[Resposta do cliente (DigiSac)]] · [[Encerramento sem retorno]]
