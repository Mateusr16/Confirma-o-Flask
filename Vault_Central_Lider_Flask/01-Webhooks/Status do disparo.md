---
recurso: Status do disparo
tipo: webhook
gatilho: "GET /webhook/status-fluxo-lider?disparoId="
arquivo: app/fluxos/painel.py
versao_base: n8n v28
atualizado: 2026-11-19
tags: [webhook, painel]
---
# Status do disparo

## Para que serve
Barra de progresso do disparo no painel (percentual, etapa atual, log e erro).

## O que o sistema faz
Lê os eventos da tabela FLUXO_STATUS daquele `disparoId`.
- **Erro:** se houver evento de erro depois do início, a barra fica vermelha.
- **Concluído:** só quando o disparo grava o evento de fim (tipo `fim`), ao terminar de verdade. A linha "Fluxo concluído" mostra a hora real do fim.
- **Reserva:** se o evento de fim nunca chegar (servidor caiu no meio), conclui depois de **30 min** sem nenhum evento.
- Etapas longas (consulta dos pedidos na intranet e conferência de boletos) mostram o andamento, ex.: "Verificando boletos (12/40)", no máximo a cada 20 s. O % avança dentro da etapa.

## O que o operador vê
A barra só chega a 100 % quando o fluxo acabou. Enquanto a etapa de boletos roda, o contador (n/total) vai subindo.

## Diferenças da v28
Na v28 (regra v16) a tela concluía por inatividade: 60 s depois de 96 %, senão 7 min. A conferência de boletos passa de 7 min sem gravar evento, e a tela mostrava 100 % com o fluxo ainda rodando (caso de 19/11/2026).

## Como testar
`test_f1_ponta_a_ponta.py` confere o evento de fim no disparo completo e a ausência dele quando o disparo falha.

## Status e tabelas
Lê [[Banco SQLite|FLUXO_STATUS]].

## Ligações
[[Disparo do fluxo]] · [[Painel Central Líder]]
