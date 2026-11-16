---
projeto: Central Líder (Flask)
atualizado: 2026-11-16
tags: [convencoes]
---
# Convenções deste vault

- **Código:** `Desktop\Confirmação-flask` (servidor Flask). Este vault fica dentro dele: `Vault_Central_Lider_Flask/`.
- **Origem das regras:** fluxo n8n v28 (`Desktop\N8N\Claude outputs\Fluxo_Central_Lider__13-11_v28_CONSULTOR_REGISTRO_REPETIDO.json`). O vault do n8n (`Desktop\N8N\Vault_Central_Lider`) continua sendo a referência das regras de negócio em detalhe.
- **Uma nota por recurso** em `01-Webhooks`, `02-Agendamentos` e `03-Infraestrutura`, sempre com as seções: *Para que serve · Como usar · O que o sistema faz · Status e tabelas · Diferenças da v28 · Como testar · Ligações*.
- **Diário de bordo:** `04-Diario/Diario de bordo.md`. Toda mudança no sistema ganha uma entrada (mais recente em cima) e a nota do recurso afetado tem o campo `atualizado` trocado.
- **Mudança que diverge da v28:** registrar no diário com a etiqueta **Divergência da v28** e na seção *Diferenças da v28* da nota do recurso.
- **Testes:** antes de fechar uma mudança, `python -m pytest -q` precisa passar; o total vai no diário.
- **Skill:** a skill `documentar-central-lider-flask` mantém este vault e o diário atualizados.
