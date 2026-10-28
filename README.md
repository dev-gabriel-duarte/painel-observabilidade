# Painel de observabilidade

Um lugar só para ver, de cada projeto: se os sistemas estão no ar, quanto
custam por mês, o que está pendente e o que foi alterado.

## Rodar no computador

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app:app --port 8800
```

Antes, defina no terminal as variáveis `PAINEL_SEGREDO` e `PAINEL_EQUIPE`
(explicadas no `.env.example`).

## Acompanhar um projeto novo

1. Copie `workspaces/_modelo.json` para `workspaces/<nome-do-projeto>.json`.
2. Preencha: repositório, sistemas a checar e custos.
3. No repositório do projeto, crie `BACKLOG.md` (pendências) e a pasta
   `historico/` (um registro por push) — mesmo formato da autopeças.
4. Se o repositório for privado, inclua-o no `GITHUB_TOKEN` (fine-grained).
5. Publique. O painel lê os arquivos a cada acesso — não precisa mexer no código.

## Testes

```bash
.venv/Scripts/python.exe -X utf8 test_painel.py
```
