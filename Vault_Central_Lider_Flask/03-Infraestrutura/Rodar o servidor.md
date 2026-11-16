---
recurso: Rodar o servidor
tipo: infraestrutura
gatilho: "python run.py"
arquivo: run.py
versao_base: n8n v28
atualizado: 2026-11-16
tags: [infra]
---
# Rodar o servidor

## Como usar (PowerShell, na pasta Confirmação-flask)
```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```
- Conferir: http://127.0.0.1:6050/api/saude (modo teste, agendador, gatilhos migrados).
- Painel: http://127.0.0.1:6050/webhook/central-lider
- Parar: Ctrl+C na janela. Se a porta estiver ocupada, o `run.py` avisa e não sobe de novo (evita dois servidores).
- Conferir conexões sem enviar nada: `python verificar_config.py`.

## O que acontece ao subir
Cria/atualiza as tabelas, apaga mensagens de contatos que o sistema não atende, liga o agendador (se ativo) e serve com waitress.

## Ligações
[[Configuração (.env)]] · [[Endereço público (zrok)]] · [[Logs e alertas]]
