---
recurso: Integrações
tipo: infraestrutura
gatilho: "-"
arquivo: app/integracoes/
versao_base: n8n v28
atualizado: 2026-11-16
tags: [infra]
---
# Integrações

| Integração | Arquivo | Uso |
|---|---|---|
| Intranet (192.168.0.6) | `intranet.py` | login (1º cookie), consulta de pedidos, boletos, alterar data, observação de contato |
| DigiSac | `digisac.py` | buscar/criar contato, template HSM, mensagem, vídeo, transferir, fechar chamado, tickets, usuários, mensagens |
| Planilha Google | `planilha.py` | leitura da aba (com `row_number`) e atualização da 1ª linha encontrada |
| E-mail | `email.py` | alertas, vendedor, expedição, responsável |
| Gemini | `gemini.py` | texto e saída JSON (equivale aos nós de IA da v28; prompts exatos em `fluxos/prompts_v28.json`) |
| Rotas | `rotas_geo.py` | Nominatim (coordenadas) e OSRM (distância) |

Toda escrita passa por `saida.externo` ([[Modo teste]]). Falhas seguem a mesma regra da v28 (a maioria continua o fluxo e registra o erro).

## Ligações
[[Configuração (.env)]] · [[Modo teste]]
