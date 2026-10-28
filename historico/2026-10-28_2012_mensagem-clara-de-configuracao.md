# Mensagem clara quando falta configuração

- **Data do push:** 28/10/2026 às 20:12 (Brasília)
- **Branch:** `main`
- **Publicado na produção?** Sim (o Railway publica sozinho).

## Contexto

Depois de uma nova publicação, o painel voltou a dizer "configure
PAINEL_SEGREDO e PAINEL_EQUIPE", embora as variáveis tivessem funcionado
minutos antes. A mesma mensagem aparecia para problemas diferentes
(variável ausente, formato errado, código curto demais), e isso dificultava
descobrir a causa.

## O que foi implementado

- O login agora diz qual é o problema: variável que não chegou ao servidor,
  falta do ":" entre o nome e o código, ou códigos com menos de 10
  caracteres. Nunca mostra os valores.
- Ao subir, o servidor registra no log do Railway se o login está pronto e
  quantas pessoas têm acesso, ou o motivo de estar desativado.

## Como isso altera o sistema

- Só a mensagem e o log mudam. As regras de acesso continuam as mesmas.

## Como foi testado

- Bateria `test_painel.py`: 71/71 (3 cenários novos no grupo Login).
