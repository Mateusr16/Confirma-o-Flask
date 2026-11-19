---
projeto: Central Líder (Flask)
atualizado: 2026-11-19
tags: [diario]
---
# Diário de bordo — Central Líder Flask

Mais recente em cima. Cada entrada: **o que mudou · por quê · arquivos · recursos afetados · testes · pendências**.

---

## 19/11/2026 — Transferência ao responsável só para usuário da Central de Relacionamento
- **O que mudou:** a busca do responsável para transferir o chamado agora considera só usuários **ativos** do departamento **CENTRAL DE RELACIONAMENTO LIDER** (pelo id do departamento usado nas transferências ou pelo nome). A lista de usuários pede ao DigiSac os departamentos de cada um (`include[0]=departments`). Vale para o botão "Solicitar transferência" e para a transferência automática quando o cliente aceita falar com o responsável.
- **Por quê:** pedido do Mateus depois do pedido 211255 (responsável PEDRO), que caiu em TRANSFERENCIA_MANUAL. Nome curto pode achar homônimo de outro departamento.
- **Arquivos:** `app/fluxos/f2_logica.py` (filtro na busca), `app/fluxos/f1_revisao.py` (`listar_usuarios_central`), `app/fluxos/consultor.py`, `app/fluxos/f2_resposta.py`, `tests/test_novos_ponta_a_ponta.py`
- **Recursos:** [[Consultas da IA (consultor)]] · [[Resposta do cliente (DigiSac)]]
- **Testes:** pytest não rodado (máquina sem flask). A busca nova passou num teste isolado: homônimo de outro departamento ignorado, departamento achado pelo id ou pelo nome, arquivado ignorado, sem departamentos → ninguém. Novo `test_transferir_so_usuario_da_central`. Rodar `python -m pytest -q` no PC.
- **Divergência da v28:** a v28 procurava o responsável entre todos os usuários do DigiSac.
- **Pendências:** (1) pytest no PC; (2) confirmar num teste real que o DigiSac devolve os departamentos dos usuários. Se não devolver, o log mostra "DigiSac não devolveu os departamentos dos usuários" e toda transferência vira TRANSFERENCIA_MANUAL; (3) ainda pendente, a pedido do Mateus: só marcar TRANSFERIDO quando o DigiSac confirmar a transferência.

## 19/11/2026 — Tela de disparo: 100 % só quando o fluxo termina de verdade
- **O que mudou:** o disparo grava um evento de fim (tipo `fim`) ao terminar sem erro, e o [[Status do disparo]] só marca concluído com ele (ou erro). A conclusão por silêncio virou reserva de 30 min. A consulta dos pedidos na intranet e a conferência de boletos gravam o andamento "(n/total)" no máximo a cada 20 s.
- **Por quê:** o Mateus viu a tela pular para 100 % na etapa de boletos com o processo ainda rodando (disparo de 19/11, 09:00). A conferência pedido a pedido passou de 7 min sem gravar evento, e a regra antiga dava o fluxo por concluído.
- **Registro atrasado:** em 17/11 o `_timer` (`ag_rotinas.py`: reenvio do template e lembrete 13h) e o Timer envio Template (`f1_revisao.py`) passaram de 5–6 s para **1–2 s**, sem entrada no diário. Registrado aqui. O Sistema-Unificado foi igualado hoje.
- **Arquivos:** `app/fluxos/painel.py`, `app/fluxos/f1_disparo.py`, `tests/test_f1_ponta_a_ponta.py`
- **Recursos:** [[Status do disparo]] · [[Disparo do fluxo]] · [[Painel Central Líder]]
- **Testes:** pytest não rodado: a máquina onde a mudança foi feita não tem flask nem acesso para instalar. A lógica nova passou num teste com dublês (executando após 10 min sem evento, progresso limitado a 20 s, fim real → 100 %, reserva de 30 min, erro prevalece). `test_f1_ponta_a_ponta.py` ganhou a checagem do evento de fim. Rodar `python -m pytest -q` no PC e anotar o total.
- **Divergência da v28:** a v28 (regra v16) concluía por inatividade (60 s depois de 96 %, senão 7 min). Agora conclui pelo evento de fim; inatividade só depois de 30 min.
- **Pendências:** (1) pytest no PC; (2) reiniciar o servidor só depois que o disparo em andamento terminar. O código novo só vale após reiniciar.

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
