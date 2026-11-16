---
recurso: Modo teste
tipo: infraestrutura
gatilho: "MODO_TESTE=true"
arquivo: app/saida.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [infra]
---
# Modo teste

Com `MODO_TESTE=true`, tudo que alteraria algo fora do sistema (mensagem, template, transferência, fechar chamado, e-mail, planilha, alteração/observação na intranet) **não é enviado**: fica registrado na tabela `envios_simulados`. Leituras (intranet, DigiSac, planilha) são reais.

Ver o que teria saído: `python simular_resposta.py --ultimos`.

## Ligações
[[Configuração (.env)]] · [[Testes automáticos]]
