---
recurso: Resolver pendência
tipo: webhook
gatilho: "POST /webhook/central-lider-resolver"
arquivo: app/fluxos/f1_resolver.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [webhook, fluxo1]
---
# Resolver pendência

## Para que serve
Tela de pendências: o consultor informa destino (cidade/UF/referência/telefone) de um pedido PENDENTE_DESTINO, ou manda tratar individualmente.

## O que o sistema faz
- **Destino informado:** aplica o destino e continua o Fluxo 1 do ponto de rota (coordenadas, prazo, contato, mensagem) → PENDENTE_REVISAO.
- **Tratar individualmente:** tira do fluxo e manda e-mail.
- Responde na hora; processa em segundo plano.

## Ligações
[[Disparo do fluxo]] · [[Revisão de envio]]
