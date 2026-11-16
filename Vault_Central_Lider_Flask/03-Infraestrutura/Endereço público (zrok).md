---
recurso: Endereço público (zrok)
tipo: infraestrutura
gatilho: "zrok2 agent"
arquivo: C:\Users\Mateus\bin\start-zrok2.ps1
versao_base: n8n v28
atualizado: 2026-11-16
tags: [infra]
---
# Endereço público (zrok)

O DigiSac só alcança o servidor por um endereço público do zrok v2 (`C:\Users\Mateus\bin\zrok2.exe`, em modo agent).

| Nome | Porta | Uso | Sobe sozinho por |
|---|---|---|---|
| `ryofnng9lhhy` | 5678 | n8n (produção) | tarefa agendada `zrok2-n8n` |
| `liderflask` | 6050 | Flask (testes) | tarefa agendada `zrok2-flask` |

- Webhook do Flask no DigiSac: `https://liderflask.shares.zrok.io/webhook/digisac-resposta`.
- Compartilhamento sem nome fixo morre quando o PC reinicia (foi o que aconteceu em 16/11) — usar sempre nome fixo.
- Testar: `Invoke-RestMethod "https://liderflask.shares.zrok.io/api/saude" -Headers @{ skip_zrok_interstitial = "1" }`.
- Ver compartilhamentos: `& zrok2.exe agent status`. **Nunca** liberar o do n8n.

## Virada
Apontar `ryofnng9lhhy` para 6050, ligar `AGENDADOR_ATIVO`, desativar o fluxo no n8n, apagar `zrok2-flask`/`liderflask` e o webhook extra do DigiSac.

## Ligações
[[Rodar o servidor]] · [[Resposta do cliente (DigiSac)]] · [[Logs e alertas]]
