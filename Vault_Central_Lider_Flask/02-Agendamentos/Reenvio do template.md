---
recurso: Reenvio do template
tipo: agendamento
gatilho: "seg-sex 13:20"
arquivo: app/fluxos/ag_rotinas.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [agendamento]
---
# Reenvio do template

## Para que serve
Reenviar o template (botão) a quem não aceitou o primeiro.

## O que o sistema faz
Pedidos em **AGUARDANDO**, template enviado entre 1 h e 72 h atrás, ainda não reenviados. Um reenvio por contato. Confere o chamado (livre ou comigo), reenvia e marca `template = conf002_reenvio`.

## Como usar
Só roda com `AGENDADOR_ATIVO=true`. Para rodar na hora: `Invoke-RestMethod -Method Post http://127.0.0.1:6050/api/rodar/reenvio_template`.

## Ligações
[[Revisão de envio]] · [[Encerramento sem retorno]]
