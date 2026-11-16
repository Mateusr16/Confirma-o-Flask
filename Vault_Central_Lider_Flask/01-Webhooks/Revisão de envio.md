---
recurso: Revisão de envio
tipo: webhook
gatilho: "POST /webhook/central-lider-revisao"
arquivo: app/fluxos/f1_revisao.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [webhook, fluxo1]
---
# Revisão de envio (Decisão de envio)

## Para que serve
"Enviar agora" / "Não enviar" de cada mensagem (pode editar o texto antes), e a decisão da tela **Respostas tardias**.

## O que o sistema faz
1. Grava a decisão (mensagem editada fica guardada com a original).
2. Confere o chamado do cliente no DigiSac:
   - **livre ou já comigo** → espera ~5 s, envia o template (botão), transfere o chamado ao departamento Central / meu usuário → **AGUARDANDO**;
   - **com outro atendente / na fila** → **AGUARDANDO_CHAMADO_LIVRE** (o agendamento [[Chamados ocupados]] tenta de novo).
3. O painel espera a resposta (síncrono).

## Diferenças da v28
Nenhuma.

## Como testar
Testado real em 13/11: envio normal e chamado ocupado → liberado 30 min depois.

## Ligações
[[Chamados ocupados]] · [[Resposta do cliente (DigiSac)]] · [[Varredura de respostas tardias]]
