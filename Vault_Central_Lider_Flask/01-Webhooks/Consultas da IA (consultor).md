---
recurso: Consultas da IA (consultor)
tipo: webhook
gatilho: "POST /webhook/central-lider-consultor"
arquivo: app/fluxos/consultor.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [webhook, fluxo2, consultor]
---
# Consultas da IA (consultor)

## Para que serve
Tela onde o consultor atende os pedidos em **AGUARDANDO_CONSULTOR** (dúvidas que a IA não respondeu) e registra resultados, inclusive das respostas tardias.

## Como usar
Três ações no cartão:
- **Responder** — escreve a orientação; pode marcar um resultado junto.
- **Registrar resultado** — Confirmado, Não concorda ou Adiado (com a nova data).
- **Transferir** — passa o chamado ao responsável do pedido.

## O que o sistema faz
- **Responder:** a IA reescreve a orientação em tom de WhatsApp (sem inventar nada) e envia ao cliente. Pedido → CONCLUIDO, vigilância de 2 h. Se o envio falhar, a consulta continua aberta e o painel mostra o erro.
- **Registrar:** login na intranet; se Adiado, altera a data (formulário `altera_data_entrega`); grava a observação de contato (pula se o contato já foi registrado antes); grava CONFIRMADO/MOTIVO/DATA na planilha; pedido → CONCLUIDO com vigilância de 1 h (2 h se veio junto com resposta). Vários pedidos da mensagem única são registrados juntos. Vindo de resposta tardia, marca o SEM_CONFIRMACAO_DIARIO como RESPOSTA_TARDIA_TRATADA.
- **Transferir:** encontra o responsável entre os usuários do DigiSac; transfere e avisa o cliente → TRANSFERIDO. Sem responsável: e-mail de ação manual e aviso ao cliente → TRANSFERENCIA_MANUAL.
- Validações iguais à v28 (consulta já tratada, data no passado, 1ª confirmação de planejados não pode ser adiada etc.).

## Como testar
Testes de paridade (47 cenários) e ponta a ponta. Real: mandar uma pergunta que a IA não saiba ("o montador vem junto?") e responder pela tela.

## Ligações
[[Resposta do cliente (DigiSac)]] · [[Varredura de vigilância]] · [[Varredura de respostas tardias]] · [[Integrações]]
