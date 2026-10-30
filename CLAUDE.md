# CLAUDE.md — Painel de observabilidade

> Leia antes de qualquer tarefa. Mesmo dono e mesmas regras de comunicação da
> autopeças: o Gabriel está aprendendo a programar — sempre em português,
> explicando o quê, por quê e como, e sendo direto sobre riscos.

## O que é

Painel pessoal do Gabriel e da equipe para acompanhar **todos os projetos**
num lugar só. Cada projeto é um **workspace** (`workspaces/<slug>.json`). Para
cada um, o painel mostra:

| Bloco | De onde vem |
|---|---|
| Sistemas (no ar / lento / fora) | Checagem HTTP dos sites, páginas de status dos fornecedores (padrão Statuspage) e API do Railway |
| Pendências | `BACKLOG.md` do repositório do projeto (`## PEN 1 — Título` + `- **Status:** ...`) |
| Alterações | Pasta `historico/` do repositório (um `.md` por mudança importante) + últimos commits |
| Custos | Digitados no JSON do workspace e em `geral.json` (convertidos para R$/mês) |
| Links (aba própria) | `links` do JSON do workspace: `grupo`, `nome`, `url`, `descricao`; `destaque: true` também vira atalho na Visão geral; `copiar_apenas: true` para endereço que não é página (webhook). **Nunca** guardar endereço com código secreto (ex.: painel do Yuri) — fica com `url: null`. |

Primeiro workspace: `autopecas` (repositório `dev-gabriel-duarte/quintaaautopecas`).

## Stack

FastAPI + HTML/CSS/JS sem build (mesmo padrão do site da autopeças), deploy
no Railway, sem banco de dados: tudo vem do GitHub, das APIs e dos JSON.

## Regras

1. Rodar `.venv/Scripts/python.exe -X utf8 test_painel.py` antes e depois de
   qualquer mudança. Cenários novos entram nesse arquivo, num grupo — nunca
   arquivo de teste solto.
2. **Nenhuma fonte derruba o painel.** Toda busca externa passa por
   `_bloco()` / `checar_sistemas()`: falha vira mensagem na tela, não erro 500.
3. **Tokens só no servidor.** Nada de token ou código de acesso em resposta
   da API nem no JavaScript. Tokens do GitHub e do Railway sempre SÓ LEITURA.
4. Texto vindo de fora (markdown, nomes, mensagens de commit) entra na tela
   como texto (`el()` / `createTextNode`), nunca como HTML. CSP sem
   `unsafe-inline` — nada de `<script>` nem `style=""` inline.
5. Custo sem valor conhecido fica `null` ("a confirmar") — não inventar número.
6. Antes de cada `git push`, perguntar ao Gabriel se a mudança merece registro em
   `historico/`. Só criar o arquivo com o aval dele (ver `historico/README.md`).
7. Entregar com os comandos `git add` / `git commit` com várias linhas `-m`.

## Variáveis (Railway)

`PAINEL_SEGREDO`, `PAINEL_EQUIPE`, `GITHUB_TOKEN`, `RAILWAY_TOKEN` — explicadas
no `.env.example`.

## Pendências

- [ ] Preencher os custos reais (todos estão como "estimado"/"a confirmar")
      e o plano do Claude em `geral.json`.
- [ ] Colocar o id do projeto do Railway em `workspaces/autopecas.json`
      (`"projeto"` no sistema "Deploys no Railway").
- [ ] Custos automáticos (API de uso do Railway, fatura da Anthropic) — hoje
      são digitados à mão.
