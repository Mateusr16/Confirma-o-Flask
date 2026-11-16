---
recurso: Encerramento sem retorno
tipo: agendamento
gatilho: "16:20 seg-qui / 15:20 sex"
arquivo: app/fluxos/ag_rotinas.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [agendamento]
---
# Encerramento sem retorno (encerramento de pendências)

## Para que serve
No fim do dia, encerra quem não respondeu.

## O que o sistema faz
1. Lê a planilha: linhas com CONFIRMADO, MOTIVO e DATA ENVIO CONF. vazios.
2. Encerra pedidos em AGUARDANDO (não aceitou o template), DATA_ENVIADA (não respondeu) ou AGUARDANDO_CHAMADO_LIVRE (chamado ocupado o dia todo). Pedidos com responsável nunca são encerrados; pedidos agrupados seguem o principal.
3. Fecha o chamado (1 por contato), exceto se o contato tem outro pedido com consultor/responsável. Chamado ocupado: só fecha se, conferindo na hora, estiver na fila ou comigo.
4. Planilha: CONFIRMADO = NÃO, MOTIVO = SEM RETORNO CLIENTE.
5. Pedido → **SEM_RETORNO_CLIENTE**; anota em SEM_CONFIRMACAO_DIARIO (conta para a reincidência e para a resposta tardia).

## Como usar
Só roda com `AGENDADOR_ATIVO=true`. Para rodar na hora: `Invoke-RestMethod -Method Post http://127.0.0.1:6050/api/rodar/encerramento_pendencias`.

## Diferenças da v28
Usa a aba da planilha do `.env` (Página3).

## Ligações
[[Varredura de respostas tardias]] · [[Chamados ocupados]] · [[Integrações]]
