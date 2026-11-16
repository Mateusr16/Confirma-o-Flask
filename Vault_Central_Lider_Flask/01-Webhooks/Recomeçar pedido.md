---
recurso: Recomeçar pedido
tipo: webhook
gatilho: "POST /webhook/central-lider-recomecar"
arquivo: app/fluxos/recomecar.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [webhook, recomeco]
---
# Recomeçar pedido / Trocar número

## Para que serve
Recomeçar o atendimento de um pedido (ex.: cliente pediu para falar com outra pessoa, número errado) e devolvê-lo para a Revisão de envio.

## Como usar
Botão Recomeçar no cartão. Campos: **motivo** (obrigatório, mínimo 5 letras), novo telefone (opcional), nome de quem vai atender (opcional), aviso ao contato antigo (só com número novo) e confirmação para pedidos CONCLUIDO.

## O que o sistema faz
1. Valida: pedido existe uma vez só, não é AGRUPADO nem OUTLET, status permite recomeço, tem mensagem montada.
2. **Número novo:** procura nos 2 canais do DigiSac; se não acha, cria o contato com nome `CPF/CNPJ - CLIENTE-(nome)`. Se a busca falhar, nada é alterado.
3. Bloqueia se o número já está em atendimento em outro pedido.
4. Guarda o histórico do recomeço no pedido, troca a saudação ("Olá, Anete!"), limpa a conversa anterior → **PENDENTE_REVISAO**.
5. Marca o recomeço na conversa (a IA não mistura com o histórico antigo), envia o aviso ao contato antigo e atualiza os pedidos da mensagem única.

## Ligações
[[Revisão de envio]] · [[Integrações]]
