---
recurso: Logs e alertas
tipo: infraestrutura
gatilho: "logs/central.log"
arquivo: app/registro.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [infra]
---
# Logs e alertas

- Log diário em `logs/central.log` (gira por dia). Cada resposta do cliente aparece como `Resposta do cliente <contato>: fluxo <X> (pedido <N>)`.
- Erro não tratado em webhook ou agendamento: registrado na tabela `execucoes` e e-mail para `EMAIL_ALERTA_ERRO` (fora do modo teste) — equivale ao "Erro no fluxo" da v28.
- Diagnóstico rápido: se o template saiu e o cliente não foi respondido, procurar "Resposta do cliente" no log; se não existir, a mensagem não chegou ao Flask → ver [[Endereço público (zrok)]].

## Ligações
[[Rodar o servidor]] · [[Endereço público (zrok)]]
