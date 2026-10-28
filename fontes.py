"""
Fontes de dados do painel: GitHub (alterações e pendências), checagem de
saúde dos sites, páginas de status dos fornecedores e Railway.

Regra de ouro: NENHUMA fonte derruba o painel. Se o GitHub, o Railway ou um
site não responder, aquele bloco aparece como "desconhecido" ou "fora", com o
motivo, e o resto continua carregando. Os tokens ficam só aqui no servidor —
nunca vão para o navegador.
"""
import os
import re
import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

# Os testes trocam isto por um httpx.MockTransport para não sair para a internet.
TRANSPORTE: Optional[httpx.AsyncBaseTransport] = None
TEMPO_LIMITE = 8.0
LENTO_MS = 2500  # acima disso o site está no ar, mas lento

CACHE_SEGUNDOS = 120
_cache: dict = {}


def criar_cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TEMPO_LIMITE, follow_redirects=True, transport=TRANSPORTE,
                             headers={'User-Agent': 'painel-observabilidade'})


async def em_cache(chave: str, buscar):
    """Guarda o resultado por CACHE_SEGUNDOS — abrir o painel várias vezes
    seguidas não pode gastar a cota de API do GitHub nem do Railway."""
    agora = time.monotonic()
    guardado = _cache.get(chave)
    if guardado and guardado[0] > agora:
        return guardado[1]
    valor = await buscar()
    _cache[chave] = (agora + CACHE_SEGUNDOS, valor)
    return valor


def limpar_cache():
    _cache.clear()


# ── Saúde dos sistemas ──────────────────────────────────────────────
def _resultado(sistema: dict, estado: str, detalhe: str, latencia_ms: Optional[int] = None) -> dict:
    return {
        'nome': sistema.get('nome', '?'),
        'tipo': sistema.get('tipo'),
        'estado': estado,  # ok | lento | fora | desconhecido
        'detalhe': detalhe,
        'latencia_ms': latencia_ms,
        'painel': sistema.get('painel') or '',
    }


async def checar_http(cliente: httpx.AsyncClient, sistema: dict) -> dict:
    inicio = time.monotonic()
    try:
        resposta = await cliente.get(sistema['url'])
    except httpx.HTTPError as erro:
        return _resultado(sistema, 'fora', f'Sem resposta ({type(erro).__name__})')
    ms = int((time.monotonic() - inicio) * 1000)
    if resposta.status_code >= 500:
        return _resultado(sistema, 'fora', f'Erro {resposta.status_code}', ms)
    if resposta.status_code >= 400:
        return _resultado(sistema, 'fora', f'Respondeu {resposta.status_code}', ms)
    if ms > LENTO_MS:
        return _resultado(sistema, 'lento', f'No ar, mas lento ({ms} ms)', ms)
    return _resultado(sistema, 'ok', f'No ar ({ms} ms)', ms)


# Páginas de status no padrão Statuspage (Supabase, GitHub, Anthropic...).
_INDICADORES = {'none': 'ok', 'minor': 'lento', 'major': 'fora', 'critical': 'fora', 'maintenance': 'lento'}


async def checar_statuspage(cliente: httpx.AsyncClient, sistema: dict) -> dict:
    try:
        resposta = await cliente.get(sistema['url'])
        resposta.raise_for_status()
        status = resposta.json().get('status') or {}
    except (httpx.HTTPError, ValueError) as erro:
        return _resultado(sistema, 'desconhecido', f'Página de status não respondeu ({type(erro).__name__})')
    estado = _INDICADORES.get(status.get('indicator'), 'desconhecido')
    descricao = status.get('description') or 'sem descrição'
    traducao = {'All Systems Operational': 'Todos os sistemas operando'}
    return _resultado(sistema, estado, traducao.get(descricao, descricao))


RAILWAY_API = 'https://backboard.railway.com/graphql/v2'
_CONSULTA_RAILWAY = '''
query($projeto: String!) {
  deployments(first: 5, input: { projectId: $projeto }) {
    edges { node { status createdAt service { name } environment { name } } }
  }
}'''
_RAILWAY_ESTADOS = {'SUCCESS': 'ok', 'DEPLOYING': 'lento', 'BUILDING': 'lento', 'INITIALIZING': 'lento',
                    'QUEUED': 'lento', 'WAITING': 'lento', 'FAILED': 'fora', 'CRASHED': 'fora'}


async def checar_railway(cliente: httpx.AsyncClient, sistema: dict) -> dict:
    token = os.getenv('RAILWAY_TOKEN', '')
    projeto = sistema.get('projeto')
    if not token or not projeto:
        return _resultado(sistema, 'desconhecido', 'Configure RAILWAY_TOKEN e o id do projeto para ver os deploys')
    try:
        resposta = await cliente.post(RAILWAY_API, json={'query': _CONSULTA_RAILWAY, 'variables': {'projeto': projeto}},
                                      headers={'Authorization': f'Bearer {token}'})
        resposta.raise_for_status()
        corpo = resposta.json()
    except (httpx.HTTPError, ValueError) as erro:
        return _resultado(sistema, 'desconhecido', f'API do Railway não respondeu ({type(erro).__name__})')
    if corpo.get('errors'):
        return _resultado(sistema, 'desconhecido', 'API do Railway recusou a consulta (confira o token e o id do projeto)')
    nos = [e['node'] for e in (((corpo.get('data') or {}).get('deployments') or {}).get('edges') or [])]
    producao = [n for n in nos if ((n.get('environment') or {}).get('name') or '').lower() == 'production'] or nos
    if not producao:
        return _resultado(sistema, 'desconhecido', 'Nenhum deploy encontrado')
    ultimo = producao[0]
    estado = _RAILWAY_ESTADOS.get(ultimo.get('status'), 'desconhecido')
    quando = formatar_data_iso(ultimo.get('createdAt'))
    servico = (ultimo.get('service') or {}).get('name') or 'serviço'
    return _resultado(sistema, estado, f'Último deploy de {servico}: {ultimo.get("status", "?").lower()} em {quando}')


_CHECADORES = {'http': checar_http, 'statuspage': checar_statuspage, 'railway': checar_railway}


async def checar_sistemas(sistemas: list) -> list:
    async with criar_cliente() as cliente:
        async def um(sistema):
            checador = _CHECADORES.get(sistema.get('tipo'))
            if not checador:
                return _resultado(sistema, 'desconhecido', 'Sem checagem automática (só custo/link)')
            try:
                return await checador(cliente, sistema)
            except Exception as erro:  # um checador com defeito não derruba os outros
                return _resultado(sistema, 'desconhecido', f'Falha na checagem ({type(erro).__name__})')
        return list(await asyncio.gather(*(um(s) for s in sistemas)))


def estado_geral(resultados: list) -> str:
    estados = {r['estado'] for r in resultados}
    if 'fora' in estados:
        return 'fora'
    if 'lento' in estados or 'desconhecido' in estados:
        return 'atencao'
    return 'ok' if estados else 'desconhecido'


# ── GitHub: alterações (historico/ + commits) e pendências (BACKLOG.md) ─
GITHUB_API = 'https://api.github.com'
NOME_HISTORICO = re.compile(r'^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})_([A-Za-z0-9-]+)\.md$')


def _cabecalhos_github(raw: bool = False) -> dict:
    cab = {'Accept': 'application/vnd.github.raw' if raw else 'application/vnd.github+json',
           'X-GitHub-Api-Version': '2022-11-28'}
    token = os.getenv('GITHUB_TOKEN', '')
    if token:
        cab['Authorization'] = f'Bearer {token}'
    return cab


class FonteIndisponivel(Exception):
    """Fonte respondeu com erro — a mensagem vai para a tela, em português."""


async def _github(cliente, caminho: str, raw: bool = False):
    try:
        resposta = await cliente.get(f'{GITHUB_API}{caminho}', headers=_cabecalhos_github(raw))
    except httpx.HTTPError as erro:
        raise FonteIndisponivel(f'GitHub não respondeu ({type(erro).__name__})')
    if resposta.status_code == 404:
        raise FonteIndisponivel('Não encontrado no GitHub (repositório privado sem GITHUB_TOKEN, ou caminho errado)')
    if resposta.status_code in (401, 403):
        raise FonteIndisponivel('GitHub recusou o acesso (confira o GITHUB_TOKEN e a cota de uso)')
    if resposta.status_code >= 400:
        raise FonteIndisponivel(f'GitHub respondeu {resposta.status_code}')
    return resposta.text if raw else resposta.json()


async def ler_arquivo(repositorio: str, caminho: str, branch: str) -> str:
    async with criar_cliente() as cliente:
        return await _github(cliente, f'/repos/{repositorio}/contents/{caminho}?ref={branch}', raw=True)


def _titulo_markdown(texto: str) -> str:
    for linha in texto.splitlines():
        if linha.startswith('# '):
            return linha[2:].strip()
    return ''


async def listar_historico(repositorio: str, pasta: str, branch: str, limite: int = 15) -> list:
    async with criar_cliente() as cliente:
        try:
            itens = await _github(cliente, f'/repos/{repositorio}/contents/{pasta}?ref={branch}')
        except FonteIndisponivel as erro:
            if 'Não encontrado' in str(erro):
                return []  # projeto ainda sem pasta historico/
            raise
        registros = []
        for item in itens if isinstance(itens, list) else []:
            m = NOME_HISTORICO.match(item.get('name', ''))
            if not m:
                continue  # README.md e outros arquivos que não seguem o padrão
            ano, mes, dia, hora, minuto, assunto = m.groups()
            registros.append({'arquivo': item['name'], 'quando': f'{ano}-{mes}-{dia}T{hora}:{minuto}',
                              'assunto': assunto.replace('-', ' ')})
        registros.sort(key=lambda r: r['arquivo'], reverse=True)
        registros = registros[:limite]

        async def titulo(reg):
            try:
                texto = await _github(cliente, f'/repos/{repositorio}/contents/{pasta}/{reg["arquivo"]}?ref={branch}', raw=True)
                reg['titulo'] = _titulo_markdown(texto) or reg['assunto']
            except FonteIndisponivel:
                reg['titulo'] = reg['assunto']
            return reg
        return list(await asyncio.gather(*(titulo(r) for r in registros)))


async def listar_commits(repositorio: str, branch: str, limite: int = 10) -> list:
    async with criar_cliente() as cliente:
        dados = await _github(cliente, f'/repos/{repositorio}/commits?sha={branch}&per_page={limite}')
    commits = []
    for c in dados if isinstance(dados, list) else []:
        info = c.get('commit') or {}
        mensagem = (info.get('message') or '').splitlines()
        commits.append({'sha': (c.get('sha') or '')[:7], 'titulo': mensagem[0] if mensagem else '',
                        'autor': (info.get('author') or {}).get('name') or '',
                        'quando': (info.get('author') or {}).get('date') or '',
                        'link': c.get('html_url') or ''})
    return commits


# ── Pendências: "## PEN 1 — Título" + linhas "- **Campo:** valor" ─────
_CABECALHO_PEN = re.compile(r'^##\s+((?:PEN|TEC)\s*\d+)\s*[—–:-]\s*(.+?)\s*$', re.MULTILINE)
_CAMPO = re.compile(r'^\s*[-*]\s*\*\*([^*:]+):?\*\*:?\s*(.*?)\s*$')
_FECHADAS = ('concluída', 'concluida', 'feita', 'feito', 'cancelada', 'cancelado')


def ler_pendencias(markdown: str) -> list:
    """Transforma o BACKLOG.md em itens. Formato (ver BACKLOG.md da autopeças):

        ## PEN 1 — Título
        - **Status:** aberta
        - **Prioridade:** alta
        Texto livre com o contexto...
    """
    # Exemplos dentro de ``` (como o modelo no topo do BACKLOG.md) não são pendências.
    markdown = re.sub(r'^```.*?^```[^\n]*$', '', markdown, flags=re.MULTILINE | re.DOTALL)
    cabecalhos = list(_CABECALHO_PEN.finditer(markdown))
    itens = []
    for i, m in enumerate(cabecalhos):
        fim = cabecalhos[i + 1].start() if i + 1 < len(cabecalhos) else len(markdown)
        bloco = markdown[m.end():fim]
        # Um "## " de outra seção encerra o item (ex.: "## Concluídas").
        outra_secao = re.search(r'^#{1,2}\s', bloco, re.MULTILINE)
        if outra_secao:
            bloco = bloco[:outra_secao.start()]
        campos, texto = {}, []
        for linha in bloco.splitlines():
            c = _CAMPO.match(linha)
            if c and not texto:
                campos[c.group(1).strip().lower()] = c.group(2).strip()
            elif linha.strip():
                texto.append(linha.strip())
        status = campos.get('status', 'aberta').lower()
        itens.append({
            'codigo': re.sub(r'\s+', ' ', m.group(1)).upper(),
            'titulo': m.group(2),
            'status': status,
            'aberta': not status.startswith(_FECHADAS),
            'prioridade': campos.get('prioridade', '').lower(),
            'aberta_em': campos.get('aberta em', ''),
            'descricao': ' '.join(texto)[:700],
        })
    return itens


def formatar_data_iso(valor: Optional[str]) -> str:
    if not valor:
        return '?'
    try:
        quando = datetime.fromisoformat(valor.replace('Z', '+00:00'))
    except ValueError:
        return valor
    if quando.tzinfo:
        quando = quando.astimezone(BRT)
    return quando.strftime('%d/%m %H:%M')


BRT = timezone(timedelta(hours=-3))
