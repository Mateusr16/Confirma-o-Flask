---
recurso: Varredura de respostas tardias
tipo: agendamento
gatilho: "seg-sex 08:05 e 60 s depois de ligar"
arquivo: app/fluxos/ag_rotinas.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [agendamento]
---
# Varredura de respostas tardias

## Para que serve
Recuperar o que o cliente mandou enquanto o sistema não ouvia (servidor desligado, zrok fora, encerramento já feito).

## O que o sistema faz
1. Alvos: pedidos encerrados sem retorno no **último dia com encerramento** (segunda olha sexta) e pedidos de dias anteriores que ficaram em AGUARDANDO / DATA_ENVIADA / AGUARDANDO_CHAMADO_LIVRE (o encerramento não rodou).
2. Busca as mensagens de cada contato no DigiSac (até 10 páginas).
3. Grava na conversa as mensagens do cliente que não chegaram pelo webhook.
4. Cliente respondeu → cartão na tela **Respostas tardias** (PENDENTE_RESPOSTA_TARDIA) com as respostas e o contexto; o diário passa a RESPONDEU_DEPOIS.
5. Pedido aberto de dia anterior sem resposta → encerra como sem retorno (mesmo caminho do [[Encerramento sem retorno]], com o dia do pedido).
Se a consulta ao DigiSac falhar para um contato, ele fica para a próxima varredura.

## Como usar
Só roda com `AGENDADOR_ATIVO=true`. Para rodar na hora: `Invoke-RestMethod -Method Post http://127.0.0.1:6050/api/rodar/varredura_tardia`. Também roda sozinha 60 s depois que o servidor sobe (agendador ligado).

## Ligações
[[Encerramento sem retorno]] · [[Revisão de envio]] · [[Consultas da IA (consultor)]]
