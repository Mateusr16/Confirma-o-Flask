# Central Líder — servidor Flask (migração do n8n v28)

## Instalar (uma vez, no PowerShell, dentro desta pasta)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # depois abra o .env e preencha
```

## Conferir a configuração

```powershell
python verificar_config.py
```

Testa intranet, DigiSac, planilha, e-mail, Gemini e rotas só com leitura/login (nada é enviado).

## Rodar

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

Para conferir se subiu, abra http://127.0.0.1:6050/api/saude no navegador. A página mostra:
- se o MODO_TESTE está ligado;
- quais gatilhos já foram migrados e quais ainda faltam.

O painel abre em http://127.0.0.1:6050/webhook/central-lider.

## Chaves do .env que mudam o comportamento

| Chave | O que faz |
|---|---|
| `MODO_TESTE=true` | Nada sai para o DigiSac, e-mail, intranet ou planilha. Tudo que seria enviado fica na tabela `envios_simulados`. |
| `AGENDADOR_ATIVO=false` | Os 6 agendamentos ficam desligados. Ligue só depois de desligar os do n8n, senão rodam em dobro. |
| `PORT=6050` | Use uma porta diferente da 5678 enquanto o n8n estiver ligado. |

## Virada do n8n para o Flask

1. No n8n, desative o workflow (os webhooks e agendamentos param).
2. No `.env`, coloque `MODO_TESTE=false` e `AGENDADOR_ATIVO=true` e reinicie o `run.py`.
3. Aponte o zrok para a porta do Flask, por exemplo `zrok share reserved <seu-nome> --override-endpoint http://127.0.0.1:6050`.
   As rotas são as mesmas (`/webhook/digisac-resposta` etc.), então no DigiSac não precisa mudar nada se o endereço do zrok continuar o mesmo.

## Estrutura

```
run.py                 inicia servidor + agendador
app/config.py          lê o .env
app/db.py              SQLite (WAL) + migrações em app/migracoes/
app/saida.py           porta única de envio externo (respeita MODO_TESTE)
app/registro.py        log diário em logs/ + e-mail de erro
app/agendador.py       os 6 agendamentos da v28
app/rotas/webhooks.py  os 9 webhooks da v28, mesmos caminhos
app/fluxos/            um módulo por etapa (F1-1 ... F2-3)
app/integracoes/       intranet, DigiSac, Sheets, SMTP, Gemini, rotas
tests/                 testes automáticos (python -m pytest)
```
