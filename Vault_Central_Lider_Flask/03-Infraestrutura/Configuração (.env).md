---
recurso: Configuração (.env)
tipo: infraestrutura
gatilho: ".env"
arquivo: app/config.py, .env.example
versao_base: n8n v28
atualizado: 2026-11-16
tags: [infra]
---
# Configuração (.env)

| Chave | Uso |
|---|---|
| `PORT` | 6050 (n8n usa 5678) |
| `MODO_TESTE` | true = nada sai; ver [[Modo teste]] |
| `AGENDADOR_ATIVO` | false enquanto o n8n estiver em produção |
| `SQLITE_PATH` | arquivo do banco (em `dados/`) |
| `INTRANET_URL/USUARIO/SENHA` | login da intranet (antes fixo nos nós) |
| `DIGISAC_URL/TOKEN` | API do DigiSac |
| `GOOGLE_CREDENCIAIS_JSON`, `PLANILHA_ID`, `PLANILHA_ABA` | planilha; aba **Página3** |
| `SMTP_*`, `EMAIL_ALERTA_ERRO` | e-mail (porta 465 = SSL direto) |
| `GEMINI_API_KEY/MODELO` | IA (gemini-3.5-flash-lite, igual à v28) |
| `OSRM_URL`, `NOMINATIM_URL` | rotas |

Senhas e tokens só ficam no `.env` (não vão para o vault nem para o diário).

## Ligações
[[Rodar o servidor]] · [[Integrações]]
