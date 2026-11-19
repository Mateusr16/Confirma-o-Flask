---
recurso: Resposta do cliente (DigiSac)
tipo: webhook
gatilho: "POST /webhook/digisac-resposta"
arquivo: app/fluxos/f2_resposta.py + f2_logica.py + prompts.py
versao_base: n8n v28
atualizado: 2026-11-19
tags: [webhook, fluxo2]
---
# Resposta do cliente (Fluxo 2)

## Para que serve
Recebe as mensagens do WhatsApp (webhook do DigiSac) e responde o cliente automaticamente.

## O que o sistema faz
1. Responde 200 na hora; o resto roda em segundo plano.
2. **Só trata contatos que o sistema atende** (pedido na AGUARDANDO_ENTREGA ou sem retorno nos últimos 30 dias). Os demais são descartados sem gravar.
3. Grava a mensagem, espera **60 s** para juntar mensagens seguidas e escolhe o pedido.
4. Conforme a etapa:
   - **TEMPLATE** (aceitou o botão): envia a mensagem programada (planejados: vídeo `arquivos/LIDER.mp4`) → DATA_ENVIADA;
   - **IA**: Gemini classifica (aceita, adiar, dúvida, não aceita…). Aceite → planilha + observação na intranet; adiamento → altera a data na intranet (próximo dia útil, com aviso de armazenagem); dúvida → base de conhecimento ou consultor;
   - **DECISAO_RESPONSAVEL**: sim → transfere ao responsável (só usuário ativo do departamento CENTRAL DE RELACIONAMENTO LIDER); não → conclui;
   - **CONSULTOR_MSG**: anexa a mensagem ao chat da consulta;
   - **VIGILANCIA**: já confirmou e o chamado está aberto → IA classifica e responde pela base ou abre consulta.

## Como testar
`python simular_resposta.py` (MODO_TESTE) ou WhatsApp real. Testado real em 13/11 (Ok! → mensagem programada) e 16/11 (adiamento 27/02/2027 → 24/05/2027; pediu 22/05, sábado).

## Ligações
[[Consultas da IA (consultor)]] · [[Varredura de vigilância]] · [[Integrações]] · [[Endereço público (zrok)]]
