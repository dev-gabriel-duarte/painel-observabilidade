# Login aceita "Nome:codigo"

- **Data do push:** 28/10/2026 às 20:10 (Brasília)
- **Branch:** `main`
- **Publicado na produção?** Sim (o Railway publica sozinho).

## Contexto

No primeiro acesso ao painel publicado, o Gabriel recebeu "Código inválido"
digitando o código que achava certo. A variável `PAINEL_EQUIPE` tem o formato
`Gabriel:codigo;Yuri:codigo`, e é fácil copiar o trecho com o nome junto.

## O que foi implementado

- O campo de login aceita só o código (como antes) **ou** `Nome:codigo`.
- O nome digitado não decide quem entra: quem entra é sempre o dono do
  código. Assim, digitar o nome de uma pessoa com o código de outra não
  permite se passar por ninguém.

## Como isso altera o sistema

- Menos tropeço no login. A segurança continua a mesma.

## Riscos e o que ficou pendente

- Se o código continuar sendo recusado, a causa provável é o valor salvo no
  Railway ter vindo de outra execução do comando que gera os códigos.

## Como foi testado

- Bateria `test_painel.py`: 68/68 (2 cenários novos no grupo Login).
