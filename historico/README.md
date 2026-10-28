# Histórico de alterações

Cada `git push` ganha um arquivo nesta pasta explicando o contexto da
mudança: por que foi feita, o que foi implementado e como isso altera o
sistema no dia a dia da loja.

O `git log` diz **o que** mudou no código. Estes arquivos dizem **por quê**
e **o que muda para a loja**, em português claro, para quem não vai ler código
(o Gabriel daqui a seis meses, o Yuri, um próximo programador).

## Nome do arquivo

```
AAAA-MM-DD_HHMM_assunto-curto.md
```

- Data e hora **de Brasília**, do momento do push (ex.: `2026-10-27_2319`).
- Assunto curto, sem acento e com hífens (ex.: `pedidos-lembretes-e-seguranca`).
- Com esse formato, a lista de arquivos já fica em ordem cronológica.

## Quando criar

O arquivo vai **junto no mesmo push**, não depois. Se fosse criado depois,
ele só chegaria ao GitHub no push seguinte, e o histórico ficaria sempre
um passo atrasado.

Ordem: terminar a mudança, rodar a bateria, escrever o arquivo do
histórico, fazer o commit (código e histórico juntos) e dar o push.

## Modelo

```markdown
# Título curto da mudança

- **Data do push:** 28/10/2026 às 14:30 (Brasília)
- **Branch:** main (produção) | demo-cliente | outro
- **Commits:** abc1234, def5678
- **Publicado na produção?** Sim / Não (por quê)

## Contexto
Qual era o problema ou o pedido. O que motivou a mudança.

## O que foi implementado
- Item por item, em linguagem simples.

## Como isso altera o sistema
- O que muda para o cliente.
- O que muda para os atendentes.
- O que muda na operação (variáveis no Railway, tabelas no Supabase, custos).

## Riscos e o que ficou pendente
- O que pode dar errado e como perceber.
- O que alguém ainda precisa fazer à mão.

## Como foi testado
- Bateria `test_main_meta.py`: N/N cenários.
- O que foi conferido no navegador ou na produção.
```
