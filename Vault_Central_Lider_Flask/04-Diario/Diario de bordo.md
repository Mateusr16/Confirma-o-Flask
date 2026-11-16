---
projeto: Central Líder (Flask)
atualizado: 2026-11-16
tags: [diario]
---
# Diário de bordo — Central Líder Flask

Mais recente em cima. Cada entrada: **o que mudou · por quê · arquivos · recursos afetados · testes · pendências**.

---

## 16/11/2026 — Vault do Obsidian e skill de documentação
- **O que mudou:** criado este vault (`Vault_Central_Lider_Flask/`) com uma nota de manual por recurso (9 webhooks, 6 agendamentos, 8 de infraestrutura), glossário de status e este diário; criada a skill `documentar-central-lider-flask` para manter tudo atualizado.
- **Por quê:** pedido do Mateus — manual de funcionalidade e registro das modificações.
- **Arquivos:** `Vault_Central_Lider_Flask/**`.
- **Testes:** sem mudança de código (218 OK).

## 16/11/2026 — Migração do restante: consultor, recomeçar e agendamentos
- **O que mudou:** migrados os 2 webhooks e 5 agendamentos que faltavam. Com isso os 9 webhooks e todos os agendamentos da v28 estão no Flask.
  - [[Consultas da IA (consultor)]] — `app/fluxos/consultor.py`
  - [[Recomeçar pedido]] — `app/fluxos/recomecar.py`
  - [[Varredura de vigilância]], [[Lembrete de confirmação 13h]], [[Reenvio do template]], [[Encerramento sem retorno]], [[Varredura de respostas tardias]] (+ ao ligar o servidor) — `app/fluxos/ag_rotinas.py`
  - `app/comum.py`: funções que imitam o JavaScript (`||`, `??`, datas, `Math.round`).
  - `app/agendador.py`: a varredura "ao iniciar" roda em segundo plano (não atrasa a subida).
  - `LEIAME.md`: tabela de agendamentos e passos da virada com zrok v2.
- **Por quê:** "Pode migrar tudo de uma vez".
- **Testes:** paridade consultor 47, recomeçar 43, agendamentos 17; ponta a ponta 7 novos; total **218 OK**.
- **Mantido igual à v28 (avaliar):** aprendizado da base após "Responder" nunca grava; transferência que falha no DigiSac com responsável mapeado fica TRANSFERIDO.
- **Pendências:** testar no DigiSac real (consulta ao consultor e recomeço com número novo); virada.

## 16/11/2026 — Teste real de adiamento
- Pedido 97680: cliente pediu adiar para maio, depois "Pode ser 22/05". 22/05/2027 é sábado → data alterada para **24/05/2027** na intranet, observação gravada, planilha preenchida, resposta no WhatsApp. Resultado OK.

## 16/11/2026 — Endereço do zrok com nome fixo
- **Problema:** template saiu às 07:18 mas o cliente não foi respondido. O compartilhamento temporário do Flask (`auard91e6sis`) caiu com a reinicialização do PC (502); as mensagens não chegaram.
- **Correção:** nome fixo `liderflask` → porta 6050 e tarefa agendada `zrok2-flask` (script `C:\Users\Mateus\bin\start-zrok2-flask.ps1`) que recria o compartilhamento ao ligar. Webhook do Flask no DigiSac trocado para `https://liderflask.shares.zrok.io/webhook/digisac-resposta`. O n8n (`ryofnng9lhhy`, tarefa `zrok2-n8n`) não foi tocado.
- **Recursos:** [[Endereço público (zrok)]].

## 13/11/2026 — Só guardar mensagens de quem o sistema atende
- **O que mudou:** a resposta do DigiSac só grava/processa contatos com pedido na AGUARDANDO_ENTREGA ou sem retorno nos últimos 30 dias; ao subir, o servidor apaga mensagens de outros contatos.
- **Por quê:** o n8n gravava todas as mensagens recebidas e isso enchia a memória.
- **Recursos:** [[Resposta do cliente (DigiSac)]], [[Banco SQLite]].

## 13/11/2026 — Primeiro teste real pelo DigiSac
- Webhook extra do DigiSac apontando para o Flask (o n8n seguiu em produção na outra aba da planilha). Template HSM entregue, cliente respondeu "Ok!" e recebeu a mensagem programada.

## 13/11/2026 — Resposta do cliente (Fluxo 2)
- Migrado o webhook `digisac-resposta` (template, IA com Gemini, adiamento, planilha, intranet, consultor, vigilância). Teste: `simular_resposta.py`.
- **Divergência da v28:** cliente que recusa falar com o responsável vai para CONCLUIDO (na v28 o nó lia um resumo inexistente e o status não mudava).

## 13/11/2026 — Revisão de envio e chamados ocupados
- Migrados [[Revisão de envio]] e [[Chamados ocupados]] + rota `POST /api/rodar/<nome>`. Teste real: chamado ocupado → AGUARDANDO_CHAMADO_LIVRE → liberado → AGUARDANDO.

## 13/11/2026 — Disparo, pendências e painel
- Migrados [[Painel Central Líder]], [[Status do disparo]], [[API Pendências]], [[Disparo do fluxo]], [[Resolver pendência]]. Teste real com o pedido 97680.
- **Divergência da v28:** quantidade nos planejados lida igual aos soltos ("1.0" = 1, não 10x).
- Planilha passou a ler a aba **Página3** (`PLANILHA_ABA`).
- Ajustes de ambiente: ID da planilha corrigido, credencial Google em `credenciais/`, SMTP 465 com SSL, `run.py` recusa subir com a porta ocupada, "database is locked" causado pelo DB Browser aberto.

## 13/11/2026 — Início da migração
- Decisões: servidor local no PC do Mateus, zrok mantido, SQLite com tabelas novas (sem importar dados do n8n), projeto do zero em `Desktop\Confirmação-flask`, mesmos caminhos `/webhook/...`.
- Base criada: Flask + waitress, SQLite (WAL), migrações, integrações, `MODO_TESTE`, log e alerta de erro, `verificar_config.py` (7/7 conexões OK).
