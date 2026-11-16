---
recurso: Disparo do fluxo
tipo: webhook
gatilho: "POST /webhook/disparar-fluxo-lider"
arquivo: app/fluxos/f1_disparo.py (+ f1_extracao.py, f1_mensagens.py)
versao_base: n8n v28
atualizado: 2026-11-16
tags: [webhook, fluxo1]
---
# Disparo do fluxo (Fluxo 1)

## Para que serve
Prepara a confirmação de entrega de todos os pedidos da planilha do dia.

## Como usar
Botão de disparo no painel. O webhook responde na hora (`Workflow was started`) e o processamento roda em segundo plano; o progresso aparece no [[Status do disparo]]. Só um disparo roda por vez.

## O que o sistema faz
1. Limpeza diária (eventos antigos, histórico; mensagens com mais de 30 dias).
2. Lê a planilha (aba **Página3**) e anota cada pedido como EM_PROCESSAMENTO.
3. Login na intranet e consulta de cada pedido. Se a intranet devolver a tela de login, para com erro (não marca nada como cancelado).
4. Marca cancelados e entregues.
5. Boletos: trava de boleto e regra dos 50 % (pode alterar a data na intranet e avisar vendedor/expedição por e-mail).
6. Outlet: confirma sem contato.
7. Tipo de móvel, depósito, coordenadas (Nominatim) e distância (OSRM) → data prevista. Sem depósito/rota → PENDENTE_DESTINO.
8. Reincidência sem retorno e resposta tardia.
9. Busca o contato no DigiSac (2 canais, últimos 8 dígitos) ou cria.
10. Monta a mensagem (soltos / planejados com vídeo) e junta pedidos do mesmo cliente numa mensagem única → PENDENTE_REVISAO.

## Status e tabelas
AGUARDANDO_ENTREGA, FLUXO_STATUS, HISTORICO_PEDIDOS, SEM_CONFIRMACAO_DIARIO.

## Como testar
Disparo real com um pedido de teste na Página3 (ex.: 97680) e conferir o cartão na Revisão de envio.

## Ligações
[[Resolver pendência]] · [[Revisão de envio]] · [[Integrações]] · [[Status do disparo]]
