// Painel de observabilidade — tela única (login, workspaces, detalhe).
// Todo dado vindo da API entra como TEXTO (createTextNode), nunca como HTML.

const $ = (id) => document.getElementById(id);

function el(tag, atributos = {}, ...filhos) {
  const no = document.createElement(tag);
  for (const [chave, valor] of Object.entries(atributos)) {
    if (valor === false || valor === null || valor === undefined) continue;
    if (chave === 'class') no.className = valor;
    else if (chave.startsWith('on')) no.addEventListener(chave.slice(2), valor);
    else if (chave === 'cor') no.style.setProperty('--cor-ws', valor);
    else if (chave.startsWith('--')) no.style.setProperty(chave, valor); // cor das etapas (constante nossa)
    else no.setAttribute(chave, valor === true ? '' : valor);
  }
  for (const filho of filhos.flat()) {
    if (filho === null || filho === undefined || filho === false) continue;
    no.append(filho instanceof Node ? filho : document.createTextNode(String(filho)));
  }
  return no;
}

// Ícones escritos por nós (nunca dado de fora).
const ICONES = {
  ferramenta: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>',
  caixa: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  loja: '<path d="M3 9 5 4h14l2 5M3 9v11h18V9M3 9h18M9 20v-6h6v6"/>',
  grafico: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  codigo: '<path d="m8 8-5 4 5 4M16 8l5 4-5 4M14 4l-4 16"/>',
  estrela: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
  subir: '<path d="m3 17 6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
  escudo: '<path d="M12 3 20 6v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  servidor: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  documento: '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  bandeira: '<path d="M5 21V4h11l-2 4 2 4H5"/>',
};
function icone(nome) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = ICONES[nome] || ICONES.caixa;
  return svg;
}

async function api(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, {
    credentials: 'same-origin',
    headers: opcoes.body ? { 'Content-Type': 'application/json' } : {},
    ...opcoes,
  });
  let corpo = null;
  try { corpo = await resposta.json(); } catch { /* resposta sem JSON */ }
  if (!resposta.ok) {
    const erro = new Error((corpo && corpo.detail) || `Erro ${resposta.status}`);
    erro.status = resposta.status;
    throw erro;
  }
  return corpo;
}

const reais = (v) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const ROTULOS = { ok: 'Tudo no ar', atencao: 'Atenção', fora: 'Fora do ar', desconhecido: 'Sem dados',
  lento: 'Lento' };
const ROTULO_SISTEMA = { ok: 'No ar', lento: 'Atenção', fora: 'Fora', desconhecido: 'Sem dados' };

function dataCurta(iso) {
  if (!iso) return '';
  const d = new Date(iso.length === 16 ? `${iso}:00-03:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
}

function selo(estado, rotulos = ROTULOS) {
  return el('span', { class: 'selo' }, el('span', { class: `ponto ${estado}` }), rotulos[estado] || estado);
}

// ── Sessão ─────────────────────────────────────────────
async function iniciar() {
  try {
    const { nome } = await api('/api/sessao');
    entrarNoApp(nome);
  } catch {
    $('tela-login').hidden = false;
    $('codigo').focus();
  }
}

function entrarNoApp(nome) {
  $('tela-login').hidden = true;
  $('app').hidden = false;
  $('quem').textContent = nome;
  rotear();
}

$('form-login').addEventListener('submit', async (evento) => {
  evento.preventDefault();
  const botao = evento.submitter;
  botao.disabled = true;
  $('erro-login').textContent = '';
  try {
    const { nome } = await api('/api/login', { method: 'POST', body: JSON.stringify({ codigo: $('codigo').value }) });
    $('codigo').value = '';
    entrarNoApp(nome);
  } catch (erro) {
    $('erro-login').textContent = erro.message;
  } finally {
    botao.disabled = false;
  }
});

$('botao-sair').addEventListener('click', async () => {
  await api('/api/sair', { method: 'POST' }).catch(() => {});
  location.hash = '';
  location.reload();
});

$('botao-atualizar').addEventListener('click', async () => {
  // Guarda o botão antes do await: evento.currentTarget vira null depois dele.
  const botao = $('botao-atualizar');
  botao.disabled = true;
  try {
    await api('/api/atualizar', { method: 'POST' });
    await rotear();
  } finally {
    botao.disabled = false;
  }
});

function sessaoCaiu(erro) {
  if (erro.status !== 401) return false;
  $('app').hidden = true;
  $('tela-login').hidden = false;
  return true;
}

// ── Rotas: #/, #/ws/<slug>, #/ws/<slug>/links e #/ws/<slug>/linha ──
window.addEventListener('hashchange', rotear);
let carregando = 0;

async function rotear() {
  const ws = location.hash.match(/^#\/ws\/([a-z0-9-]+)(?:\/(links|linha))?$/);
  const minha = ++carregando;
  const conteudo = $('conteudo');
  conteudo.replaceChildren(el('div', { class: 'esqueleto' }), el('div', { class: 'esqueleto' }));
  try {
    if (ws) {
      // A linha do tempo vem numa rota própria: ler todos os registros só quando a aba é aberta.
      const [dados, linha] = await Promise.all([api(`/api/workspaces/${ws[1]}`),
        ws[2] === 'linha' ? api(`/api/workspaces/${ws[1]}/linha-do-tempo`) : null]);
      if (minha !== carregando) return;
      desenharWorkspace(dados, ws[2] || 'geral', linha);
    } else {
      const dados = await api('/api/workspaces');
      if (minha !== carregando) return;
      desenharInicio(dados);
    }
    $('atualizado').textContent = `Atualizado às ${new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
  } catch (erro) {
    if (sessaoCaiu(erro)) return;
    conteudo.replaceChildren(el('p', { class: 'aviso-fonte' }, erro.message));
  }
}

function trilha(...partes) {
  const itens = [el('a', { href: '#/' }, 'Workspaces')];
  for (const p of partes) itens.push(el('span', { class: 'sep' }, '/'), el('span', {}, p));
  $('trilha').replaceChildren(...itens);
}

// ── Início: todos os workspaces ───────────────────────
function desenharInicio(d) {
  trilha();
  document.title = 'Observabilidade';
  const sistemas = d.workspaces.reduce((a, w) => ({ ok: a.ok + w.sistemas.ok, total: a.total + w.sistemas.total }), { ok: 0, total: 0 });
  const pendencias = d.workspaces.reduce((a, w) => a + w.pendencias_abertas, 0);
  const aConfirmar = d.workspaces.reduce((a, w) => a + w.custos_a_confirmar, 0) + d.custos_gerais.a_confirmar;

  $('conteudo').replaceChildren(
    el('div', { class: 'titulo-pagina' },
      el('div', {}, el('h1', {}, 'Workspaces'),
        el('p', { class: 'suave' }, 'Sistemas, custos, pendências e alterações de cada projeto.'))),
    el('div', { class: 'metricas' },
      metrica('Projetos', d.workspaces.length),
      metrica('Sistemas no ar', `${sistemas.ok}/${sistemas.total}`),
      metrica('Pendências abertas', pendencias),
      metrica('Custo mensal estimado', reais(d.total_mensal_brl), aConfirmar ? `${aConfirmar} item(ns) a confirmar` : 'todos confirmados')),
    el('h2', { class: 'secao-titulo' }, 'Projetos'),
    el('div', { class: 'grade-ws' }, d.workspaces.map(cartaoWorkspace), el('div', { class: 'cartao-novo' },
      el('strong', {}, '+ Novo projeto'),
      el('span', {}, 'Copie '), el('code', {}, 'workspaces/_modelo.json'),
      el('span', {}, 'com outro nome, preencha e publique.'))),
    el('h2', { class: 'secao-titulo' }, 'Custos de todos os projetos'),
    el('section', { class: 'painel' }, tabelaCustos(d.custos_gerais, d.cotacao_data)),
  );
}

function metrica(rotulo, valor, detalhe) {
  return el('div', { class: 'metrica' }, el('span', {}, rotulo), el('strong', {}, valor), detalhe ? el('small', {}, detalhe) : null);
}

function cartaoWorkspace(w) {
  const ultima = w.ultima_alteracao;
  return el('a', { class: 'cartao-ws', href: `#/ws/${w.slug}`, cor: w.cor },
    el('div', { class: 'ws-cabeca' },
      el('span', { class: 'ws-icone' }, icone(w.icone)),
      el('div', {}, el('h2', {}, w.nome), el('p', {}, w.descricao))),
    el('div', { class: 'ws-numeros' },
      el('div', {}, el('span', {}, 'Sistemas'), el('strong', {}, `${w.sistemas.ok}/${w.sistemas.total}`)),
      el('div', {}, el('span', {}, 'Pendências'), el('strong', {}, w.pendencias_erro ? '?' : w.pendencias_abertas)),
      el('div', {}, el('span', {}, 'Custo/mês'), el('strong', {}, reais(w.custo_mensal_brl)))),
    el('div', { class: 'ws-rodape' },
      selo(w.estado),
      el('span', { class: 'ultima' }, ultima ? `Última alteração: ${dataCurta(ultima.quando)}` : 'Sem registros no histórico')));
}

// ── Um workspace ──────────────────────────────────────
let filtroPendencias = 'abertas';

const NOME_ABA = { links: 'Links', linha: 'Linha do tempo' };

function desenharWorkspace(w, aba, linha) {
  trilha(w.nome, ...(NOME_ABA[aba] ? [NOME_ABA[aba]] : []));
  document.title = `${NOME_ABA[aba] ? `${NOME_ABA[aba]} · ` : ''}${w.nome} · Observabilidade`;
  const atalhos = w.links.filter((l) => l.destaque && l.url);
  $('conteudo').replaceChildren(
    el('div', { class: 'titulo-pagina' },
      el('div', { class: 'cabeca-ws', cor: w.cor },
        el('span', { class: 'ws-icone' }, icone(w.icone)),
        el('div', {}, el('h1', {}, w.nome), el('p', { class: 'suave' }, w.descricao))),
      selo(w.estado)),
    el('nav', { class: 'abas', 'aria-label': 'Seções do projeto' },
      el('a', { href: `#/ws/${w.slug}`, 'aria-current': aba === 'geral' ? 'page' : null }, 'Visão geral'),
      el('a', { href: `#/ws/${w.slug}/linha`, 'aria-current': aba === 'linha' ? 'page' : null }, 'Linha do tempo'),
      el('a', { href: `#/ws/${w.slug}/links`, 'aria-current': aba === 'links' ? 'page' : null }, `Links (${w.links.length})`)),
    aba === 'links' ? painelLinks(w) : aba === 'linha' ? painelLinhaDoTempo(w, linha) : visaoGeral(w, atalhos),
  );
}

function visaoGeral(w, atalhos) {
  return el('div', {},
    atalhos.length ? el('div', { class: 'links' }, atalhos.map((l) => linkExterno(l.url, l.nome, 'botao'))) : null,
    el('div', { class: 'grade-detalhe' },
      el('div', { class: 'coluna' }, painelPendencias(w), painelHistorico(w), painelCommits(w)),
      el('div', { class: 'coluna' }, painelSistemas(w),
        el('section', { class: 'painel' }, el('div', { class: 'painel-topo' }, el('h2', {}, 'Custos'),
          el('span', { class: 'suave' }, 'por mês, em reais')), tabelaCustos(w.custos, w.cotacao_data)))));
}

// ── Aba Links: todos os endereços do projeto, por grupo ──
function painelLinks(w) {
  if (!w.links.length) return el('p', { class: 'vazio' }, 'Nenhum link configurado. Eles ficam em "links" no arquivo do workspace.');
  const grupos = new Map();
  for (const l of w.links) {
    if (!grupos.has(l.grupo)) grupos.set(l.grupo, []);
    grupos.get(l.grupo).push(l);
  }
  return el('div', { class: 'grade-links' }, [...grupos].map(([grupo, itens]) =>
    painel(grupo, `${itens.length} ${itens.length === 1 ? 'link' : 'links'}`,
      el('ul', { class: 'lista' }, itens.map(linhaLink)))));
}

function linhaLink(l) {
  return el('li', { class: 'link-item' },
    l.url && !l.copiar_apenas ? linkExterno(l.url, l.nome, 'link-nome') : el('strong', { class: 'link-nome' }, l.nome),
    l.url ? el('button', { class: 'botao fantasma copiar', type: 'button', 'aria-label': `Copiar o endereço de ${l.nome}`, onclick: (e) => copiar(l.url, e.currentTarget) }, 'Copiar') : null,
    el('span', { class: 'mono endereco' }, l.url ? l.url.replace(/^https?:\/\//, '') : 'endereço não guardado aqui'),
    l.descricao ? el('p', {}, l.descricao) : null);
}

async function copiar(texto, botao) {
  try {
    await navigator.clipboard.writeText(texto);
    botao.textContent = 'Copiado ✓';
  } catch {
    botao.textContent = 'Não copiou';
  }
  setTimeout(() => { botao.textContent = 'Copiar'; }, 1600);
}

function linkExterno(url, texto, classe) {
  // Só http(s): um "javascript:" num arquivo de configuração não vira link clicável.
  if (!/^https?:\/\//i.test(url || '')) return el('span', { class: classe }, texto);
  return el('a', { class: classe, href: url, target: '_blank', rel: 'noopener noreferrer' }, texto);
}

function painel(titulo, detalhe, ...corpo) {
  return el('section', { class: 'painel' },
    el('div', { class: 'painel-topo' }, el('h2', {}, titulo), detalhe ? (detalhe instanceof Node ? detalhe : el('span', { class: 'suave' }, detalhe)) : null),
    ...corpo);
}

function avisoFonte(bloco) {
  return bloco.erro ? el('p', { class: 'aviso-fonte' }, bloco.erro) : null;
}

function painelSistemas(w) {
  const itens = w.sistemas.dados;
  return painel('Sistemas', `${itens.filter((s) => s.estado === 'ok').length} de ${itens.length} no ar`,
    avisoFonte(w.sistemas),
    itens.length ? el('ul', { class: 'lista' }, itens.map((s) => el('li', { class: 'sistema' },
      el('span', { class: `ponto ${s.estado}`, title: ROTULO_SISTEMA[s.estado] }),
      el('strong', {}, s.nome),
      el('small', {}, s.detalhe),
      s.painel ? linkExterno(s.painel, 'Abrir ↗') : null))) : el('p', { class: 'vazio' }, 'Nenhum sistema configurado.'));
}

function painelPendencias(w) {
  const todas = w.pendencias.dados;
  const lista = el('ul', { class: 'lista' });
  const desenhar = () => {
    const visiveis = filtroPendencias === 'abertas' ? todas.filter((p) => p.aberta) : todas;
    lista.replaceChildren(...visiveis.map((p) => el('li', { class: `pendencia${p.aberta ? '' : ' fechada'}` },
      el('span', { class: 'codigo' }, p.codigo),
      el('strong', {}, p.titulo),
      p.prioridade ? el('span', { class: `prioridade ${p.prioridade}` }, p.prioridade) : el('span'),
      el('p', {}, inline(p.descricao || '')),
      el('small', { class: 'meta-pendencia' }, [p.status !== 'aberta' && p.status, p.aberta_em && `desde ${p.aberta_em}`].filter(Boolean).join(' · ')))));
    if (!visiveis.length) lista.replaceChildren(el('li', { class: 'suave' }, todas.length ? 'Nenhuma pendência aberta.' : 'Nenhuma pendência no BACKLOG.md.'));
    filtro.querySelectorAll('button').forEach((b) => b.classList.toggle('ativo', b.dataset.f === filtroPendencias));
  };
  const filtro = el('div', { class: 'filtro', role: 'group', 'aria-label': 'Filtrar pendências' },
    ['abertas', 'todas'].map((f) => el('button', { type: 'button', 'data-f': f, onclick: () => { filtroPendencias = f; desenhar(); } },
      f === 'abertas' ? `Abertas (${todas.filter((p) => p.aberta).length})` : `Todas (${todas.length})`)));
  desenhar();
  return painel('Pendências', filtro, avisoFonte(w.pendencias), lista);
}

function painelHistorico(w) {
  const itens = w.historico.dados;
  return painel('Alterações', el('a', { class: 'ver-mais', href: `#/ws/${w.slug}/linha` }, 'Linha do tempo →'), avisoFonte(w.historico),
    itens.length ? el('ul', { class: 'lista' }, itens.map((r) => el('li', { class: 'registro' },
      el('button', { type: 'button', onclick: () => abrirRegistro(w.slug, r) },
        el('strong', {}, r.titulo), el('small', {}, dataCurta(r.quando)))))) :
      (w.historico.erro ? null : el('p', { class: 'vazio' }, 'Nenhum registro em historico/ ainda.')));
}

function painelCommits(w) {
  const itens = w.commits.dados;
  return painel('Últimos commits', w.repositorio, avisoFonte(w.commits),
    itens.length ? el('ul', { class: 'lista' }, itens.map((c) => el('li', { class: 'commit' },
      el('span', { class: 'mono' }, c.sha),
      linkExterno(c.link, c.titulo),
      el('small', {}, `${c.autor} · ${dataCurta(c.quando)}`)))) : null);
}

function tabelaCustos(custos, cotacaoData) {
  const linhas = custos.itens.map((c) => el('tr', {},
    el('td', {}, c.item, c.confirmado ? null : el('span', { class: 'estimado' }, c.mensal_brl === null ? 'a confirmar' : 'estimado'),
      c.obs ? el('small', {}, c.obs) : null),
    el('td', {}, c.mensal_brl === null ? '—' : reais(c.mensal_brl),
      c.moeda !== 'BRL' && c.valor !== null ? el('small', {}, `${c.moeda} ${c.valor}${c.periodo === 'anual' ? '/ano' : ''}`) : null)));
  return el('table', { class: 'tabela-custos' },
    el('tbody', {}, linhas),
    el('tfoot', {}, el('tr', {}, el('td', {}, 'Total', cotacaoData ? el('small', {}, `Cotação de ${cotacaoData}`) : null),
      el('td', {}, reais(custos.total_mensal_brl)))));
}

// ── Aba Linha do tempo: a história do projeto em etapas ──
// Cartões lado a lado, ligados por linhas. Quem divide as etapas é o servidor
// (fontes.agrupar_em_etapas): cada marco abre uma etapa e as mudanças seguintes
// ficam dentro dela — o número na bolinha. Tocar numa etapa mostra as mudanças
// embaixo; a última, tracejada, são as pendências abertas ("Próximos").
const TIPOS = {
  funcao: 'Função nova', melhoria: 'Melhoria', correcao: 'Correção', seguranca: 'Segurança',
  infraestrutura: 'Infraestrutura', documentacao: 'Documentação', outro: 'Outro', sem: 'Sem tipo',
};
const ICONE_DO_TIPO = { funcao: 'estrela', melhoria: 'subir', correcao: 'ferramenta', seguranca: 'escudo',
  infraestrutura: 'servidor', documentacao: 'documento', outro: 'caixa', sem: 'caixa' };
const COR_COMECO = '#e9ecef';
const CORES_ETAPA = ['#4cc9f0', '#f7c948', '#a78bfa', '#f472b6', '#4ade80', '#fb923c', '#38bdf8', '#e879f9'];
const COR_PROXIMOS = '#9aa1ad';
const escolhida = { slug: '', indice: -1 };

const tiposDe = (p) => (p.tipos.length ? p.tipos : ['sem']);
const diaDoRegistro = (q) => `${q.slice(8, 10)}/${q.slice(5, 7)}/${q.slice(0, 4)}`;
const corDaEtapa = (i) => (i === 0 ? COR_COMECO : CORES_ETAPA[(i - 1) % CORES_ETAPA.length]);
const rotuloDaEtapa = (i) => (i === 0 ? 'Começo' : `Etapa ${i}`);

function periodo(pontos) {
  const de = diaDoRegistro(pontos[0].quando);
  const ate = diaDoRegistro(pontos[pontos.length - 1].quando);
  return de === ate ? de : `${de} a ${ate}`;
}

function painelLinhaDoTempo(w, linha) {
  const etapas = linha.etapas.dados;
  const proximos = linha.proximos.dados;
  if (!etapas.length) {
    return el('div', {}, avisoFonte(linha.etapas), linha.etapas.erro ? null
      : el('p', { class: 'vazio' }, 'Nenhum registro em historico/ ainda. Cada arquivo de lá entra numa etapa desta linha do tempo.'));
  }
  const pontos = etapas.flatMap((e) => e.pontos);
  const conta = (teste) => pontos.filter(teste).length;
  const semTipo = conta((p) => !p.tipos.length);
  const temProximos = proximos.length > 0 || Boolean(linha.proximos.erro);
  const total = etapas.length + (temProximos ? 1 : 0);
  if (escolhida.slug !== w.slug || escolhida.indice < 0 || escolhida.indice >= total) {
    escolhida.slug = w.slug;
    escolhida.indice = etapas.length - 1; // abre na etapa atual
  }

  const nos = [];
  const trilho = el('div', { class: 'trilho' });
  etapas.forEach((etapa, i) => {
    if (i > 0) trilho.append(el('span', { class: 'conector', '--cor-etapa': corDaEtapa(i), 'aria-hidden': 'true' }));
    const no = el('button', { type: 'button', class: 'no-etapa', '--cor-etapa': corDaEtapa(i),
      'aria-label': `${rotuloDaEtapa(i)}: ${etapa.nome}. ${etapa.pontos.length} ${etapa.pontos.length === 1 ? 'mudança' : 'mudanças'}, ${periodo(etapa.pontos)}`,
      title: etapa.nome, onclick: () => escolher(i) },
    el('span', { class: 'no-icone' }, icone(ICONE_DO_TIPO[etapa.tipo] || 'caixa')),
    el('span', { class: 'no-textos' },
      el('span', { class: 'no-rotulo' }, rotuloDaEtapa(i)),
      el('strong', { class: 'no-titulo' }, etapa.nome)),
    el('span', { class: 'no-contagem', 'aria-hidden': 'true' }, etapa.pontos.length));
    nos.push(no);
    trilho.append(no);
  });
  if (temProximos) {
    trilho.append(el('span', { class: 'conector proximo', '--cor-etapa': COR_PROXIMOS, 'aria-hidden': 'true' }));
    const no = el('button', { type: 'button', class: 'no-etapa proximo', '--cor-etapa': COR_PROXIMOS,
      'aria-label': `Próximos: ${proximos.length} ${proximos.length === 1 ? 'pendência aberta' : 'pendências abertas'}`,
      onclick: () => escolher(etapas.length) },
    el('span', { class: 'no-icone' }, icone('bandeira')),
    el('span', { class: 'no-textos' }, el('span', { class: 'no-rotulo' }, 'Próximos'), el('strong', { class: 'no-titulo' }, 'Pendências abertas')),
    el('span', { class: 'no-contagem', 'aria-hidden': 'true' }, proximos.length));
    nos.push(no);
    trilho.append(no);
  }

  const palco = el('div', { class: 'palco', role: 'group', 'aria-label': 'Etapas do projeto' }, trilho);
  const detalhe = el('div', { class: 'detalhe-area' });
  arrastavel(palco);
  palco.addEventListener('keydown', (e) => {
    const passo = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (!passo || !nos.includes(document.activeElement)) return;
    e.preventDefault();
    const i = Math.min(Math.max(escolhida.indice + passo, 0), nos.length - 1);
    escolher(i);
    nos[i].focus({ preventScroll: true });
  });

  function centralizar(i, suave) {
    const no = nos[i];
    const alvo = no.offsetLeft - (palco.clientWidth - no.offsetWidth) / 2;
    palco.scrollTo({ left: Math.max(alvo, 0), behavior: suave && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto' });
  }

  function marcar(i) {
    escolhida.indice = i;
    nos.forEach((no, j) => { no.classList.toggle('escolhida', j === i); no.setAttribute('aria-pressed', String(j === i)); });
    detalhe.replaceChildren(i < etapas.length ? detalheEtapa(w, etapas[i], i) : detalheProximos(linha.proximos));
  }
  function escolher(i) {
    marcar(i);
    centralizar(i, true);
  }

  marcar(escolhida.indice);
  // Centraliza a etapa escolhida depois que o palco está na tela (precisa das medidas).
  requestAnimationFrame(() => centralizar(escolhida.indice, false));

  return el('div', {},
    el('div', { class: 'metricas' },
      metrica('Mudanças registradas', pontos.length, `desde ${diaDoRegistro(pontos[0].quando)}`),
      metrica('Etapas', etapas.length, 'cada uma começa num marco'),
      metrica('Correções', conta((p) => p.tipos.includes('correcao')), 'bugs que ganharam registro'),
      metrica('Só no teste', conta((p) => p.na_producao === false), 'esperando ir para a produção')),
    semTipo ? el('p', { class: 'aviso-fonte solto' }, `${semTipo} ${semTipo === 1 ? 'registro ainda não tem' : 'registros ainda não têm'} a linha "Tipo" no cabeçalho. O modelo está no historico/README.md do projeto.`) : null,
    palco,
    el('p', { class: 'dica-palco' }, 'Deslize ou arraste para o lado e toque numa etapa para ver as mudanças dela.'),
    detalhe);
}

// Arrastar com o mouse para o lado, como na imagem de referência. No toque, o
// próprio navegador já rola: o arraste só vale para o mouse.
function arrastavel(palco) {
  let inicio = null;
  let arrastou = false;
  palco.addEventListener('pointerdown', (e) => {
    if (e.pointerType !== 'mouse' || e.button !== 0) return;
    inicio = { x: e.clientX, rolagem: palco.scrollLeft, id: e.pointerId };
    arrastou = false;
  });
  palco.addEventListener('pointermove', (e) => {
    if (!inicio) return;
    const dx = e.clientX - inicio.x;
    if (!arrastou && Math.abs(dx) > 5) {
      arrastou = true;
      palco.classList.add('arrastando');
      palco.setPointerCapture(inicio.id);
    }
    if (arrastou) palco.scrollLeft = inicio.rolagem - dx;
  });
  const soltar = () => { inicio = null; palco.classList.remove('arrastando'); };
  palco.addEventListener('pointerup', soltar);
  palco.addEventListener('pointercancel', soltar);
  // Um arraste que termina em cima de um cartão não conta como toque nele.
  palco.addEventListener('click', (e) => {
    if (!arrastou) return;
    arrastou = false;
    e.stopPropagation();
    e.preventDefault();
  }, true);
}

function detalheEtapa(w, etapa, i) {
  const marco = etapa.pontos.find((p) => p.arquivo === etapa.marco);
  return el('section', { class: 'detalhe-etapa', '--cor-etapa': corDaEtapa(i) },
    el('div', { class: 'detalhe-cabeca' },
      el('span', { class: 'no-rotulo' }, `${rotuloDaEtapa(i)} · ${periodo(etapa.pontos)}`),
      el('h2', {}, etapa.nome),
      marco && marco.resumo ? el('p', { class: 'resumo-tempo' }, inline(marco.resumo)) : null),
    el('ol', { class: 'mudancas' }, etapa.pontos.map((p) => linhaMudanca(w, p))));
}

function detalheProximos(bloco) {
  return el('section', { class: 'detalhe-etapa', '--cor-etapa': COR_PROXIMOS },
    el('div', { class: 'detalhe-cabeca' },
      el('span', { class: 'no-rotulo' }, 'Próximos · BACKLOG.md'),
      el('h2', {}, 'Pendências abertas'),
      el('p', { class: 'resumo-tempo' }, 'O que ainda vai acontecer: primeiro o que já está em andamento, depois por prioridade.')),
    avisoFonte(bloco),
    el('ol', { class: 'mudancas' }, bloco.dados.map((p) => el('li', { class: 'mudanca' },
      el('div', { class: 'meta-tempo' }, el('span', { class: 'codigo' }, p.codigo),
        p.status.includes('andamento') ? el('span', { class: 'selo-mini andamento' }, 'em andamento') : null,
        p.prioridade ? el('span', { class: `prioridade ${p.prioridade}` }, p.prioridade) : null),
      el('strong', { class: 'titulo-pendencia' }, p.titulo),
      p.descricao ? el('p', { class: 'resumo-tempo curto' }, inline(p.descricao)) : null))));
}

function linhaMudanca(w, p) {
  const commits = p.commits.slice(0, 4);
  return el('li', { class: `mudanca t-${tiposDe(p)[0]}` },
    el('div', { class: 'meta-tempo' },
      el('time', { datetime: p.quando }, diaDoRegistro(p.quando)),
      tiposDe(p).map((t) => el('span', { class: `tipo t-${t}` }, TIPOS[t] || TIPOS.outro)),
      p.impacto === 'alto' ? el('span', { class: 'selo-mini marco' }, 'Marco') : null,
      p.versao ? el('span', { class: 'selo-mini versao' }, `v${p.versao.replace(/^v/i, '')}`) : null,
      p.na_producao === null ? null : el('span', { class: `selo-mini ${p.na_producao ? 'producao' : 'teste'}`, title: p.publicado || null },
        p.na_producao ? 'Na produção' : 'Só no teste')),
    el('button', { type: 'button', class: 'titulo-tempo', onclick: () => abrirRegistro(w.slug, p) }, p.titulo),
    p.resumo ? el('p', { class: 'resumo-tempo' }, inline(p.resumo)) : null,
    el('div', { class: 'rodape-tempo' },
      commits.length ? el('span', { class: 'commits-tempo' }, commits.map((c) => linkExterno(c.link, c.sha, 'mono')),
        p.commits.length > commits.length ? el('span', { class: 'suave' }, `+${p.commits.length - commits.length}`) : null) : el('span'),
      el('button', { type: 'button', class: 'ler-registro', onclick: () => abrirRegistro(w.slug, p) }, 'Ler o registro →')));
}

// ── Leitura de um registro do histórico ───────────────
async function abrirRegistro(slug, registro) {
  $('gaveta-titulo').textContent = dataCurta(registro.quando);
  $('gaveta-corpo').replaceChildren(el('div', { class: 'esqueleto' }));
  $('gaveta').setAttribute('aria-hidden', 'false');
  $('fundo-gaveta').hidden = false;
  try {
    const { markdown } = await api(`/api/workspaces/${slug}/historico/${encodeURIComponent(registro.arquivo)}`);
    $('gaveta-corpo').replaceChildren(...renderizarMarkdown(markdown));
  } catch (erro) {
    if (sessaoCaiu(erro)) return;
    $('gaveta-corpo').replaceChildren(el('p', { class: 'aviso-fonte' }, erro.message));
  }
}

function fecharGaveta() {
  $('gaveta').setAttribute('aria-hidden', 'true');
  $('fundo-gaveta').hidden = true;
}
$('fechar-gaveta').addEventListener('click', fecharGaveta);
$('fundo-gaveta').addEventListener('click', fecharGaveta);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharGaveta(); });

// Markdown simples (títulos, listas, negrito, código, links), montado nó por
// nó — o texto do arquivo nunca vira HTML.
function inline(texto) {
  const nos = [];
  const padrao = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let ultimo = 0;
  for (const m of texto.matchAll(padrao)) {
    if (m.index > ultimo) nos.push(texto.slice(ultimo, m.index));
    if (m[2]) nos.push(el('strong', {}, m[2]));
    else if (m[3]) nos.push(el('code', {}, m[3]));
    else nos.push(linkExterno(m[5], m[4]));
    ultimo = m.index + m[0].length;
  }
  if (ultimo < texto.length) nos.push(texto.slice(ultimo));
  return nos;
}

function renderizarMarkdown(md) {
  const blocos = [];
  const linhas = md.replace(/\r\n/g, '\n').split('\n');
  let lista = null;
  let paragrafo = [];
  const fecharParagrafo = () => { if (paragrafo.length) blocos.push(el('p', {}, inline(paragrafo.join(' ')))); paragrafo = []; };
  const fecharLista = () => { lista = null; };
  for (let i = 0; i < linhas.length; i++) {
    const linha = linhas[i];
    if (linha.startsWith('```')) {
      fecharParagrafo(); fecharLista();
      const codigo = [];
      for (i++; i < linhas.length && !linhas[i].startsWith('```'); i++) codigo.push(linhas[i]);
      blocos.push(el('pre', {}, el('code', {}, codigo.join('\n'))));
      continue;
    }
    const titulo = linha.match(/^(#{1,3})\s+(.*)$/);
    const item = linha.match(/^\s*(?:[-*]|\d+\.)\s+(.*)$/);
    if (titulo) { fecharParagrafo(); fecharLista(); blocos.push(el(`h${titulo[1].length}`, {}, inline(titulo[2]))); }
    else if (item) {
      fecharParagrafo();
      if (!lista) { lista = el(/^\s*\d+\./.test(linha) ? 'ol' : 'ul'); blocos.push(lista); }
      lista.append(el('li', {}, inline(item[1])));
    } else if (linha.startsWith('>')) { fecharParagrafo(); fecharLista(); blocos.push(el('blockquote', {}, inline(linha.replace(/^>\s?/, '')))); }
    else if (!linha.trim()) { fecharParagrafo(); fecharLista(); }
    else if (lista && /^\s{2,}/.test(linha)) lista.lastChild.append(' ', ...inline(linha.trim()));
    else paragrafo.push(linha.trim());
  }
  fecharParagrafo();
  return blocos;
}

iniciar();
