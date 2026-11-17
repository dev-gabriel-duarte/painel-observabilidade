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
import unicodedata
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


# Texto de cada registro, guardado pelo "sha" que o GitHub dá a cada arquivo. O sha
# é calculado a partir do conteúdo: mesmo sha = mesmo texto, para sempre. Então um
# registro já lido nunca é baixado de novo — só os novos ou os que alguém editou.
# Por isso este guardado NÃO é apagado pelo "Atualizar agora": ele não envelhece.
_TEXTOS_POR_SHA: dict = {}
LIMITE_TEXTOS_GUARDADOS = 1000
LIMITE_REGISTROS = 500        # teto da linha do tempo, por segurança
DOWNLOADS_SIMULTANEOS = 8     # não abrir centenas de conexões com o GitHub de uma vez
TAMANHO_MAXIMO_REGISTRO = 200_000


async def _registros_com_texto(cliente, repositorio: str, pasta: str, branch: str, limite: int) -> list:
    """Lista os registros da pasta (mais novo primeiro) e devolve [(registro, texto)].
    Texto None = aquele arquivo não pôde ser lido (o resto continua)."""
    try:
        itens = await _github(cliente, f'/repos/{repositorio}/contents/{pasta}?ref={branch}')
    except FonteIndisponivel as erro:
        if 'Não encontrado' in str(erro):
            return []  # projeto ainda sem pasta historico/
        raise
    registros = []
    for item in itens if isinstance(itens, list) else []:
        nome = item.get('name', '') if isinstance(item, dict) else ''
        m = NOME_HISTORICO.match(nome)
        if not m:
            continue  # README.md e outros arquivos que não seguem o padrão
        ano, mes, dia, hora, minuto, assunto = m.groups()
        registros.append({'arquivo': nome, 'quando': f'{ano}-{mes}-{dia}T{hora}:{minuto}',
                          'assunto': assunto.replace('-', ' '), '_sha': str(item.get('sha') or '')})
    registros.sort(key=lambda r: r['arquivo'], reverse=True)
    registros = registros[:limite]
    vez = asyncio.Semaphore(DOWNLOADS_SIMULTANEOS)

    async def ler(reg):
        sha = reg.pop('_sha')
        if sha and sha in _TEXTOS_POR_SHA:
            return reg, _TEXTOS_POR_SHA[sha]
        async with vez:
            try:
                texto = await _github(cliente, f'/repos/{repositorio}/contents/{pasta}/{reg["arquivo"]}?ref={branch}', raw=True)
            except FonteIndisponivel:
                return reg, None
        texto = str(texto)[:TAMANHO_MAXIMO_REGISTRO]
        if sha:
            if len(_TEXTOS_POR_SHA) >= LIMITE_TEXTOS_GUARDADOS:
                _TEXTOS_POR_SHA.clear()  # memória limitada: recomeça do zero
            _TEXTOS_POR_SHA[sha] = texto
        return reg, texto
    return list(await asyncio.gather(*(ler(r) for r in registros)))


async def listar_historico(repositorio: str, pasta: str, branch: str, limite: int = 15) -> list:
    async with criar_cliente() as cliente:
        lidos = await _registros_com_texto(cliente, repositorio, pasta, branch, limite)
    for reg, texto in lidos:
        reg['titulo'] = (_titulo_markdown(texto) if texto else '') or reg['assunto']
    return [reg for reg, _ in lidos]


async def listar_linha_do_tempo(repositorio: str, pasta: str, branch: str) -> list:
    """Todos os registros, já interpretados, do mais ANTIGO para o mais novo
    (a ordem em que a história aconteceu)."""
    async with criar_cliente() as cliente:
        lidos = await _registros_com_texto(cliente, repositorio, pasta, branch, LIMITE_REGISTROS)
    pontos = []
    for reg, texto in lidos:
        ponto = ler_registro(texto or '', reg['arquivo'], repositorio)
        ponto.update(quando=reg['quando'], ilegivel=texto is None,
                     titulo=(_titulo_markdown(texto) if texto else '') or reg['assunto'])
        pontos.append(ponto)
    pontos.sort(key=lambda p: p['arquivo'])
    return pontos


MESES = ('janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro',
         'outubro', 'novembro', 'dezembro')


def agrupar_em_etapas(pontos: list) -> list:
    """Divide a história em etapas (os cartões lado a lado da aba Linha do tempo).

    Cada MARCO (registro com "Impacto: alto") abre uma etapa, e as mudanças que vêm
    depois dele, até o próximo marco, ficam dentro dela. O nome é a linha "Etapa:"
    do marco (curta); sem ela, o título do registro. Projeto que ainda não marcou
    nenhum marco: uma etapa por mês, para a tela nunca ficar vazia.
    `pontos` chega do mais antigo para o mais novo (listar_linha_do_tempo)."""
    tem_marco = any(p.get('impacto') == 'alto' for p in pontos)
    etapas = []
    for p in pontos:
        mes = p['quando'][:7]
        e_marco = tem_marco and p.get('impacto') == 'alto'
        abre = e_marco if tem_marco else (not etapas or etapas[-1]['mes'] != mes)
        if abre or not etapas:
            if tem_marco:
                nome = p.get('etapa') or p['titulo']
            else:
                nome = f'{MESES[int(mes[5:7]) - 1]} de {mes[:4]}' if re.fullmatch(r'\d{4}-\d{2}', mes) else mes
            etapas.append({'nome': nome, 'marco': p['arquivo'] if e_marco else '',
                           'tipo': (p.get('tipos') or ['sem'])[0], 'mes': mes, 'pontos': []})
        etapas[-1]['pontos'].append(p)
    return etapas


# ── Cabeçalho de um registro: "- **Tipo:** função nova" etc. ──────────
# Formato no historico/README.md da autopeças. Campo que falta fica vazio:
# registro sem "Tipo" aparece como "sem tipo" — nada é adivinhado.
_CAMPO_REGISTRO = re.compile(r'^\s*[-*]\s*\*\*([^*]+)\*\*\s*:?\s*(.*?)\s*$')
# Exige um dígito: "acabada" só tem letras de a a f, mas não é commit.
_SHA_COMMIT = re.compile(r'\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b')
TIPOS = {
    'funcao nova': 'funcao', 'nova funcao': 'funcao', 'funcao': 'funcao', 'novidade': 'funcao',
    'melhoria': 'melhoria',
    'correcao': 'correcao', 'correcao de bug': 'correcao', 'bug': 'correcao',
    'seguranca': 'seguranca',
    'infraestrutura': 'infraestrutura', 'infra': 'infraestrutura',
    'documentacao': 'documentacao', 'docs': 'documentacao',
}
IMPACTOS = ('alto', 'medio', 'baixo')


def _sem_acento(texto: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', texto or '') if unicodedata.category(c) != 'Mn').lower().strip()


def _cortar(texto: str, limite: int) -> str:
    texto = ' '.join((texto or '').split())
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(' ', 1)[0].rstrip(',;:') + '…'


def ler_registro(markdown: str, arquivo: str = '', repositorio: str = '') -> dict:
    """Transforma um registro do historico/ num ponto da linha do tempo.

        # Título
        - **Data do push:** ...
        - **Branch:** main (produção)
        - **Commits:** abc1234, def5678
        - **Publicado na produção?** Sim
        - **Tipo:** função nova, segurança
        - **Impacto:** alto
        - **Resumo:** uma frase do que muda para a loja.
        - **Versão:** 3.4.0   (opcional: só quando o sistema tem número de verdade)
        - **Etapa:** Agenda com 3 boxes   (opcional, só nos marcos: nome curto da etapa)

        ## Contexto
        Primeiro parágrafo — vira o resumo quando falta a linha "Resumo".
    """
    campos, ultimo, contexto = {}, None, []
    secao, contexto_acabou = None, False
    for linha in (markdown or '')[:TAMANHO_MAXIMO_REGISTRO].replace('\r\n', '\n').split('\n'):
        if linha.startswith('## '):
            secao = _sem_acento(linha[3:])
            continue
        if secao is None:
            campo = _CAMPO_REGISTRO.match(linha)
            if campo:
                ultimo = _sem_acento(campo.group(1)).rstrip(':?').strip()
                campos[ultimo] = campo.group(2).strip()
            elif ultimo and linha[:1].isspace() and linha.strip():
                campos[ultimo] += ' ' + linha.strip()  # valor que quebrou de linha
            else:
                ultimo = None
        elif secao.startswith('contexto') and not contexto_acabou:
            if linha.strip():
                contexto.append(linha.strip())
            elif contexto:
                contexto_acabou = True  # só o primeiro parágrafo

    tipos = []
    for parte in re.split(r'[,;/+]|\s+e\s+', campos.get('tipo', '')):
        chave = _sem_acento(parte).strip(' .')
        if chave:
            tipo = TIPOS.get(chave, 'outro')
            if tipo not in tipos:
                tipos.append(tipo)
    impacto = (_sem_acento(campos.get('impacto', '')).split() or [''])[0].strip('.,;')
    publicado = _sem_acento(campos.get('publicado na producao', ''))
    shas = list(dict.fromkeys(_SHA_COMMIT.findall(campos.get('commits', ''))))[:30]
    base = f'https://github.com/{repositorio}/commit/' if repositorio else ''
    return {
        'arquivo': arquivo,
        'tipos': tipos,
        'impacto': impacto if impacto in IMPACTOS else '',
        'resumo': _cortar(campos.get('resumo') or ' '.join(contexto), 320),
        'versao': _cortar(campos.get('versao', '').strip('` '), 20),
        'etapa': _cortar(campos.get('etapa', ''), 40),
        'na_producao': True if publicado.startswith('sim') else False if publicado.startswith('nao') else None,
        'publicado': _cortar(campos.get('publicado na producao', ''), 240),
        'branch': _cortar(campos.get('branch', '').replace('`', ''), 160),
        'commits': [{'sha': s[:7], 'link': f'{base}{s}' if base else ''} for s in shas],
    }


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
