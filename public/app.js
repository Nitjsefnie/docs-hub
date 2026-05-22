// docs-hub mockup — hash-routed screens.
// Routes:
//   #/                  → index
//   #/login             → login
//   #/d/<slug>          → doc viewer (chrome + iframe)
//   #/d/<slug>/v<n>     → doc viewer at specific version
//   #/d/<slug>/versions → version history
//   #/404               → not found

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ─────────────────────────── utilities ───────────────────────────

function fmtBytes(n) {
  if (n < 1024) return n + ' b';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' kb';
  return (n / (1024 * 1024)).toFixed(2) + ' mb';
}

function relTime(iso) {
  const t = new Date(iso).getTime();
  const now = new Date('2026-05-22T11:42:00Z').getTime();
  const d = Math.max(0, now - t);
  const mins = d / 60_000;
  if (mins < 1) return 'just now';
  if (mins < 60) return Math.round(mins) + 'm ago';
  const hours = mins / 60;
  if (hours < 24) return Math.round(hours) + 'h ago';
  const days = hours / 24;
  if (days < 14) return Math.round(days) + 'd ago';
  if (days < 60) return Math.round(days / 7) + 'w ago';
  return Math.round(days / 30) + 'mo ago';
}

function absTime(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getUTCFullYear() +
    '-' +
    pad(d.getUTCMonth() + 1) +
    '-' +
    pad(d.getUTCDate()) +
    ' ' +
    pad(d.getUTCHours()) +
    ':' +
    pad(d.getUTCMinutes())
  );
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

function uniq(arr) { return [...new Set(arr)]; }

// ─────────────────────────── filter state ───────────────────────────

const FILTER = {
  q: '',
  project: '',
  agent: '',
  tag: '',
  sort: 'updated',     // updated | title | version
  sortDir: 'desc',     // desc | asc
};

// Default direction per key, used when the user picks a new sort field.
const SORT_DEFAULT_DIR = {
  title: 'asc', slug: 'asc', project: 'asc', tags: 'desc',
  agent: 'asc', updated: 'desc', version: 'desc', size: 'desc',
};

function setSort(key) {
  if (FILTER.sort === key) {
    FILTER.sortDir = FILTER.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    FILTER.sort = key;
    FILTER.sortDir = SORT_DEFAULT_DIR[key] || 'desc';
  }
}

function applyFilters(docs) {
  let out = docs.slice();
  if (FILTER.q) {
    const q = FILTER.q.toLowerCase();
    out = out.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        d.slug.toLowerCase().includes(q),
    );
  }
  if (FILTER.project) out = out.filter((d) => d.project === FILTER.project);
  if (FILTER.agent)   out = out.filter((d) => d.posted_by === FILTER.agent);
  if (FILTER.tag)     out = out.filter((d) => d.tags.includes(FILTER.tag));

  const dir = FILTER.sortDir === 'asc' ? 1 : -1;
  const sizeOf = (d) => window.VERSIONS[d.slug]?.[0]?.byte_size ?? 0;
  const cmp = {
    title:   (a, b) => a.title.localeCompare(b.title),
    slug:    (a, b) => a.slug.localeCompare(b.slug),
    project: (a, b) => (a.project || '').localeCompare(b.project || ''),
    tags:    (a, b) => a.tags.length - b.tags.length,
    agent:   (a, b) => a.posted_by.localeCompare(b.posted_by),
    updated: (a, b) => new Date(a.updated_at) - new Date(b.updated_at),
    version: (a, b) => a.latest_version - b.latest_version,
    size:    (a, b) => sizeOf(a) - sizeOf(b),
  }[FILTER.sort] || (() => 0);
  out.sort((a, b) => dir * cmp(a, b));
  return out;
}

// ─────────────────────────── screens ───────────────────────────

function renderTopbar(opts = {}) {
  // crumbs: array of {label, href?}
  const crumbs = opts.crumbs || [];
  const crumbHtml = crumbs.length
    ? crumbs
        .map((c, i) => {
          const piece = c.href
            ? `<a href="${esc(c.href)}">${esc(c.label)}</a>`
            : `<span class="here">${esc(c.label)}</span>`;
          return (i ? '<span class="sep">/</span>' : '') + piece;
        })
        .join('')
    : '';

  return `
    <header class="topbar">
      <a href="#/" class="brand" style="color:inherit">
        <span class="prompt">$</span>
        <span class="host">docs.nitjsefni.eu</span>
        <span class="cursor"></span>
      </a>
      <div class="crumbs">${crumbHtml}</div>
      <div class="meta">
        <span>user <span class="who">19</span></span>
        <span class="dot">·</span>
        <a href="#/login" title="Sign out">logout</a>
      </div>
    </header>
  `;
}

function renderIndex() {
  const docs = applyFilters(window.DOCS);
  const total = window.DOCS.length;
  const allProjects = uniq(window.DOCS.map((d) => d.project).filter(Boolean)).sort();
  const allAgents   = uniq(window.DOCS.map((d) => d.posted_by)).sort();
  const allTags     = uniq(window.DOCS.flatMap((d) => d.tags)).sort();

  const opt = (val, label, sel) =>
    `<option value="${esc(val)}" ${val === sel ? 'selected' : ''}>${esc(label)}</option>`;

  const headers = [
    { key: 'title',   label: 'Title / Slug' },
    { key: 'project', label: 'Project' },
    { key: 'tags',    label: 'Tags' },
    { key: 'agent',   label: 'Agent' },
    { key: 'updated', label: 'Updated' },
    { key: 'version', label: 'Ver' },
    { key: 'size',    label: 'Size', align: 'right' },
  ];

  const headHtml = headers
    .map((h) => {
      const active = FILTER.sort === h.key;
      const glyph = active ? (FILTER.sortDir === 'asc' ? '▲' : '▼') : '▼';
      const cls = active ? '' : 'inactive';
      const style = h.align === 'right' ? 'text-align:right' : '';
      const titleAttr = active
        ? `title="sort by ${h.label.toLowerCase()} — reverse"`
        : `title="sort by ${h.label.toLowerCase()}"`;
      return `<th class="${cls}" style="${style}" ${titleAttr} data-sort="${h.key}">${esc(h.label)}<span class="arrow">${glyph}</span></th>`;
    })
    .join('');

  const rowHtml = docs.length
    ? docs
        .map((d) => {
          const latest = window.VERSIONS[d.slug]?.[0];
          const size = latest ? fmtBytes(latest.byte_size) : '';
          return `
            <tr>
              <td class="title-cell">
                <a class="t" href="#/d/${esc(d.slug)}">${esc(d.title)}</a>
                <div class="slug"><span class="prompt">›</span>${esc(d.slug)}</div>
              </td>
              <td class="proj">${esc(d.project || '—')}</td>
              <td class="tags">${d.tags.map((t) => `<span class="tag" data-tag="${esc(t)}">${esc(t)}</span>`).join('')}</td>
              <td class="agent">${esc(d.posted_by)}</td>
              <td class="upd">
                <span class="rel">${relTime(d.updated_at)}</span>
                <span class="abs">${absTime(d.updated_at)}</span>
              </td>
              <td class="ver">
                <a class="v" href="#/d/${esc(d.slug)}">v${d.latest_version}</a>
                <a class="hist" href="#/d/${esc(d.slug)}/versions" title="version history">log →</a>
              </td>
              <td class="size tnum">${size}</td>
            </tr>
          `;
        })
        .join('')
    : `<tr class="empty"><td colspan="${headers.length}">no docs match these filters · <a href="#" id="clear-filters">clear all</a></td></tr>`;

  return `
    ${renderTopbar({ crumbs: [{ label: 'index' }] })}
    <main class="main">
      <div class="filterbar">
        <div class="field">
          <span class="label">search</span>
          <input id="f-q" placeholder="title or slug…" value="${esc(FILTER.q)}" autocomplete="off">
        </div>
        <div class="field select">
          <span class="label">project</span>
          <select id="f-project">
            <option value="">all</option>
            ${allProjects.map((p) => opt(p, p, FILTER.project)).join('')}
          </select>
        </div>
        <div class="field select">
          <span class="label">agent</span>
          <select id="f-agent">
            <option value="">all</option>
            ${allAgents.map((a) => opt(a, a, FILTER.agent)).join('')}
          </select>
        </div>
        <div class="field select">
          <span class="label">tag</span>
          <select id="f-tag">
            <option value="">all</option>
            ${allTags.map((t) => opt(t, '#' + t, FILTER.tag)).join('')}
          </select>
        </div>
        <div class="count"><b class="accent">${docs.length}</b> / ${total} docs</div>
      </div>
      <table class="docs-table">
        <thead><tr>${headHtml}</tr></thead>
        <tbody>${rowHtml}</tbody>
      </table>
    </main>
  `;
}

function wireIndex() {
  const reroute = () => render();
  $('#f-q')?.addEventListener('input', (e) => { FILTER.q = e.target.value; reroute(); });
  $('#f-project')?.addEventListener('change', (e) => { FILTER.project = e.target.value; reroute(); });
  $('#f-agent')?.addEventListener('change', (e) => { FILTER.agent = e.target.value; reroute(); });
  $('#f-tag')?.addEventListener('change', (e) => { FILTER.tag = e.target.value; reroute(); });
  $$('[data-sort]').forEach((th) =>
    th.addEventListener('click', () => {
      setSort(th.dataset.sort);
      reroute();
    }),
  );
  $$('.docs-table .tag[data-tag]').forEach((el) =>
    el.addEventListener('click', () => {
      FILTER.tag = FILTER.tag === el.dataset.tag ? '' : el.dataset.tag;
      reroute();
    }),
  );
  $('#clear-filters')?.addEventListener('click', (e) => {
    e.preventDefault();
    Object.assign(FILTER, { q: '', project: '', agent: '', tag: '' });
    reroute();
  });
  // Restore focus + caret in the search box so typing feels continuous.
  if (FILTER.q) {
    const inp = $('#f-q');
    if (inp) {
      inp.focus();
      inp.setSelectionRange(inp.value.length, inp.value.length);
    }
  }
}

function renderDocViewer(slug, requestedVersion) {
  const doc = window.DOCS.find((d) => d.slug === slug);
  if (!doc) return renderNotFound('/d/' + slug);

  const versions = window.VERSIONS[slug] || [];
  const latest = doc.latest_version;
  const ver = requestedVersion ?? latest;
  const v = versions.find((x) => x.version === ver);
  if (!v) return renderNotFound('/d/' + slug + '/v' + ver);

  const isStale = ver !== latest;
  const idx = versions.findIndex((x) => x.version === ver);
  const newer = versions[idx - 1];
  const older = versions[idx + 1];

  const crumbs = [
    { label: 'index', href: '#/' },
    { label: doc.project || '—' },
    { label: slug.split('/').slice(1).join('/') || slug, href: '#/d/' + slug },
  ];

  return `
    ${renderTopbar({ crumbs })}
    <div class="docview">
      <div class="docchrome">
        <div class="left">
          <div class="title-row">
            <div class="title">${esc(doc.title)}</div>
            <div class="vtag ${isStale ? 'stale stale-warn' : ''}">v${v.version}</div>
          </div>
          <div class="meta">
            <span class="slug"><span class="prompt">›</span>${esc(slug)}</span>
            <span class="dot">·</span>
            <span>by <span class="agent">${esc(v.posted_by)}</span></span>
            <span class="dot">·</span>
            <span>${relTime(v.created_at)} · ${absTime(v.created_at)}</span>
            <span class="dot">·</span>
            <span>${fmtBytes(v.byte_size)}</span>
            <span class="dot">·</span>
            <span title="${esc(v.sha256)}">sha ${esc(v.sha256.slice(0, 10))}…</span>
          </div>
        </div>
        <div class="actions">
          <div class="nav-arrows">
            <button ${older ? `onclick="location.hash='#/d/${esc(slug)}/v${older.version}'"` : 'disabled'} title="older version">←</button>
            <span class="which">v${v.version} / v${latest}</span>
            <button ${newer ? `onclick="location.hash='#/d/${esc(slug)}/v${newer.version}'"` : 'disabled'} title="newer version">→</button>
          </div>
          ${isStale ? `<a class="btn accent" href="#/d/${esc(slug)}">latest →</a>` : ''}
          <a class="btn" href="#/d/${esc(slug)}/versions">log <span class="kbd">L</span></a>
          <button class="btn" id="copy-link" title="copy permalink">⎘ link</button>
        </div>
      </div>
      <div class="artifact-frame">
        <iframe id="artifact" sandbox="allow-same-origin" srcdoc="${esc(window.SAMPLE_ARTIFACT)}"></iframe>
      </div>
    </div>
  `;
}

function wireDocViewer() {
  $('#copy-link')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const url = location.href;
    if (navigator.clipboard) navigator.clipboard.writeText(url).catch(() => {});
    const old = btn.innerHTML;
    btn.innerHTML = '✓ copied';
    setTimeout(() => (btn.innerHTML = old), 1200);
  });
  document.addEventListener('keydown', _docKeydown);
}
const _docKeydown = (e) => {
  if (e.target.matches('input, textarea, select')) return;
  if (e.key === 'l' || e.key === 'L') {
    const m = location.hash.match(/^#\/d\/(.+?)(?:\/v\d+|\/versions)?$/);
    if (m) location.hash = '#/d/' + m[1] + '/versions';
  }
};

function renderVersions(slug) {
  const doc = window.DOCS.find((d) => d.slug === slug);
  if (!doc) return renderNotFound('/d/' + slug + '/versions');
  const versions = window.VERSIONS[slug] || [];
  const latest = doc.latest_version;

  const crumbs = [
    { label: 'index', href: '#/' },
    { label: doc.project || '—' },
    { label: slug.split('/').slice(1).join('/') || slug, href: '#/d/' + slug },
    { label: 'versions' },
  ];

  const rows = versions
    .map(
      (v) => `
      <div class="version-row" data-href="#/d/${esc(slug)}/v${v.version}">
        <div class="vtag ${v.version === latest ? 'latest' : ''}">v${v.version}</div>
        <div>
          <div class="who">${esc(v.posted_by)}</div>
          <div class="sha" title="${esc(v.sha256)}">sha ${esc(v.sha256.slice(0, 16))}…</div>
        </div>
        <div class="when">
          ${relTime(v.created_at)}
          <span class="abs">${absTime(v.created_at)}</span>
        </div>
        <div class="size tnum">${fmtBytes(v.byte_size)}</div>
        <div class="sha tnum">${esc(v.sha256.slice(0, 8))}</div>
        <div class="actions">
          <button class="render-btn">render →</button>
        </div>
      </div>
    `,
    )
    .join('');

  return `
    ${renderTopbar({ crumbs })}
    <main class="main">
      <div class="version-head">
        <div>
          <h1>${esc(doc.title)}</h1>
          <div class="sub"><span class="prompt">›</span>${esc(slug)} · ${versions.length} version${versions.length === 1 ? '' : 's'}</div>
        </div>
        <div class="version-actions">
          <a class="btn" href="#/d/${esc(slug)}">view latest →</a>
          <a class="btn" href="#/">← back to index</a>
        </div>
      </div>
      <div class="version-list">${rows}</div>
    </main>
  `;
}

function wireVersions() {
  $$('.version-row').forEach((row) =>
    row.addEventListener('click', () => {
      location.hash = row.dataset.href;
    }),
  );
}

function renderLogin() {
  return `
    <div class="login-shell">
      <form class="login-card" id="login-form">
        <div class="brandline">
          <span class="prompt">$</span>
          <span>docs.nitjsefni.eu</span>
          <span class="cursor"></span>
        </div>
        <p class="why">Sign in with your nitjsefni.eu credentials. Same user id and password as the other services on this host.</p>
        <label for="uid">User ID</label>
        <input id="uid" name="user_id" inputmode="numeric" pattern="[0-9]+" autocomplete="username" placeholder="19" required>
        <label for="pw">Password</label>
        <input id="pw" name="password" type="password" autocomplete="current-password" required>
        <button class="submit" type="submit">Sign in →</button>
        <div class="err" id="login-err"></div>
        <div class="foot">
          <span>HMAC session · strict cookie</span>
          <span>5/300s rate limit</span>
        </div>
      </form>
    </div>
  `;
}

function wireLogin() {
  $('#login-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const uid = $('#uid').value.trim();
    const pw = $('#pw').value;
    const err = $('#login-err');
    if (uid === '19' && pw === 'hunter2') {
      err.textContent = '';
      location.hash = '#/';
    } else {
      err.textContent = 'Invalid credentials.';
    }
  });
}

function renderNotFound(path) {
  return `
    ${renderTopbar({ crumbs: [{ label: '404' }] })}
    <div class="notfound">
      <div>
        <div class="code">4<span class="slash">/</span>4</div>
        <div class="path"><span class="prompt">›</span>${esc(path || location.hash.slice(1) || '/')}</div>
        <h2>No artifact under that slug.</h2>
        <p>The slug doesn't resolve to any published document, or that specific version doesn't exist yet. Re-publish from the agent CLI, or pick a different slug from the index.</p>
        <div class="actions">
          <a class="btn accent" href="#/">← back to index</a>
        </div>
      </div>
    </div>
  `;
}

// ─────────────────────────── router ───────────────────────────

function parseRoute() {
  const h = location.hash.replace(/^#/, '') || '/';
  if (h === '/' || h === '') return { name: 'index' };
  if (h === '/login') return { name: 'login' };
  if (h === '/404') return { name: '404' };
  let m = h.match(/^\/d\/(.+?)\/versions$/);
  if (m) return { name: 'versions', slug: m[1] };
  m = h.match(/^\/d\/(.+?)\/v(\d+)$/);
  if (m) return { name: 'viewer', slug: m[1], version: Number(m[2]) };
  m = h.match(/^\/d\/(.+)$/);
  if (m) return { name: 'viewer', slug: m[1], version: null };
  return { name: '404' };
}

function render() {
  document.removeEventListener('keydown', _docKeydown);
  const route = parseRoute();
  const root = $('#app');
  let html = '';
  switch (route.name) {
    case 'index':    html = renderIndex(); break;
    case 'login':    html = renderLogin(); break;
    case 'versions': html = renderVersions(route.slug); break;
    case 'viewer':   html = renderDocViewer(route.slug, route.version); break;
    case '404':      html = renderNotFound(); break;
  }
  root.innerHTML = html;
  switch (route.name) {
    case 'index':    wireIndex(); break;
    case 'login':    wireLogin(); break;
    case 'versions': wireVersions(); break;
    case 'viewer':   wireDocViewer(); break;
  }
  document.title = ({
    index: 'docs.nitjsefni.eu',
    login: 'sign in · docs',
    versions: 'versions · docs',
    viewer: route.slug + ' · docs',
    '404': '404 · docs',
  })[route.name];
}

window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', render);
