---
projeto: Central Líder (Flask)
atualizado: 2026-11-16
tags: [glossario]
---
# Glossário de status (coluna `status` da AGUARDANDO_ENTREGA)

| Status | Significado | Quem coloca |
|---|---|---|
| EM_PROCESSAMENTO | pedido lido da planilha, disparo em andamento | [[Disparo do fluxo]] |
| PENDENTE_DESTINO | sem depósito/rota automática; espera o consultor | [[Disparo do fluxo]] |
| PENDENTE_REVISAO | mensagem pronta, espera "Enviar agora" | [[Disparo do fluxo]], [[Resolver pendência]], [[Recomeçar pedido]] |
| AGUARDANDO_CHAMADO_LIVRE | chamado do cliente com outro atendente; template não saiu | [[Revisão de envio]] |
| AGUARDANDO | template enviado, cliente ainda não aceitou | [[Revisão de envio]], [[Chamados ocupados]] |
| DATA_ENVIADA | cliente aceitou o template e recebeu a mensagem programada | [[Resposta do cliente (DigiSac)]] |
| AGUARDANDO_DECISAO_RESPONSAVEL | IA ofereceu falar com o responsável | [[Resposta do cliente (DigiSac)]] |
| AGUARDANDO_CONSULTOR | dúvida enviada para a tela Consultas da IA | [[Resposta do cliente (DigiSac)]] |
| CONCLUIDO | contato resolvido (pode ficar em vigilância) | resposta, consultor |
| TRANSFERIDO / TRANSFERENCIA_MANUAL | chamado com o responsável / falhou e precisa de ação manual | resposta, consultor |
| ESCALADO | e-mail ao responsável | [[Resposta do cliente (DigiSac)]] |
| SEM_RETORNO_CLIENTE | encerrado sem resposta | [[Encerramento sem retorno]] |
| PENDENTE_RESPOSTA_TARDIA | cliente respondeu depois do encerramento | [[Varredura de respostas tardias]] |
| AGRUPADO | foi junto na mensagem única de outro pedido | [[Disparo do fluxo]] |
| OUTLET, BLOQUEADO, CANCELADO, PEDIDO_CANCELADO, PEDIDO_ENTREGUE | não recebem mensagem | [[Disparo do fluxo]] |
