---
projeto: Central Líder (Flask)
criado: 2026-11-19
tags: [melhorias, desempenho, revisão-de-código]
---
# Análise de melhorias: processo de confirmação

Revisão do código (`app/`), dos logs e do banco. Nada foi alterado no código.
Prioridade: 🔴 corrigir já · 🟠 ganho grande · 🟡 melhoria.

## 1. Onde o disparo gasta tempo (medido no FLUXO_STATUS de 19/11)

| Etapa | Duração | % |
|---|---|---|
| Planilha + login + lojas.php | 0:40 | 4 % |
| Entregas realizadas | 0:09 | 1 % |
| **Boletos** | **8:17** | **45 %** |
| **Outlet** (situacao_pedidos) | **3:23** | **19 %** |
| Rota e prazo (Nominatim + OSRM) | 2:40 | 15 % |
| Contatos DigiSac | 1:01 | 6 % |
| Mensagens (situacao_pedidos de novo + projetos) | 2:12 | 12 % |
| **Total** | **~18 min** | |

Em 18/11 os boletos levaram 12:42. Todo o resto do fluxo é sequencial: um pedido por vez, uma requisição por vez.

---

## 2. 🔴 Problemas de produção (antes de otimizar)

### 2.1 Duas instâncias com agendador ligado
- **19/11 06:54:** o `central.log` mostra **dois processos** do Confirmação-flask subindo com 1 s de diferença ("Central Líder |" e "Serving on" duplicados). Os dois rodaram os agendamentos: vigilância às 07:00 (FECHAR 2) **duas vezes** e varredura tardia às 08:05 **duas vezes**.
  - Causa: `porta_ocupada()` é checagem e depois bind (corrida). No Windows o waitress consegue abrir a mesma porta duas vezes.
- **Sistema-Unificado** subiu às 09:35 e às 12:14 com `MODO_TESTE=false` e `AGENDADOR_ATIVO=true` (porta 6055, **banco próprio**). Ele rodou lembrete 13h e reenvio 13:20 (0 contatos porque o banco dele está defasado). Mas o encerramento das 16:20 lê a **planilha real** e fecha chamados no DigiSac. Com os dois no ar, a ação sai em dobro ou baseada em dados velhos.
- **Correção:**
  1. Trava de instância única: abrir `dados/.lock` com `msvcrt.locking` (Windows) no início do `run.py` e sair se já estiver travado. Isso substitui `porta_ocupada`.
  2. Trava de agendamento no banco: tabela `travas(job, dono, ate)` com `INSERT ... WHERE NOT EXISTS`. Mesmo se dois processos subirem, só um executa cada job.
  3. Decidir qual pasta é a de produção e deixar `AGENDADOR_ATIVO=false` na outra.

### 2.2 Envio em dobro na Revisão (corrida + ordem invertida)
`f1_revisao.processar_decisao`: busca a linha em `PENDENTE_REVISAO` → lista usuários → espera 1–2 s → consulta tickets → **envia o template** → só então muda o status. Dois cliques (ou painel em 2 abas) dentro dessa janela de ~3–5 s **enviam o template duas vezes**.
- **Inverter: primeiro "reservar", depois enviar.**
  ```python
  n = UPDATE AGUARDANDO_ENTREGA SET status='ENVIANDO'
      WHERE pedidoLider=? AND status='PENDENTE_REVISAO'   -- rowcount == 1 ou sai
  ```
  Em caso de falha, volta para `PENDENTE_REVISAO`.
- **O resultado do template não é conferido.** `enviar_template` devolve `{"error": ...}` e mesmo assim o pedido vira `AGUARDANDO`. Se der erro, não transferir; marcar `ERRO_ENVIO` e mostrar no painel.
- Inverter também a ordem das consultas: chamar `tickets_abertos` primeiro e `listar_usuarios_todos()` (paginada) **só se houver chamado de outro atendente** (os nomes só servem para a mensagem de OCUPADO). Melhor ainda: cache de 10 min da lista de usuários. Vale também para `chamados_ocupados` e para a transferência.

### 2.3 Retry que duplica mensagem no WhatsApp
`digisac._req` tenta 3 vezes em **qualquer** erro, inclusive POST de mensagem com `ReadTimeout`. Se o DigiSac recebeu e só demorou a responder, o cliente recebe a mensagem 2 ou 3 vezes. Ele também repete erros 4xx, que nunca vão passar.
- Retry só para GET, ou para POST em `ConnectError`/`ConnectTimeout` (não chegou a enviar), HTTP 429 e 5xx. Nunca repetir 4xx.
- O mesmo vale para `intranet.aviso_entrega` (GET que grava observação: um retry após timeout duplica a observação) e para `alterar_data`.

### 2.4 Resposta do cliente que trava na planilha (6 ocorrências hoje)
Pedidos 211348, 211412, 211414, 211324 e 211419: "não encontrado na planilha para gravar a resposta". Em `f2_resposta.registrar_resultado`, `localizar_linhas_sheet` **levanta erro**. O status já foi gravado e a mensagem já foi enviada, mas **a observação na intranet e a vigilância de 1 h não acontecem**.
- Planilha não encontrada passa a ser aviso: segue para a observação na intranet e a vigilância, grava `pendenciaPlanilha` no `dadosPedido` e manda um único e-mail-resumo.
- Investigar por que a linha some (alguém apaga a linha confirmada? outra aba?). Em 211348 a 1ª resposta funcionou e a 2ª, minutos depois, já não achou a linha.

### 2.5 Endpoints abertos na internet
O zrok publica **tudo**: painel, `/webhook/disparar-fluxo-lider`, `central-lider-revisao` (envia template), `resolver`, `recomecar` e `/api/rodar/<job>`. Não há autenticação e o CORS é `*`. Quem tiver a URL consegue disparar envios para clientes.
- Público só o `digisac-resposta`, com segredo na URL (`?k=...`, conferido no Flask).
- Painel e APIs: token num header (`X-Central-Token`), ou aceitar só `127.0.0.1`/rede local (`request.remote_addr`) e acessar o painel pela rede interna.
- `/api/rodar` só de localhost.

### 2.6 Banco crescendo ~1 GB/mês por log inútil
`dados/central_lider.db` = **270 MB**: 196 MB são a tabela `execucoes`, com **81.702 linhas de `digisac-resposta` em 6 dias** (todas as mensagens da empresa, com o corpo inteiro). O filtro `contato_atendido` descarta a mensagem, mas `_rodar` já registrou a execução.
- Registrar só quando o contato é atendido (o handler devolve `None` → não grava).
- Gravar sem o `body` completo (só contactId e messageId).
- Retenção: apagar `execucoes` com mais de 15 dias na limpeza diária e rodar `VACUUM` uma vez.
- Polling do painel (`central-lider-pendencias`, `status-fluxo-lider`) também não precisa ir para `execucoes`.

---

## 3. 🟠 Desempenho do disparo (18 min → estimativa de 4–6 min)

### 3.1 Boletos (45 % do tempo)
`conferir_boletos(data)` é chamado **uma vez por pedido**, com o intervalo de um único dia, e a página devolve **todos os pedidos daquele dia**.
1. **Cache por data dentro do disparo** (`dict data → html`). Pedidos da mesma data passam a fazer 1 consulta. Mudança pequena e sem risco.
2. **Uma consulta só para o intervalo** `min(data)…max(data)` e separar por pedido (`tratar_conferencia_boleto` e `analisar_50` já procuram pelo número `11-XXXXXX` dentro do HTML). Testar antes se a página não pagina nem corta resultado com intervalo grande. Se funcionar, a etapa cai de minutos para segundos.
3. `html_boletos` deixa de ser uma lista com N HTMLs e vira um índice `pedido → bloco`. Hoje `analisar_50` faz busca linear em todos os HTMLs.

### 3.2 `situacao_pedidos` consultado 2–3× por pedido
O mesmo HTML é buscado em **Entrega por produto** (parciais), **Outlet** (todos) e **Mensagens soltos/planejados** (todos).
- Cache por pedido dentro do `Disparo` (`self._situacao[pedido]`). Elimina a consulta da etapa Mensagens (~2 min).
- Melhor: buscar uma vez logo após `extrair_dados_pedido`, junto com `lojas.php`.

### 3.3 Paralelizar as consultas à intranet
Tudo é sequencial e a intranet é local. Use `ThreadPoolExecutor(max_workers=4)` em lojas.php, situacao_pedidos e boletos.
- ⚠️ PHP com sessão em arquivo **serializa requisições do mesmo cookie**. Paralelizar com um único login não acelera. Faça **1 login por worker** (pool de 3–4 objetos `Intranet`).
- Use `requests.Session()` por worker (keep-alive), mandando só o cookie do login como hoje (`session.cookies.clear()` e header manual).

### 3.4 Rota e prazo (15 %)
- **Coordenadas geocodificadas não são salvas.** `preparar_coordenadas` só gera `linhasParaTabela` para copiar à mão no código. Toda cidade fora da `TABELA_COORD` é geocodificada de novo em todo disparo (1,5 s cada). Salvar numa tabela `COORDENADAS(chave, lat, lon, fonte, criadoEm)` e ler TABELA + banco.
- **Cache de distância** `ROTAS(origem, destino) → km`. A distância entre duas cidades não muda, então a chamada ao OSRM (0,8 s + rede, servidor público de demonstração) some depois da primeira vez.
- Calcular por **par de cidades único**, não por pedido.

### 3.5 Planilha: uma leitura completa por atualização
`planilha._atualizar` chama `get_all_values()` **a cada atualização** (cancelado, faturado, outlet, boleto e a resposta do cliente). São N leituras completas por disparo, e a cota do Google (60 leituras/min) pode estourar com 429.
- O disparo já lê a planilha no início com `row_number`. Guardar o mapa `Pedido → row_number` e o cabeçalho.
- Acumular as alterações e mandar **um `batch_update` por etapa** (ou no fim). Para evitar escrever na linha errada se alguém mexer na planilha durante o disparo: 1 releitura só da coluna Pedido (`aba.col_values(n)`) antes do batch.
- Mesmo no `_atualizar` por `row_number` (Fluxo 2), o cabeçalho pode ficar em cache (hoje relê a planilha inteira só para saber as colunas).

### 3.6 Inverter ordens: filtrar barato antes do caro
Ordem atual: cancelado → entregue → **boleto** → **outlet** → **rota (OSRM)** → reincidência/tardia → **celular válido** → contato.
Reincidência, resposta tardia e celular válido são **só banco/memória** e hoje rodam **depois** do OSRM.
- Calcular `verificar_reincidencia`, `verificar_resposta_tardia` e `preparar_tentativas` logo após a extração (sem I/O externo), e **pular rota/OSRM** para quem vai ser ESCALAR/JA_ESCALADO ou não tem celular.
- ⚠️ Isso muda a prioridade de status em casos raros: pedido escalado e sem cidade hoje vira `PENDENTE_DESTINO` e passaria a `ESCALADO`. Decidir qual é o certo e registrar no diário.
- **Não inverter boleto ↔ outlet.** Hoje um outlet com boleto a analisar fica `PENDENCIA_BOLETO`. Invertendo, ele seria confirmado sem conferir o boleto. A saída é deixar o boleto barato (3.1), não mudar a ordem.
- A checagem de boleto repetida em `reincidencia_e_contatos` só pega `motivoPlanilha` com "BOLETO" ou `pagamento50`. Ela pode ir para o início (é dado da planilha) e tirar esses pedidos antes de tudo.

### 3.7 DigiSac: busca de contato
Até 4 GETs por pedido (2 telefones × 2 serviços). Testar `GET /contacts?where[data.number][$iLike]=%XXXXXXXX` **sem** `serviceId` e escolher pela ordem de `SERVICES`: cai pela metade. Paralelizável também (2–3 workers).

---

## 4. 🟡 Robustez e manutenção

- **Disparo duplo:** `_lock_disparo` **enfileira** o segundo clique, que roda o fluxo inteiro de novo depois. Recusar com 409 ("já existe um disparo em andamento") e o painel mostra o disparo atual.
- **Mensagens perdidas no reinício:** cada resposta do DigiSac é uma thread que dorme 60 s. Reiniciar o servidor mata essas threads (hoje às 10:15 havia várias em espera). A varredura tardia recupera só parte. A tabela `esperas` já existe (vazia): gravar a mensagem lá ao receber, processar a partir dela e, ao subir, retomar o que ficou aberto.
- **Painel:** `status_disparo` lê o `FLUXO_STATUS` inteiro a cada 2 s e `api_pendencias` lê `AGUARDANDO_ENTREGA` inteira. Filtrar por `disparoId` no SQL. Para o painel tanto faz hoje, mas cresce.
- **Login da intranet a cada resposta** (Fluxo 2, observação e adiamento): reaproveitar uma sessão e relogar só quando `html_eh_tela_login`.
- **Código duplicado** em `Confirmação-flask/app` e `Sistema-Unificado/modulos/central_lider` (hoje idênticos, igualados à mão). Escolher um como fonte única e aposentar o outro, ou usar git com um único repositório. Do contrário, as correções vão divergir.
- **Testes não rodados** nas 2 últimas entradas do diário. Antes de reiniciar em produção: `python -m pytest -q` (pode virar um `reiniciar.ps1` que roda o teste e só reinicia se passar).
- **Arquivos soltos:** `dados/central_lider_ - Copia.db` e `central_lider__.db` (165 MB) e `_to_delete/`.
- **Constantes no código:** e-mails (`EMAIL_EXPEDICAO`, `EMAIL_ALERTA`, `EMAIL_AVISOS`), IDs do DigiSac e listas de responsáveis (`RESPONSAVEIS_PLANEJADOS/SOLTOS`) poderiam ir para o `.env` ou para uma tabela. Responsável novo hoje exige deploy e cai em BLOQUEADO.
- `limpeza_diaria.status_efetivo` é O(n²) (procura o pai do AGRUPADO na lista toda). Trocar por um dict. Irrelevante com 80 linhas, mas fácil.

---

## 5. Ordem sugerida de execução

1. Trava de instância única + agendador desligado na pasta que não é a de produção (2.1).
2. Reservar antes de enviar + conferir o resultado do template na Revisão (2.2).
3. Retry seguro no DigiSac e na intranet (2.3).
4. Planilha não encontrada deixa de derrubar a resposta (2.4).
5. Token/segredo nos endpoints (2.5).
6. Parar de logar mensagens descartadas + retenção + VACUUM (2.6).
7. Cache de boletos por data, cache de `situacao_pedidos`, cache de coordenadas e rotas (3.1, 3.2, 3.4): **maior ganho com menor risco**.
8. Planilha em lote (3.5) → paralelismo com várias sessões (3.3) → inversão de filtros (3.6).
