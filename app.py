"""
Painel de observabilidade — uso pessoal do Gabriel e da equipe.

Um "workspace" é um projeto (hoje: a autopeças). Cada um é descrito por um
arquivo em workspaces/<slug>.json: repositório no GitHub, sistemas a checar
e custos. Para acompanhar um projeto novo, basta criar outro arquivo — não
precisa mexer no código.

Tela:
  /                         → login, lista de workspaces e a visão de cada um
  /api/workspaces           → resumo de todos (estado, custo, pendências)
  /api/workspaces/{slug}    → sistemas, custos, pendências e alterações
"""
import os
import re
import hmac
import json
import time
import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import fontes

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('painel')
# O httpx registraria cada URL consultada no log; aqui só interessa o que der errado.
logging.getLogger('httpx').setLevel(logging.WARNING)

RAIZ = Path(__file__).parent
PASTA_WORKSPACES = RAIZ / 'workspaces'
PASTA_WEB = RAIZ / 'web'
SLUG = re.compile(r'^[a-z0-9-]{1,40}$')

app = FastAPI(title='Painel de observabilidade', docs_url=None, redoc_url=None, openapi_url=None)


# ── Configuração ────────────────────────────────────────────────────
def carregar_json(caminho: Path) -> dict:
    with open(caminho, encoding='utf-8') as arquivo:
        return json.load(arquivo)


def carregar_workspaces() -> dict:
    """Lê workspaces/*.json a cada chamada (são poucos e pequenos): editar um
    arquivo e publicar já muda o painel, sem reiniciar nada."""
    workspaces = {}
    for caminho in sorted(PASTA_WORKSPACES.glob('*.json')):
        if caminho.name.startswith('_'):
            continue  # _modelo.json e afins
        try:
            dados = carregar_json(caminho)
        except (OSError, ValueError) as erro:
            logger.error(f'Workspace {caminho.name} ignorado: JSON inválido ({erro})')
            continue
        slug = dados.get('slug') or caminho.stem
        if SLUG.match(slug):
            dados['slug'] = slug
            workspaces[slug] = dados
    return workspaces


def carregar_geral() -> dict:
    caminho = RAIZ / 'geral.json'
    try:
        return carregar_json(caminho)
    except (OSError, ValueError):
        return {'cotacao': {'BRL': 1}, 'custos': []}


# ── Custos ──────────────────────────────────────────────────────────
def resumir_custos(custos: list, cotacao: dict) -> dict:
    """Converte tudo para reais por mês. Valor anual vira /12. Item sem valor
    (null) entra como "a confirmar" e não soma — melhor mostrar a lacuna do que
    inventar um número."""
    itens, total, a_confirmar = [], 0.0, 0
    for c in custos:
        moeda = (c.get('moeda') or 'BRL').upper()
        valor = c.get('valor')
        mensal_brl = None
        if isinstance(valor, (int, float)) and moeda in cotacao:
            mensal = valor / 12 if c.get('periodo') == 'anual' else valor
            mensal_brl = round(mensal * cotacao[moeda], 2)
            total += mensal_brl
        else:
            a_confirmar += 1
        itens.append({**c, 'moeda': moeda, 'mensal_brl': mensal_brl,
                      'confirmado': bool(c.get('confirmado')) and mensal_brl is not None})
    return {'itens': itens, 'total_mensal_brl': round(total, 2), 'a_confirmar': a_confirmar,
            'estimado': any(not i['confirmado'] for i in itens)}


# ── Login (código por pessoa, cookie assinado) ──────────────────────
COOKIE = 'painel_sessao'
SESSAO_SEGUNDOS = 12 * 3600
_tentativas: dict = {}
MAX_TENTATIVAS = (8, 900)  # 8 erros a cada 15 min por IP


def equipe() -> dict:
    """PAINEL_EQUIPE="Gabriel:codigo-longo;Yuri:outro-codigo" (códigos com 10+
    caracteres). O nome de quem entrou vem do código."""
    pessoas = {}
    for item in os.getenv('PAINEL_EQUIPE', '').split(';'):
        nome, _, codigo = item.partition(':')
        nome, codigo = re.sub(r'\s+', ' ', nome).strip()[:40], codigo.strip()
        if nome and len(codigo) >= 10:
            pessoas[nome] = codigo
    return pessoas


def problema_de_configuracao() -> str:
    """Diz em português o que falta no Railway — sem nunca mostrar os valores."""
    if not os.getenv('PAINEL_SEGREDO', '').strip():
        return 'a variável PAINEL_SEGREDO não chegou ao servidor (confira o nome e clique em Deploy no Railway).'
    bruto = os.getenv('PAINEL_EQUIPE', '').strip()
    if not bruto:
        return 'a variável PAINEL_EQUIPE não chegou ao servidor (confira o nome e clique em Deploy no Railway).'
    if not equipe():
        pares = [p for p in bruto.split(';') if p.strip()]
        sem_dois_pontos = sum(1 for p in pares if ':' not in p)
        if sem_dois_pontos:
            return 'PAINEL_EQUIPE precisa do formato Nome:codigo;Nome:codigo (faltou o ":" entre o nome e o código).'
        return 'todos os códigos do PAINEL_EQUIPE têm menos de 10 caracteres — use códigos mais longos.'
    return ''


def _chave() -> bytes:
    segredo = os.getenv('PAINEL_SEGREDO', '')
    return hashlib.sha256(('painel-obs:' + segredo).encode('utf-8')).digest()


def assinar(nome: str, expira: int) -> str:
    corpo = f'{nome}|{expira}'
    assinatura = hmac.new(_chave(), corpo.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{corpo}|{assinatura}'


def ler_sessao(request: Request) -> Optional[str]:
    valor = request.cookies.get(COOKIE) or ''
    partes = valor.rsplit('|', 2)
    if len(partes) != 3 or not os.getenv('PAINEL_SEGREDO'):
        return None
    nome, expira, assinatura = partes
    esperado = assinar(nome, int(expira) if expira.isdigit() else 0).rsplit('|', 1)[-1]
    if not hmac.compare_digest(assinatura.encode('utf-8'), esperado.encode('utf-8')):
        return None
    if not expira.isdigit() or int(expira) < time.time():
        return None
    if nome not in equipe():
        return None  # tirou a pessoa do PAINEL_EQUIPE → a sessão cai na hora
    return nome


def exigir_login(request: Request) -> str:
    nome = ler_sessao(request)
    if not nome:
        raise HTTPException(status_code=401, detail='Entre com o seu código.')
    return nome


def _ip(request: Request) -> str:
    encaminhado = request.headers.get('x-forwarded-for', '')
    return encaminhado.split(',')[0].strip() or (request.client.host if request.client else '?')


def _bloqueado(ip: str) -> bool:
    agora = time.time()
    recentes = [t for t in _tentativas.get(ip, []) if t > agora - MAX_TENTATIVAS[1]]
    _tentativas[ip] = recentes
    return len(recentes) >= MAX_TENTATIVAS[0]


class Login(BaseModel):
    codigo: str


@app.post('/api/login')
async def login(dados: Login, request: Request, response: Response):
    problema = problema_de_configuracao()
    if problema:
        raise HTTPException(status_code=503, detail=f'Painel desativado: {problema}')
    ip = _ip(request)
    if _bloqueado(ip):
        raise HTTPException(status_code=429, detail='Muitas tentativas. Espere 15 minutos.')
    codigo = dados.codigo.strip()
    pessoas = equipe()
    # Aceita também "Gabriel:codigo" — é o formato da variável, e é fácil
    # copiar o trecho com o nome junto.
    prefixo, separador, resto = codigo.partition(':')
    if separador and prefixo.strip().lower() in {n.lower() for n in pessoas}:
        codigo = resto.strip()
    for nome, certo in pessoas.items():
        if hmac.compare_digest(codigo.encode('utf-8'), certo.encode('utf-8')):
            expira = int(time.time()) + SESSAO_SEGUNDOS
            response.set_cookie(COOKIE, assinar(nome, expira), max_age=SESSAO_SEGUNDOS, httponly=True,
                                samesite='lax', secure=request.url.scheme == 'https'
                                or request.headers.get('x-forwarded-proto') == 'https')
            logger.info(f'Login: {nome} ({ip})')
            return {'nome': nome}
    _tentativas.setdefault(ip, []).append(time.time())
    logger.warning(f'Login recusado ({ip})')
    raise HTTPException(status_code=401, detail='Código inválido.')


@app.post('/api/sair')
async def sair(response: Response):
    response.delete_cookie(COOKIE)
    return {'ok': True}


@app.get('/api/sessao')
async def sessao(request: Request):
    return {'nome': exigir_login(request)}


# ── Dados ───────────────────────────────────────────────────────────
def _workspace(slug: str) -> dict:
    ws = carregar_workspaces().get(slug) if SLUG.match(slug) else None
    if not ws:
        raise HTTPException(status_code=404, detail='Workspace não encontrado.')
    return ws


async def _bloco(buscar):
    """Roda uma fonte e devolve {dados} ou {erro} — nunca levanta exceção."""
    try:
        return {'dados': await buscar(), 'erro': None}
    except fontes.FonteIndisponivel as erro:
        return {'dados': [], 'erro': str(erro)}
    except Exception as erro:
        logger.error(f'Fonte falhou: {erro!r}')
        return {'dados': [], 'erro': 'Falha inesperada ao buscar estes dados.'}


async def _pendencias(ws: dict) -> list:
    repo, branch, arquivo = ws.get('repositorio'), ws.get('branch', 'main'), ws.get('backlog')
    if not repo or not arquivo:
        return []
    async def buscar():
        try:
            texto = await fontes.ler_arquivo(repo, arquivo, branch)
        except fontes.FonteIndisponivel as erro:
            if 'Não encontrado' in str(erro):
                return []
            raise
        return fontes.ler_pendencias(texto)
    return await fontes.em_cache(f'pend:{ws["slug"]}', buscar)


async def _sistemas(ws: dict) -> list:
    return await fontes.em_cache(f'sis:{ws["slug"]}', lambda: fontes.checar_sistemas(ws.get('sistemas', [])))


async def _historico(ws: dict) -> list:
    if not ws.get('repositorio'):
        return []
    return await fontes.em_cache(f'hist:{ws["slug"]}', lambda: fontes.listar_historico(
        ws['repositorio'], ws.get('historico', 'historico'), ws.get('branch', 'main')))


async def _commits(ws: dict) -> list:
    if not ws.get('repositorio'):
        return []
    return await fontes.em_cache(f'commits:{ws["slug"]}', lambda: fontes.listar_commits(
        ws['repositorio'], ws.get('branch', 'main')))


@app.get('/api/workspaces')
async def lista_workspaces(request: Request):
    exigir_login(request)
    geral = carregar_geral()
    cotacao = geral.get('cotacao') or {'BRL': 1}
    workspaces = list(carregar_workspaces().values())

    async def resumo(ws):
        sistemas, pendencias, historico = await asyncio.gather(_bloco(lambda: _sistemas(ws)), _bloco(lambda: _pendencias(ws)),
                                                               _bloco(lambda: _historico(ws)))
        custos = resumir_custos(ws.get('custos', []), cotacao)
        ultima = (historico['dados'] or [None])[0]
        return {
            'slug': ws['slug'], 'nome': ws.get('nome', ws['slug']), 'descricao': ws.get('descricao', ''),
            'icone': ws.get('icone', 'caixa'), 'cor': ws.get('cor', '#4C6EF5'),
            'estado': fontes.estado_geral(sistemas['dados']),
            'sistemas': {'total': len(sistemas['dados']),
                         'ok': sum(1 for s in sistemas['dados'] if s['estado'] == 'ok')},
            'custo_mensal_brl': custos['total_mensal_brl'], 'custos_a_confirmar': custos['a_confirmar'],
            'pendencias_abertas': sum(1 for p in pendencias['dados'] if p['aberta']),
            'pendencias_erro': pendencias['erro'],
            'ultima_alteracao': ultima,
        }

    resumos = await asyncio.gather(*(resumo(ws) for ws in workspaces))
    gerais = resumir_custos(geral.get('custos', []), cotacao)
    return {
        'workspaces': resumos,
        'custos_gerais': gerais,
        'total_mensal_brl': round(sum(r['custo_mensal_brl'] for r in resumos) + gerais['total_mensal_brl'], 2),
        'cotacao': cotacao, 'cotacao_data': geral.get('cotacao_data', ''),
    }


def _links(ws: dict) -> list:
    """Links do workspace, conferidos: só endereço http(s) vira link (um
    "javascript:" esquecido no JSON não chega à tela) e todo link tem grupo.
    Link sem endereço é permitido — serve para dizer que algo existe sem
    guardar um endereço secreto aqui."""
    links = []
    for item in ws.get('links', []):
        if not isinstance(item, dict) or not item.get('nome'):
            continue
        url = item.get('url')
        links.append({
            'nome': str(item['nome'])[:80],
            'url': url if isinstance(url, str) and re.match(r'^https?://', url, re.I) else None,
            'descricao': str(item.get('descricao') or '')[:400],
            'grupo': str(item.get('grupo') or 'Links')[:60],
            'destaque': bool(item.get('destaque')),
            'copiar_apenas': bool(item.get('copiar_apenas')),
        })
    return links


@app.get('/api/workspaces/{slug}')
async def detalhe_workspace(slug: str, request: Request):
    exigir_login(request)
    ws = _workspace(slug)
    geral = carregar_geral()
    sistemas, pendencias, historico, commits = await asyncio.gather(
        _bloco(lambda: _sistemas(ws)), _bloco(lambda: _pendencias(ws)),
        _bloco(lambda: _historico(ws)), _bloco(lambda: _commits(ws)))
    return {
        'slug': ws['slug'], 'nome': ws.get('nome', slug), 'descricao': ws.get('descricao', ''),
        'icone': ws.get('icone', 'caixa'), 'cor': ws.get('cor', '#4C6EF5'),
        'repositorio': ws.get('repositorio', ''), 'links': _links(ws),
        'estado': fontes.estado_geral(sistemas['dados']),
        'sistemas': sistemas, 'pendencias': pendencias, 'historico': historico, 'commits': commits,
        'custos': resumir_custos(ws.get('custos', []), geral.get('cotacao') or {'BRL': 1}),
        'cotacao_data': geral.get('cotacao_data', ''),
    }


@app.get('/api/workspaces/{slug}/historico/{arquivo}')
async def registro_historico(slug: str, arquivo: str, request: Request):
    exigir_login(request)
    ws = _workspace(slug)
    if not fontes.NOME_HISTORICO.match(arquivo) or not ws.get('repositorio'):
        raise HTTPException(status_code=404, detail='Registro não encontrado.')
    caminho = f'{ws.get("historico", "historico")}/{arquivo}'
    try:
        texto = await fontes.em_cache(f'md:{slug}:{arquivo}', lambda: fontes.ler_arquivo(
            ws['repositorio'], caminho, ws.get('branch', 'main')))
    except fontes.FonteIndisponivel as erro:
        raise HTTPException(status_code=502, detail=str(erro))
    return {'arquivo': arquivo, 'markdown': texto}


@app.post('/api/atualizar')
async def atualizar(request: Request):
    """Botão "Atualizar agora": esquece o cache e busca tudo de novo."""
    exigir_login(request)
    fontes.limpar_cache()
    return {'ok': True}


@app.get('/health')
async def health():
    return {'status': 'ok'}


# ── Páginas e proteções ─────────────────────────────────────────────
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


@app.middleware('http')
async def protecoes(request: Request, call_next):
    # Escrita vinda de outro site (CSRF) é recusada antes de tudo.
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origem = request.headers.get('origin')
        host = request.headers.get('x-forwarded-host') or request.headers.get('host') or ''
        if origem and origem.split('://', 1)[-1].rstrip('/') != host:
            return JSONResponse({'detail': 'Origem não permitida.'}, status_code=403)
    resposta = await call_next(request)
    resposta.headers['X-Content-Type-Options'] = 'nosniff'
    resposta.headers['Referrer-Policy'] = 'no-referrer'
    resposta.headers['X-Frame-Options'] = 'DENY'
    resposta.headers['X-Robots-Tag'] = 'noindex, nofollow'
    resposta.headers['Content-Security-Policy'] = CSP
    if request.headers.get('x-forwarded-proto') == 'https':
        resposta.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if request.url.path.startswith('/api/'):
        resposta.headers['Cache-Control'] = 'no-store'
    return resposta


@app.get('/')
async def pagina():
    return FileResponse(PASTA_WEB / 'index.html')


app.mount('/assets', StaticFiles(directory=PASTA_WEB / 'assets'), name='assets')

if problema_de_configuracao():
    logger.warning(f'Login desativado: {problema_de_configuracao()}')
else:
    logger.info(f'Painel pronto: {len(equipe())} pessoa(s) com acesso.')
