---
recurso: Testes automáticos
tipo: infraestrutura
gatilho: "python -m pytest -q"
arquivo: tests/
versao_base: n8n v28
atualizado: 2026-11-16
tags: [infra]
---
# Testes automáticos

- **Paridade** (`tests/paridade/`): roda o JavaScript original de cada nó da v28 em Node e compara com o Python (precisa de Node; sem Node os testes são pulados).
- **Ponta a ponta**: disparo, pendência, revisão, chamado ocupado, resposta do cliente, consultor, recomeçar, vigilância, reenvio, lembrete, encerramento e varredura tardia, com integrações simuladas.
- Total em 16/11: **218 testes OK**.

Rodar: `python -m pytest -q` na pasta do projeto (com a `.venv` ativa).

## Ligações
[[Modo teste]] · [[Diario de bordo]]
