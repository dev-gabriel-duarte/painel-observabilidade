# Primeira versão do painel de observabilidade

- **Data do push:** 28/10/2026 às 19:49 (Brasília) — primeiro envio para o GitHub
- **Branch:** `main`
- **Publicado na produção?** Ainda não: falta criar o serviço no Railway e as variáveis.

## Contexto

O Gabriel quis um lugar só para acompanhar os projetos (começando pela
autopeças): se os sistemas estão no ar, quanto custam, o que está pendente e
o que foi alterado. Precisa servir para os próximos projetos também,
escolhendo cada um como um "workspace". O uso é pessoal, dele e da equipe.

A decisão foi um projeto próprio no Railway, separado da autopeças, para os
dados serem ao vivo e o painel não depender do servidor de um cliente.

## O que foi implementado

- **Tela inicial:** um cartão por workspace, com sistemas no ar, pendências
  abertas, custo por mês e a última alteração, além dos totais gerais.
- **Visão de cada workspace:**
  - Pendências, lidas do `BACKLOG.md` do repositório (PEN e TEC).
  - Alterações, lidas da pasta `historico/`, que abrem o texto completo.
  - Últimos commits.
  - Sistemas (checagem dos sites, páginas de status do Supabase, do GitHub e
    da Anthropic, e deploys do Railway).
  - Custos convertidos para reais por mês.
- **Projeto novo = arquivo novo:** copiar `workspaces/_modelo.json`; o código
  não muda.
- **Login com código por pessoa** (`PAINEL_EQUIPE`), cookie assinado, bloqueio
  depois de 8 tentativas erradas, CSP sem script inline, tokens só no servidor.
- **Nenhuma fonte derruba o painel:** se o GitHub ou um site cair, o bloco
  mostra o motivo e o resto continua.

## Como isso altera o sistema

- Nada muda na autopeças. O painel só **lê** o repositório e os sites.
- Na autopeças entra o arquivo `BACKLOG.md`, que o painel lê.

## Riscos e o que ficou pendente

- Os custos estão como "estimado" ou "a confirmar": é preciso preencher os
  valores reais e o plano do Claude.
- Para os dados aparecerem no servidor, faltam o `GITHUB_TOKEN` (só leitura)
  e, de forma opcional, o `RAILWAY_TOKEN` e o id do projeto.
- A consulta ao Railway foi escrita pela documentação da API, mas ainda não
  rodou com um token de verdade. Conferir no primeiro deploy.

## Como foi testado

- Bateria `test_painel.py`: 66/66 cenários (login, proteções, pendências,
  custos, dados, falhas, configuração).
- No navegador, com os sistemas checados de verdade pela internet: tela
  inicial, visão da autopeças, leitura de um registro e tela de celular.
- A bateria achou dois bugs, já corrigidos: o exemplo de formato do
  `BACKLOG.md` sendo lido como pendência, e o botão "Atualizar agora" que não
  voltava a ficar clicável.
