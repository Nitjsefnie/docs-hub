# Live Document Auto-Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the docs-hub SPA auto-refresh the open screen every 30 s so new versions and new docs appear without a manual reload — the viewer auto-swaps its iframe to a newer version when tracking latest.

**Architecture:** One global, route-aware `setInterval` in `public/app.js`. Each tick force-refreshes the current screen's data, computes a cheap per-screen signature, and re-renders only when that signature changes. The viewer's signature is the *resolved displayed version* (latest for a bare slug, the pinned `n` for `/v<n>`), so a bare-slug viewer swaps on a new publish while a pinned view is never disturbed. Frontend-only; no backend, DB, or API changes.

**Tech Stack:** Vanilla ES (no framework, no build step) in `public/app.js`; FastAPI backend (unchanged); pytest (backend regression only).

**Spec:** `docs/superpowers/specs/2026-05-29-doc-autoreload-design.html` · published at https://docs.nitjsefni.eu/d/docs-hub/2026-05-29-doc-autoreload-design

---

## Testing note (read first)

This repo has **no JavaScript test harness** — `tests/` is pytest against the FastAPI backend only, and the spec (§08) explicitly defers adding a JS runner as out of scope. So the standard automated-TDD red/green loop does **not** apply to these `app.js` changes. Instead each task uses:

1. **`node --check public/app.js`** — a real automated guard that the file still parses (node v22 confirmed available).
2. **A manual browser check** against a running instance — see "Running the app for manual checks" below.
3. **`.venv/bin/pytest -v`** at the end — confirms the backend is untouched and still green.

This is a deliberate, spec-sanctioned deviation from automated TDD, not an oversight.

### Running the app for manual checks

The SPA is a static asset served by the FastAPI app, which reads `public/app.js` fresh on each request (`views.py` stamps `?v=<mtime>` to bust caches), so no rebuild is needed — just reload the browser.

```bash
# from repo root, with the venv and .env already set up (see AGENTS.md)
.venv/bin/uvicorn backend.app:app --port 8084
```

Then open `http://localhost:8084/` (log in with the shared authdb credentials). To make a new version land while watching, publish a throwaway version from another terminal:

```bash
python3 ~/.claude/scripts/docs_hub.py publish /tmp/probe.html \
  --slug docs-hub/_autoreload-probe --title "probe" --from manual_test --project docs-hub
```

Re-running that command bumps the probe doc's version each time. Delete it when done via the CLI's delete flow. (If running a local server with auth/DB is impractical, the alternative is to verify on the live site *after* deploy using the same throwaway slug — the change is a static asset with zero backend impact.)

---

## File Structure

All changes are in one file. No files are created.

| File | Responsibility | Change |
|------|----------------|--------|
| `public/app.js` | SPA: routing, data layer, screen rendering | Add a `force` refresh path to the data layer, per-screen signature helpers, last-rendered-signature tracking, and a global poll loop wired at boot. |

The data-layer functions `loadDocs` / `loadVersions` are called only from `render()` (verified via LSP `findReferences`: `loadDocs` at lines 526/529/533, `loadVersions` at 530/534). Adding an optional `force = false` parameter is backward-compatible with all existing zero-arg calls.

---

### Task 1: Add a `force` refresh path to the data layer

**Files:**
- Modify: `public/app.js` (functions `loadDocs` ~line 39, `loadVersions` ~line 47)

Currently both functions cache once and never refetch. The poller needs to refetch fresh and overwrite the cache, while normal navigation keeps using the cache.

- [ ] **Step 1: Replace `loadDocs` with a `force`-aware version**

Find:

```javascript
async function loadDocs() {
  if (_docs === null) {
    const j = await fetchJSON('/api/list');
    _docs = j.docs || [];
  }
  return _docs;
}
```

Replace with:

```javascript
async function loadDocs(force = false) {
  if (_docs === null || force) {
    const j = await fetchJSON('/api/list');
    _docs = j.docs || [];
  }
  return _docs;
}
```

- [ ] **Step 2: Replace `loadVersions` with a `force`-aware version**

Find:

```javascript
async function loadVersions(slug) {
  if (!(slug in _versions)) {
    try {
      const j = await fetchJSON('/api/versions/' + slug);
      _versions[slug] = j.versions || [];
    } catch (e) {
      _versions[slug] = [];
    }
  }
  return _versions[slug];
}
```

Replace with:

```javascript
async function loadVersions(slug, force = false) {
  if (!(slug in _versions) || force) {
    try {
      const j = await fetchJSON('/api/versions/' + slug);
      _versions[slug] = j.versions || [];
    } catch (e) {
      // On a forced refresh failure, keep whatever we already had rather
      // than clobbering it to []. Only seed [] on a true first-load failure.
      if (!(slug in _versions)) _versions[slug] = [];
    }
  }
  return _versions[slug];
}
```

- [ ] **Step 3: Syntax check**

Run: `node --check public/app.js`
Expected: exit 0 (no output).

- [ ] **Step 4: Manual smoke check**

With the app running, open `http://localhost:8084/`, click into a doc, open its version log. Expected: everything still loads and navigates exactly as before (no behavioral change yet — `force` defaults to `false`).

- [ ] **Step 5: Commit**

```bash
git add public/app.js
git commit -m "feat: add force-refresh path to SPA data layer

loadDocs/loadVersions gain an optional force flag (default false) that
refetches and overwrites the cache. Backward-compatible with all
existing zero-arg callers in render(). On a forced loadVersions failure,
preserve existing data instead of clobbering to [].

Co-Authored-By: <MODEL NAME> <noreply@anthropic.com>"
```

---

### Task 2: Add signature helpers and last-rendered-signature tracking

**Files:**
- Modify: `public/app.js` (data-layer var block ~lines 13-15; new helpers; `render()` ~line 518)

A "signature" is a cheap deterministic string of exactly what a screen *displays*. Re-rendering only when it changes is the load-bearing guard (spec §07, HIGH risk): without it the viewer iframe would reload every tick.

- [ ] **Step 1: Add the `_lastSig` module variable**

Find:

```javascript
let _docs = null;        // cached GET /api/list
const _versions = {};    // slug → GET /api/versions/<slug>
let _whoami = null;      // cached GET /api/whoami
```

Replace with:

```javascript
let _docs = null;        // cached GET /api/list
const _versions = {};    // slug → GET /api/versions/<slug>
let _whoami = null;      // cached GET /api/whoami
let _lastSig = null;     // signature of the currently-rendered screen (poll gate)
```

- [ ] **Step 2: Add the signature helpers**

Insert these functions immediately above the `// ─── router ───` section (just before `function parseRoute()`, ~line 505):

```javascript
// ─────────────────────────── poll signatures ───────────────────────────
// A cheap deterministic string of exactly what each screen DISPLAYS, so the
// poll loop re-renders only when the visible output would actually change.

function sigIndex() {
  return (_docs || [])
    .map((d) => d.slug + '|' + d.latest_version + '|' + d.updated_at)
    .join('\n');
}

function sigVersions(slug) {
  return (_versions[slug] || [])
    .map((v) => v.version + '|' + v.sha256)
    .join('\n');
}

// The viewer keys off the ONE version on screen, not the whole list. A route
// pinned to /v<n> resolves to n (never changes on publish → no reload); a bare
// slug resolves to latest (bumps when a new version lands → iframe swaps).
function sigViewer(route) {
  const doc = (_docs || []).find((d) => d.slug === route.slug);
  return String(route.version ?? (doc && doc.latest_version) ?? '?');
}

function currentSig(route) {
  if (route.name === 'index') return sigIndex();
  if (route.name === 'versions') return sigVersions(route.slug);
  if (route.name === 'viewer') return sigViewer(route);
  return null;
}
```

- [ ] **Step 3: Stamp `_lastSig` at the end of `render()`**

Find the end of `render()`:

```javascript
  document.title =
    ({
      index: 'docs.nitjsefni.eu',
      versions: 'versions · docs',
      viewer: (route.slug || '') + ' · docs',
      '404': '404 · docs',
    })[route.name] || 'docs.nitjsefni.eu';
}
```

Replace with:

```javascript
  document.title =
    ({
      index: 'docs.nitjsefni.eu',
      versions: 'versions · docs',
      viewer: (route.slug || '') + ' · docs',
      '404': '404 · docs',
    })[route.name] || 'docs.nitjsefni.eu';
  _lastSig = currentSig(route);
}
```

- [ ] **Step 4: Syntax check**

Run: `node --check public/app.js`
Expected: exit 0.

- [ ] **Step 5: Manual smoke check**

Reload `http://localhost:8084/` and navigate index → viewer → version log. Expected: no behavioral change (the signature is computed and stored but nothing reads it yet). In DevTools console, after loading the index, typing `_lastSig` is not accessible (module scope) — instead confirm there are no console errors on navigation.

- [ ] **Step 6: Commit**

```bash
git add public/app.js
git commit -m "feat: add per-screen poll signatures and last-rendered tracking

sigIndex/sigVersions/sigViewer produce a cheap deterministic string of
what each screen displays; render() stamps the current screen's signature
into _lastSig. The viewer signature is the resolved displayed version so a
pinned /v<n> view is gated out of re-render. No behavior change yet.

Co-Authored-By: <MODEL NAME> <noreply@anthropic.com>"
```

---

### Task 3: Add the poll loop and wire it at boot

**Files:**
- Modify: `public/app.js` (new functions near the bottom; boot listeners ~lines 557-558)

This is the functional payoff. One `setInterval`, route-aware, with the focus guard and visibility pause from the spec (§03, §05).

- [ ] **Step 1: Add the poll-loop functions**

Insert immediately above the boot listeners at the bottom of the file (just before `window.addEventListener('hashchange', render);`):

```javascript
// ─────────────────────────── poll loop ───────────────────────────
// One global, route-aware timer. Each tick force-refreshes the current
// screen's data and re-renders only when its signature changed. Pauses
// while the tab is hidden; fires once immediately when the tab is reshown.

const POLL_MS = 30_000;

function indexFilterFocused() {
  const el = document.activeElement;
  return !!(el && el.closest && el.closest('.filterbar'));
}

function maybeRerender(sig) {
  if (sig === _lastSig) return;                 // signature gate: nothing changed
  if (parseRoute().name === 'index' && indexFilterFocused()) return; // defer mid-filter
  render();                                     // render() re-stamps _lastSig
}

async function pollTick() {
  if (document.visibilityState === 'hidden') return;
  const route = parseRoute();
  try {
    if (route.name === 'index') {
      await loadDocs(true);
      maybeRerender(sigIndex());
    } else if (route.name === 'viewer') {
      await loadDocs(true);                      // refreshes latest_version
      await loadVersions(route.slug, true);      // refreshes the new version object
      maybeRerender(sigViewer(route));           // resolved DISPLAYED version only
    } else if (route.name === 'versions') {
      await loadDocs(true);
      await loadVersions(route.slug, true);
      maybeRerender(sigVersions(route.slug));
    }
  } catch (e) {
    // Swallow — a failed tick is skipped, the next one recovers. Never tear
    // the screen into the error view over a transient blip.
  }
}

function startPolling() {
  setInterval(pollTick, POLL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') pollTick();
  });
}
```

- [ ] **Step 2: Wire `startPolling` into boot**

Find:

```javascript
window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', render);
```

Replace with:

```javascript
window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', render);
window.addEventListener('DOMContentLoaded', startPolling);
```

- [ ] **Step 3: Syntax check**

Run: `node --check public/app.js`
Expected: exit 0.

- [ ] **Step 4: Manual functional check — viewer auto-swap**

With the app running and `/tmp/probe.html` created (`echo '<h1>probe v1</h1>' > /tmp/probe.html`):
1. Publish the probe once (command in "Running the app" above), open `http://localhost:8084/#/d/docs-hub/_autoreload-probe` (bare slug — tracking latest).
2. Edit `/tmp/probe.html` and publish again.
3. Within ~30 s the iframe content updates to the new version and the `v{n} / v{m}` counter advances. Expected: PASS.

To shorten the wait while testing, temporarily set `POLL_MS = 3000`, then restore to `30_000` before committing.

- [ ] **Step 5: Manual functional check — pinned view is left in place**

1. On the probe doc, click the `←` nav arrow to pin an older `/v<n>` (URL now ends `/v1`).
2. Publish a new version. Expected: the iframe does **not** change and scroll position is preserved (PASS). The `{m}` in the counter may lag — expected per spec §08.

- [ ] **Step 6: Manual functional check — index + log live-update and focus guard**

1. Sit on `http://localhost:8084/#/` and publish a new version → the probe row's version bumps within ~30 s.
2. Start typing in the `search` box and publish during the wait → the table does **not** re-render mid-keystroke; it updates on the next tick after the input loses focus. Expected: PASS.
3. Sit on `…/_autoreload-probe/versions` and publish → a new row appears and the `latest` badge moves. Expected: PASS.

- [ ] **Step 7: Manual functional check — quiescence**

Leave a viewer open with no publishing. In DevTools Network tab, confirm `/api/list` + `/api/versions/...` are fetched each tick but the iframe document is **not** reloaded (no new `/d/.../v...` request). Switch to another tab for a minute and confirm polling pauses (no fetches), then resumes on return. Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add public/app.js
git commit -m "feat: live auto-reload of the open SPA screen every 30s

A single route-aware poll loop force-refreshes the current screen's data
and re-renders only when its signature changes. The viewer auto-swaps its
iframe to a new version when tracking latest; pinned /v<n> views stay put.
Index re-render is deferred while a filter input is focused; polling pauses
on a hidden tab and fires once on reshow.

Co-Authored-By: <MODEL NAME> <noreply@anthropic.com>"
```

---

### Task 4: Full verification pass and regression

**Files:** none (verification only)

- [ ] **Step 1: Final syntax check**

Run: `node --check public/app.js`
Expected: exit 0.

- [ ] **Step 2: Backend regression**

Run: `.venv/bin/pytest -v`
Expected: all tests pass (the backend was not touched; this confirms it).

- [ ] **Step 3: Confirm `POLL_MS` is 30_000**

Run: `grep -n "POLL_MS = " public/app.js`
Expected: shows `const POLL_MS = 30_000;` (not a shortened test value).

- [ ] **Step 4: Walk the spec §06 checklist**

Re-confirm each item from spec §06 passed during Task 3: viewer auto-swap, stale view left alone, index live-update, filter focus guard, version log live-update, no-change quiescence, pytest green. Note any that could not be exercised and why.

- [ ] **Step 5: Clean up the probe doc**

Delete the throwaway via the CLI's two-step delete flow:

```bash
python3 ~/.claude/scripts/docs_hub.py --help   # confirm delete subcommand usage if present
```

If the CLI has no delete, remove it through the `/api/delete` preview→confirm flow, or leave a note that `docs-hub/_autoreload-probe` is a test artifact to be removed manually.

---

## Self-Review

**Spec coverage:**
- §02 single global poll loop → Task 3. ✓
- §03 per-screen behaviour (viewer/index/log, focus guard, visibility pause) → Task 3 steps 1, 4–7. ✓
- §04 change inventory (force path, sig helpers, `_lastSig` stamp, `startPolling`) → Tasks 1, 2, 3. ✓
- §05 data/control flow (pollTick, maybeRerender, sigViewer) → Task 3 step 1. ✓
- §06 verification checklist → Task 3 steps 4–7, Task 4. ✓
- §07 risks (signature gate, focus guard, swallow failures, deleted version) → signature gate Task 2/3, focus guard Task 3, try/catch Task 3, deleted-version handled by existing `renderNotFound` on re-render. ✓
- §08 out of scope (SSE, JS harness, configurable interval, in-place counter) → none implemented, as intended. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/etc. The only intentional token is `<MODEL NAME>` in commit trailers, which the executing agent fills with its own model name per the repo convention.

**Type consistency:** `loadDocs(force)`, `loadVersions(slug, force)`, `sigIndex()`, `sigVersions(slug)`, `sigViewer(route)`, `currentSig(route)`, `maybeRerender(sig)`, `pollTick()`, `startPolling()`, `indexFilterFocused()`, `_lastSig`, `POLL_MS` — names used consistently across Tasks 2 and 3. `route` object shape (`{name, slug, version}`) matches `parseRoute()`'s existing returns.
