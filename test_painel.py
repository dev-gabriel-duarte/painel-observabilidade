"""
Bateria de testes do painel de observabilidade.

    .venv/Scripts/python.exe -X utf8 test_painel.py

Nada sai para a internet: o GitHub, o Railway e os sites são simulados com
httpx.MockTransport (fontes.TRANSPORTE). Mesmo padrão da autopeças: toda
mudança nova ganha um grupo de cenários AQUI, nunca num arquivo solto.
"""
import os
import sys
import json
import time

os.environ['PAINEL_SEGREDO'] = 'segredo-de-teste'
os.environ['PAINEL_EQUIPE'] = 'Gabriel:codigo-do-gabriel; Yuri:codigo-do-yuri-1; Curto:123'
os.environ.pop('GITHUB_TOKEN', None)
os.environ.pop('RAILWAY_TOKEN', None)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as painel  # noqa: E402
import fontes  # noqa: E402

RESULTADOS = []


def registrar(grupo, nome, ok):
    RESULTADOS.append((grupo, nome, bool(ok)))


# ── Internet simulada ───────────────────────────────────────────────
BACKLOG = """# Backlog

## PEN 1 — Trocar o domínio
- **Status:** aberta
- **Prioridade:** alta
- **Aberta em:** 28/10/2026

Comprar o domínio e apontar para o Railway.

## PEN 2 — Pagamento de sinal
- **Status:** concluída
- **Prioridade:** média

Já feito.

## TEC 1 — Atualizar FastAPI
- **Status:** em andamento

## Outras anotações
Isto não é pendência.
"""
REGISTRO = '# Pedidos pelo site\n\n- **Data:** 27/10\n\n## Contexto\nTexto.\n'
chamadas = []
cenario = {'site': 200, 'github': 'ok', 'lento': False, 'railway': 'SUCCESS'}


def responder(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    chamadas.append(url)
    if 'quintaa' in url and url.endswith('/health'):
        if cenario['site'] == 'caiu':
            raise httpx.ConnectError('sem rede', request=request)
        return httpx.Response(cenario['site'], json={'status': 'ok'})
    if 'status.' in url or 'githubstatus' in url:
        return httpx.Response(200, json={'status': {'indicator': 'none', 'description': 'All Systems Operational'}})
    if 'backboard.railway' in url:
        return httpx.Response(200, json={'data': {'deployments': {'edges': [
            {'node': {'status': cenario['railway'], 'createdAt': '2026-10-28T12:00:00Z',
                      'service': {'name': 'web'}, 'environment': {'name': 'production'}}}]}}})
    if 'api.github.com' in url:
        if cenario['github'] == 'privado':
            return httpx.Response(404, json={'message': 'Not Found'})
        if cenario['github'] == 'fora':
            raise httpx.ConnectTimeout('timeout', request=request)
        if '/commits' in url:
            return httpx.Response(200, json=[{'sha': 'abcdef1234', 'html_url': 'https://github.com/x/commit/abc',
                                              'commit': {'message': 'feat: algo\n\ncorpo', 'author': {'name': 'Gabriel', 'date': '2026-10-28T01:00:00Z'}}}])
        if 'BACKLOG.md' in url:
            return httpx.Response(200, text=BACKLOG)
        if url.split('?')[0].endswith('/contents/historico'):
            return httpx.Response(200, json=[{'name': 'README.md'}, {'name': '2026-10-27_2319_pedidos-lembretes.md'},
                                             {'name': '2026-10-28_2230_pasta-historico.md'}, {'name': 'rascunho.md'}])
        if '/contents/historico/' in url:
            return httpx.Response(200, text=REGISTRO)
    return httpx.Response(200, text='ok')


fontes.TRANSPORTE = httpx.MockTransport(responder)


def novo():
    fontes.limpar_cache()
    painel._tentativas.clear()
    return TestClient(painel.app)


def logado(codigo='codigo-do-gabriel'):
    c = novo()
    c.post('/api/login', json={'codigo': codigo})
    return c


# ── Grupo 1: login ─────────────────────────────────────────────────
def grupo_1_login():
    g = '1. Login'
    c = novo()
    registrar(g, 'sem login, a API devolve 401', c.get('/api/workspaces').status_code == 401)
    r = c.post('/api/login', json={'codigo': 'codigo-do-gabriel'})
    registrar(g, 'código certo entra e o nome vem do código', r.status_code == 200 and r.json()['nome'] == 'Gabriel')
    registrar(g, 'cookie é HttpOnly', 'httponly' in r.headers.get('set-cookie', '').lower())
    registrar(g, 'sessão reconhecida', c.get('/api/sessao').json()['nome'] == 'Gabriel')
    registrar(g, 'código errado: 401', novo().post('/api/login', json={'codigo': 'chute'}).status_code == 401)
    registrar(g, 'código curto demais na configuração é ignorado', 'Curto' not in painel.equipe())
    registrar(g, 'código com acento não quebra a comparação', novo().post('/api/login', json={'codigo': 'códigô'}).status_code == 401)
    registrar(g, 'aceita "Nome:codigo" digitado (formato da variável)',
              novo().post('/api/login', json={'codigo': 'Gabriel:codigo-do-gabriel'}).json().get('nome') == 'Gabriel'
              and novo().post('/api/login', json={'codigo': ' gabriel : codigo-do-gabriel '}).status_code == 200)
    registrar(g, '...mas não deixa entrar com o nome de um e o código de outro',
              novo().post('/api/login', json={'codigo': 'Gabriel:codigo-do-yuri-1'}).json().get('nome') == 'Yuri'
              and novo().post('/api/login', json={'codigo': 'Fulano:codigo-do-gabriel'}).status_code == 401)

    c = novo()
    for _ in range(8):
        c.post('/api/login', json={'codigo': 'errado'})
    registrar(g, 'depois de 8 erros, bloqueia por 15 min (mesmo com o código certo)',
              c.post('/api/login', json={'codigo': 'codigo-do-gabriel'}).status_code == 429)

    c = novo()
    c.cookies.set(painel.COOKIE, painel.assinar('Gabriel', int(time.time()) + 999) + 'x')
    registrar(g, 'cookie adulterado não entra', c.get('/api/sessao').status_code == 401)
    c = novo()
    c.cookies.set(painel.COOKIE, painel.assinar('Gabriel', int(time.time()) - 5))
    registrar(g, 'cookie vencido não entra', c.get('/api/sessao').status_code == 401)

    yuri = logado('codigo-do-yuri-1')
    original = os.environ['PAINEL_EQUIPE']
    os.environ['PAINEL_EQUIPE'] = 'Gabriel:codigo-do-gabriel'
    registrar(g, 'tirar alguém do PAINEL_EQUIPE derruba a sessão dele', yuri.get('/api/sessao').status_code == 401)
    os.environ['PAINEL_EQUIPE'] = original

    original = os.environ['PAINEL_EQUIPE']
    for valor, trecho in (('Gabriel:curto', 'menos de 10'), ('Gabriel=codigo-longo-123', 'formato'), ('', 'PAINEL_EQUIPE não chegou')):
        os.environ['PAINEL_EQUIPE'] = valor
        r = novo().post('/api/login', json={'codigo': 'x'})
        registrar(g, f'configuração errada explica o motivo: {trecho}', r.status_code == 503 and trecho in r.json()['detail']
                  and 'codigo-longo' not in r.json()['detail'])
    os.environ['PAINEL_EQUIPE'] = original

    segredo = os.environ.pop('PAINEL_SEGREDO')
    registrar(g, 'sem PAINEL_SEGREDO o painel fica fechado (503)',
              novo().post('/api/login', json={'codigo': 'codigo-do-gabriel'}).status_code == 503)
    os.environ['PAINEL_SEGREDO'] = segredo


# ── Grupo 2: proteções ─────────────────────────────────────────────
def grupo_2_protecoes():
    g = '2. Proteções'
    c = novo()
    pagina = c.get('/')
    registrar(g, 'página carrega', pagina.status_code == 200 and 'painel.js' in pagina.text)
    csp = pagina.headers.get('content-security-policy', '')
    registrar(g, 'CSP só com script do próprio site e sem inline', "script-src 'self'" in csp and 'unsafe-inline' not in csp)
    registrar(g, 'não pode ser embutido em outro site', pagina.headers.get('x-frame-options') == 'DENY')
    registrar(g, 'não aparece em buscador', 'noindex' in pagina.headers.get('x-robots-tag', ''))
    registrar(g, 'login vindo de outro site é recusado',
              c.post('/api/login', json={'codigo': 'codigo-do-gabriel'}, headers={'Origin': 'https://mal.example'}).status_code == 403)
    registrar(g, '/docs e /openapi.json desligados', c.get('/docs').status_code == 404 and c.get('/openapi.json').status_code == 404)
    c = logado()
    registrar(g, 'respostas da API não ficam em cache do navegador',
              c.get('/api/workspaces').headers.get('cache-control') == 'no-store')
    registrar(g, 'workspace inexistente: 404', c.get('/api/workspaces/nao-existe').status_code == 404)
    registrar(g, 'nome de workspace com caractere perigoso: 404', c.get('/api/workspaces/..%2Fapp').status_code == 404)
    registrar(g, 'arquivo do histórico fora do padrão não é lido (sem passear por pastas)',
              c.get('/api/workspaces/autopecas/historico/..%2F..%2Fapp.py').status_code == 404
              and c.get('/api/workspaces/autopecas/historico/README.md').status_code == 404)
    texto = c.get('/api/workspaces/autopecas').text
    registrar(g, 'nenhum token vai para o navegador', 'segredo-de-teste' not in texto and 'codigo-do' not in texto)


# ── Grupo 3: pendências (BACKLOG.md) ───────────────────────────────
def grupo_3_pendencias():
    g = '3. Pendências'
    itens = fontes.ler_pendencias(BACKLOG)
    registrar(g, 'lê PEN e TEC, ignora seções que não são pendência', [i['codigo'] for i in itens] == ['PEN 1', 'PEN 2', 'TEC 1'])
    pen1 = itens[0]
    registrar(g, 'lê título, status, prioridade e data', pen1['titulo'] == 'Trocar o domínio' and pen1['status'] == 'aberta'
              and pen1['prioridade'] == 'alta' and pen1['aberta_em'] == '28/10/2026')
    registrar(g, 'descrição vem do texto livre', pen1['descricao'] == 'Comprar o domínio e apontar para o Railway.')
    registrar(g, 'concluída conta como fechada', itens[1]['aberta'] is False)
    registrar(g, '"em andamento" continua aberta', itens[2]['aberta'] is True)
    registrar(g, 'texto da seção seguinte não vaza para a última pendência', 'não é pendência' not in itens[2]['descricao'])
    registrar(g, 'sem status escrito, assume aberta', fontes.ler_pendencias('## PEN 9 — X\nalgo')[0]['aberta'])
    registrar(g, 'arquivo vazio: nenhuma pendência', fontes.ler_pendencias('') == [])
    com_modelo = '# Backlog\n\n```\n## PEN 1 — Título curto\n- **Status:** aberta\n```\n\n## TEC 1 — Real\n- **Status:** aberta\n'
    registrar(g, 'exemplo de formato dentro de ``` não vira pendência (bug achado no BACKLOG.md real)',
              [i['codigo'] for i in fontes.ler_pendencias(com_modelo)] == ['TEC 1'])


# ── Grupo 4: custos ────────────────────────────────────────────────
def grupo_4_custos():
    g = '4. Custos'
    cot = {'BRL': 1, 'USD': 5.0, 'EUR': 6.0}
    r = painel.resumir_custos([
        {'item': 'A', 'valor': 5, 'moeda': 'USD', 'confirmado': True},
        {'item': 'B', 'valor': 120, 'moeda': 'BRL', 'periodo': 'anual'},
        {'item': 'C', 'valor': None, 'moeda': 'USD'},
        {'item': 'D', 'valor': 2, 'moeda': 'XYZ'},
    ], cot)
    registrar(g, 'converte para reais e anual vira mensal', r['itens'][0]['mensal_brl'] == 25 and r['itens'][1]['mensal_brl'] == 10)
    registrar(g, 'item sem valor ou moeda desconhecida não soma e conta como "a confirmar"',
              r['total_mensal_brl'] == 35 and r['a_confirmar'] == 2)
    registrar(g, 'só é "confirmado" quem foi marcado assim', r['itens'][0]['confirmado'] and not r['itens'][1]['confirmado'])
    registrar(g, 'lista vazia: total zero', painel.resumir_custos([], cot)['total_mensal_brl'] == 0)


# ── Grupo 5: visão geral e detalhe ─────────────────────────────────
def grupo_5_dados():
    g = '5. Dados'
    for k, v in (('site', 200), ('github', 'ok'), ('railway', 'SUCCESS')):
        cenario[k] = v
    c = logado()
    lista = c.get('/api/workspaces').json()
    auto = next(w for w in lista['workspaces'] if w['slug'] == 'autopecas')
    registrar(g, 'o modelo (_modelo.json) não aparece como projeto', all(w['slug'] != 'novo-projeto' for w in lista['workspaces']))
    registrar(g, 'resumo traz pendências abertas do BACKLOG.md', auto['pendencias_abertas'] == 2)
    registrar(g, 'resumo traz a última alteração do historico/', auto['ultima_alteracao']['arquivo'] == '2026-10-28_2230_pasta-historico.md')
    registrar(g, 'total geral soma projetos e custos gerais', lista['total_mensal_brl'] >= auto['custo_mensal_brl'])

    d = c.get('/api/workspaces/autopecas').json()
    nomes = [s['nome'] for s in d['sistemas']['dados']]
    registrar(g, 'detalhe traz todos os sistemas configurados', 'Site e painel (produção)' in nomes and len(nomes) >= 5)
    site = next(s for s in d['sistemas']['dados'] if s['nome'] == 'Site e painel (produção)')
    registrar(g, 'site no ar aparece "ok" com o tempo de resposta', site['estado'] == 'ok' and site['latencia_ms'] is not None)
    sup = next(s for s in d['sistemas']['dados'] if 'Supabase' in s['nome'])
    registrar(g, 'página de status traduzida', sup['estado'] == 'ok' and sup['detalhe'] == 'Todos os sistemas operando')
    rail = next(s for s in d['sistemas']['dados'] if s['tipo'] == 'railway')
    registrar(g, 'Railway sem token: "sem dados" explicando o que configurar', rail['estado'] == 'desconhecido' and 'RAILWAY_TOKEN' in rail['detalhe'])
    hist = d['historico']['dados']
    registrar(g, 'histórico: só arquivos no padrão, mais novo primeiro, título do "# "',
              [h['arquivo'] for h in hist] == ['2026-10-28_2230_pasta-historico.md', '2026-10-27_2319_pedidos-lembretes.md']
              and hist[0]['titulo'] == 'Pedidos pelo site')
    registrar(g, 'commits com sha curto e só a primeira linha da mensagem',
              d['commits']['dados'][0]['sha'] == 'abcdef1' and d['commits']['dados'][0]['titulo'] == 'feat: algo')
    reg = c.get('/api/workspaces/autopecas/historico/2026-10-27_2319_pedidos-lembretes.md')
    registrar(g, 'abre o texto completo de um registro', reg.status_code == 200 and reg.json()['markdown'] == REGISTRO)

    antes = len(chamadas)
    c.get('/api/workspaces/autopecas')
    registrar(g, 'abrir de novo em seguida usa o cache (não gasta cota do GitHub)', len(chamadas) == antes)
    c.post('/api/atualizar')
    c.get('/api/workspaces/autopecas')
    registrar(g, '"Atualizar agora" busca tudo de novo', len(chamadas) > antes)


# ── Grupo 6: falhas não derrubam o painel ──────────────────────────
def grupo_6_falhas():
    g = '6. Falhas'
    cenario['site'] = 'caiu'
    c = logado()
    d = c.get('/api/workspaces/autopecas').json()
    site = next(s for s in d['sistemas']['dados'] if s['nome'] == 'Site e painel (produção)')
    registrar(g, 'site sem resposta: "fora" e o estado geral vira "fora"', site['estado'] == 'fora' and d['estado'] == 'fora')
    cenario['site'] = 503
    d = logado().get('/api/workspaces/autopecas').json()
    registrar(g, 'site com erro 503: "fora"', next(s for s in d['sistemas']['dados'] if s['nome'].startswith('Site'))['estado'] == 'fora')
    cenario['site'] = 200

    cenario['github'] = 'privado'
    r = logado().get('/api/workspaces/autopecas')
    corpo = r.json()
    registrar(g, 'repositório privado sem token: o painel abre mesmo assim', r.status_code == 200)
    registrar(g, '...e explica que falta o GITHUB_TOKEN', 'GITHUB_TOKEN' in (corpo['commits']['erro'] or ''))
    registrar(g, '...pendências e histórico sem arquivo viram lista vazia, sem erro',
              corpo['pendencias']['dados'] == [] and corpo['historico']['dados'] == [])
    cenario['github'] = 'fora'
    r = logado().get('/api/workspaces')
    registrar(g, 'GitHub fora do ar: a lista de workspaces continua abrindo', r.status_code == 200)
    d = logado().get('/api/workspaces/autopecas').json()
    registrar(g, '...e o bloco mostra o motivo', 'não respondeu' in (d['commits']['erro'] or ''))
    cenario['github'] = 'ok'

    os.environ['RAILWAY_TOKEN'] = 'token-teste'
    for status, esperado in (('SUCCESS', 'ok'), ('FAILED', 'fora'), ('BUILDING', 'lento')):
        cenario['railway'] = status
        sistema = {'nome': 'R', 'tipo': 'railway', 'projeto': 'p1'}
        import asyncio
        res = asyncio.run(fontes.checar_sistemas([sistema]))[0]
        registrar(g, f'Railway com deploy {status.lower()}: "{esperado}"', res['estado'] == esperado)
    os.environ.pop('RAILWAY_TOKEN')

    import asyncio
    res = asyncio.run(fontes.checar_sistemas([{'nome': 'X', 'tipo': 'inventado'}]))[0]
    registrar(g, 'tipo de checagem desconhecido não quebra', res['estado'] == 'desconhecido')
    registrar(g, 'estado geral: tudo ok / algum sem dados / algum fora',
              fontes.estado_geral([{'estado': 'ok'}]) == 'ok'
              and fontes.estado_geral([{'estado': 'ok'}, {'estado': 'desconhecido'}]) == 'atencao'
              and fontes.estado_geral([{'estado': 'ok'}, {'estado': 'fora'}]) == 'fora')


# ── Grupo 7: configuração ──────────────────────────────────────────
def grupo_7_configuracao():
    g = '7. Configuração'
    for caminho in list(painel.PASTA_WORKSPACES.glob('*.json')) + [painel.RAIZ / 'geral.json']:
        try:
            json.loads(caminho.read_text(encoding='utf-8'))
            ok = True
        except ValueError:
            ok = False
        registrar(g, f'{caminho.name} é JSON válido', ok)
    ws = painel.carregar_workspaces()
    registrar(g, 'workspace da autopeças carregado', 'autopecas' in ws and ws['autopecas']['repositorio'].endswith('quintaaautopecas'))
    tipos = {s['tipo'] for s in ws['autopecas']['sistemas']}
    registrar(g, 'todo sistema tem um tipo de checagem conhecido', tipos <= set(fontes._CHECADORES))


# ── Grupo 8: aba Links ─────────────────────────────────────────────
def grupo_8_links():
    g = '8. Links'
    c = logado()
    d = c.get('/api/workspaces/autopecas').json()
    links = d['links']
    por_url = {l['url']: l for l in links if l['url']}
    prod, teste = 'https://quintaaautopecas-production.up.railway.app', 'https://quintaaautopecas-teste.up.railway.app'
    registrar(g, 'sites principal E de testes: agendamento, pedido e painel dos atendentes',
              all(f'{base}{p}' in por_url for base in (prod, teste) for p in ('/agendar', '/agendar/novo', '/pedido', '/atendimento')))
    registrar(g, 'todo link tem grupo e uma explicação de para que serve',
              all(l['grupo'] and len(l['descricao']) >= 20 for l in links))
    registrar(g, 'grupos: site principal, site de testes, ferramentas e os antigos',
              list(dict.fromkeys(l['grupo'] for l in links)) == ['Site principal (produção)', 'Site de testes', 'Ferramentas e contas', 'Antigos / a desligar'])
    registrar(g, 'atalhos do topo: os dois sites e os dois painéis',
              {l['url'] for l in links if l['destaque']} >= {f'{prod}/agendar', f'{prod}/atendimento', f'{teste}/agendar', f'{teste}/atendimento'})
    texto = (painel.PASTA_WORKSPACES / 'autopecas.json').read_text(encoding='utf-8')
    registrar(g, 'nenhum endereço secreto guardado (painel do Yuri fica sem link)',
              '/painel/' not in texto and 'token=' not in texto.lower()
              and next(l for l in links if 'Yuri' in l['nome'])['url'] is None)
    registrar(g, 'webhook da Meta: só para copiar, não vira botão de abrir', por_url[f'{prod}/webhook']['copiar_apenas'] is True)

    falso = {'slug': 'x', 'links': [
        {'nome': 'Perigo', 'url': 'javascript:alert(1)', 'grupo': 'G'}, {'url': 'https://sem-nome.com'},
        {'nome': 'Sem grupo', 'url': 'HTTPS://ok.com', 'descricao': 'd' * 900}, 'texto solto']}
    conferidos = painel._links(falso)
    registrar(g, 'servidor confere: "javascript:" vira texto, sem nome é ignorado, grupo padrão e texto cortado',
              [l['nome'] for l in conferidos] == ['Perigo', 'Sem grupo'] and conferidos[0]['url'] is None
              and conferidos[1]['url'] == 'HTTPS://ok.com' and conferidos[1]['grupo'] == 'Links' and len(conferidos[1]['descricao']) == 400)
    js = (painel.PASTA_WEB / 'assets' / 'painel.js').read_text(encoding='utf-8')
    registrar(g, 'tela: aba Links com rota própria (#/ws/<slug>/links)', '(?:\\/(links))?$' in js and 'function painelLinks' in js)


if __name__ == '__main__':
    for grupo in (grupo_1_login, grupo_2_protecoes, grupo_3_pendencias, grupo_4_custos, grupo_5_dados,
                  grupo_6_falhas, grupo_7_configuracao, grupo_8_links):
        try:
            grupo()
        except Exception as erro:  # um grupo quebrado aparece como falha, não esconde os outros
            import traceback
            traceback.print_exc()
            registrar(grupo.__name__, f'grupo quebrou: {erro!r}', False)
    atual = None
    for grupo, nome, ok in RESULTADOS:
        if grupo != atual:
            print(f'\n{grupo}')
            atual = grupo
        print(f'  [{"OK " if ok else "FALHOU"}] {nome}')
    falhas = [r for r in RESULTADOS if not r[2]]
    print('\n' + '=' * 70)
    print(f'TOTAL: {len(RESULTADOS)} cenários — {len(RESULTADOS) - len(falhas)} passaram, {len(falhas)} falharam')
    print('=' * 70)
    sys.exit(1 if falhas else 0)
