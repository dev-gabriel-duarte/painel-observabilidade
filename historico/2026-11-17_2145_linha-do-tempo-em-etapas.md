# Aba "Linha do tempo" em etapas

- **Data do push:** 17/11/2026 às 21:45 (Brasília)
- **Branch:** `main`, vindo de `claude/keen-dijkstra-pc21w9`
- **Commits:** `5d583d5`, `91b4702` e o commit que atualizou este registro
- **Publicado na produção?** Sim, em 17/11/2026, a pedido do Gabriel (o Railway publica sozinho a partir do `main`).
- **Tipo:** função nova
- **Impacto:** médio
- **Resumo:** Cada projeto ganha a aba Linha do tempo: a história contada em etapas, cartões lado a lado ligados por linhas, e as pendências abertas no fim.

## Contexto

Pedido do Gabriel (PEN 29 da autopeças): uma linha do tempo interativa de cada
projeto, com as versões e as mudanças que realmente impactam, inclusive
correções de bug importantes. Ele também quis enxergar melhor as próximas
pendências (PEN 26 a 28).

A primeira versão era uma lista vertical, um ponto por registro. O Gabriel não
quis esse formato e mandou uma imagem de referência: etapas lado a lado,
ligadas por linhas, cada uma com rótulo ("ETAPA 1"), nome curto e uma bolinha
com um número. A aba foi refeita nesse formato antes do envio.

## O que foi implementado

- **Etapas lado a lado**, sobre um fundo de pontinhos. Cada etapa tem rótulo
  ("COMEÇO", "ETAPA 1"...), ícone pelo tipo da mudança, nome curto e a bolinha
  com quantas mudanças ela tem. As linhas entre as etapas levam a cor da
  etapa seguinte.
- **Quem divide as etapas são os marcos**: o registro com "Impacto: alto" abre
  uma etapa, e as mudanças seguintes, até o próximo marco, ficam dentro dela. O
  nome curto vem da linha "Etapa" do marco. Projeto sem marcos: uma etapa por mês.
- **Tocar numa etapa** mostra embaixo as mudanças dela: data, tipo, se já está
  na produção ou só no teste, resumo, commits (com link) e "Ler o registro".
- **Última etapa, tracejada: "Próximos"**, com as pendências abertas do
  `BACKLOG.md`: primeiro as em andamento, depois por prioridade.
- Arrastar com o mouse ou deslizar com o dedo; no teclado, as setas andam
  entre as etapas. A tela abre na etapa mais recente.
- O texto de cada registro é guardado pelo código (sha) que o GitHub dá ao
  arquivo: só registro novo ou editado é baixado de novo.

## Como isso altera o sistema

- Para quem usa: uma aba nova em cada projeto. As outras não mudaram; a
  "Visão geral" ganhou o atalho "Linha do tempo →" no bloco Alterações.
- Para escrever registros: o modelo (`historico/README.md`) ganhou as linhas
  Tipo, Impacto, Resumo, Etapa (só nos marcos) e Versão (opcional). Registro
  antigo, sem essas linhas, continua aparecendo.
- Nenhuma variável nova no Railway.

## Riscos e o que ficou pendente

- A aba lê o `historico/` do `main` de cada projeto. Na autopeças, os registros
  com Tipo, Impacto, Resumo e Etapa (e os 14 retroativos de junho a outubro)
  foram ao `main` no mesmo dia, logo antes desta publicação. Os retroativos foram
  escritos a partir do `git log` e publicados sem revisão linha a linha: o que
  estiver errado se corrige no próprio arquivo, e a aba atualiza sozinha.
- O primeiro envio foi recusado (403): o app do Claude no GitHub não tinha acesso
  a este repositório. O Gabriel liberou o acesso em 17/11.
- O nome curto da etapa é cortado com reticências se for comprido demais.

## Como foi testado

- Bateria `test_painel.py`: 115/115 (grupo 9 com 36 cenários: leitura do
  cabeçalho, divisão em etapas, ordem das pendências, guarda pelo sha, GitHub
  fora do ar e a tela).
- Prévia local com os 29 registros reais da autopeças, no navegador, em 1440,
  820, 390 e 360 px: 10 etapas, nenhuma tela rola para o lado, o arraste anda
  exatamente o que o mouse andou e não troca a etapa escolhida.
