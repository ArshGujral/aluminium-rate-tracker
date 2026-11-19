// Cloudflare Worker that saves supplier quotes and markup to quotes.json in this repository, so the website can save
// with the PIN alone instead of a GitHub key on every device. It holds the GitHub key as a secret (GITHUB_TOKEN, a
// fine-grained token with Contents: read and write on this repository only) and checks every save against PIN_HASH,
// the SHA-256 of the PIN, so the PIN itself is never stored. Wrong PINs are counted per visitor in the ATTEMPTS KV
// namespace (if bound) and a visitor is refused for an hour after 10 of them.
//
// Requests (JSON POST to the worker's address):
//   { pin, op: "add", quote: {date, supplier, gauge, rate, mcxAtQuote?, note, createdAt} }
//   { pin, op: "delete", id }
//   { pin, op: "markup", markup: {markupPct, markup33, markup38, learn} }
//   { pin, op: "check" }                      (only checks the PIN)
// Each answers { ok: true, quotes, markup } or { ok: false, error } with a matching HTTP status.

const REPO = 'ArshGujral/aluminium-rate-tracker';
const FILE = 'quotes.json';
const ORIGINS = ['https://arshgujral.github.io'];
const MAX_WRONG = 10;

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const cors = {
      'Access-Control-Allow-Origin': ORIGINS.includes(origin) ? origin : ORIGINS[0],
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400',
      Vary: 'Origin',
    };
    const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'POST') return reply(405, { ok: false, error: 'Use POST.' });
    if (!env.GITHUB_TOKEN || !/^[0-9a-f]{64}$/.test(env.PIN_HASH || '')) return reply(500, { ok: false, error: 'The worker is not set up: GITHUB_TOKEN or PIN_HASH is missing.' });

    let body;
    try { body = await request.json(); } catch { return reply(400, { ok: false, error: 'Send JSON.' }); }

    // PIN check, with a limit on wrong guesses per visitor
    const who = 'wrong:' + (request.headers.get('CF-Connecting-IP') || 'unknown');
    const wrong = env.ATTEMPTS ? Number(await env.ATTEMPTS.get(who)) || 0 : 0;
    if (wrong >= MAX_WRONG) return reply(429, { ok: false, error: 'Too many wrong PINs. Try again in an hour.' });
    if ((await sha256(String(body.pin ?? ''))) !== env.PIN_HASH) {
      if (env.ATTEMPTS) await env.ATTEMPTS.put(who, String(wrong + 1), { expirationTtl: 3600 });
      return reply(403, { ok: false, error: 'Wrong PIN.' });
    }

    const change = makeChange(body);
    if (typeof change === 'string') return reply(400, { ok: false, error: change });

    // Read, change and save. If something else saved in between, GitHub refuses the stale copy; redo it on the new one.
    for (let tries = 0; tries < 4; tries++) {
      const cur = await readFile(env);
      if (!cur.ok) return reply(502, { ok: false, error: 'Could not read the quotes from GitHub (' + cur.status + ').' });
      if (!change) return reply(200, { ok: true, quotes: cur.doc.quotes, markup: cur.doc.markup || null });
      const next = change.apply(cur.doc);
      const put = await gh(env, 'PUT', { message: change.message, branch: 'main', sha: cur.sha, content: b64(JSON.stringify(next, null, 1) + '\n') });
      if (put.status === 409 || put.status === 422) continue;
      if (!put.ok) return reply(502, { ok: false, error: 'GitHub refused the save (' + put.status + ').' });
      return reply(200, { ok: true, quotes: next.quotes, markup: next.markup || null });
    }
    return reply(503, { ok: false, error: 'The quotes kept changing while saving. Try again.' });
  },
};

// Turns a request into { message, apply(doc) -> doc }, null for a plain check, or an error string.
function makeChange(body) {
  const text = (v, max) => (typeof v === 'string' ? v.trim().slice(0, max) : '');
  const num = (v, lo, hi) => (typeof v === 'number' && isFinite(v) && v >= lo && v <= hi ? v : null);
  if (body.op === 'check') return null;
  if (body.op === 'add') {
    const q = body.quote || {};
    const quote = {
      date: /^\d{4}-\d{2}-\d{2}$/.test(q.date) ? q.date : null,
      supplier: text(q.supplier, 60),
      gauge: ['32', '33', '38'].includes(q.gauge) ? q.gauge : '32',
      rate: num(q.rate, 1, 100000),
      note: text(q.note, 80),
      createdAt: new Date().toISOString(),
      id: 'q' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    };
    const m = num(q.mcxAtQuote, 1, 100000);
    if (m !== null) quote.mcxAtQuote = m;
    if (!quote.date || quote.rate === null) return 'A quote needs a date and a rate.';
    return { message: 'Add supplier quote: ' + quote.date + (quote.supplier ? ', ' + quote.supplier : ''), apply: (d) => ({ ...d, quotes: [...d.quotes, quote] }) };
  }
  if (body.op === 'delete') {
    const id = text(body.id, 40);
    if (!id) return 'Say which quote to delete.';
    return { message: 'Delete supplier quote', apply: (d) => ({ ...d, quotes: d.quotes.filter((q) => q.id !== id) }) };
  }
  if (body.op === 'markup') {
    const m = body.markup || {};
    const markup = { markupPct: num(m.markupPct, 0, 300), markup33: num(m.markup33, 0, 300), markup38: num(m.markup38, 0, 300), learn: m.learn !== false };
    if (markup.markupPct === null || markup.markup33 === null || markup.markup38 === null) return 'Markups must be between 0 and 300.';
    return { message: 'Change markup settings', apply: (d) => ({ ...d, markup }) };
  }
  return 'Unknown request.';
}

async function readFile(env) {
  const r = await gh(env, 'GET');
  if (!r.ok) return { ok: false, status: r.status };
  const f = await r.json();
  const doc = JSON.parse(unb64(f.content));
  return { ok: true, sha: f.sha, doc: { ...doc, quotes: Array.isArray(doc.quotes) ? doc.quotes : [] } };
}

function gh(env, method, body) {
  return fetch('https://api.github.com/repos/' + REPO + '/contents/' + FILE + (method === 'GET' ? '?ref=main' : ''), {
    method,
    headers: { Accept: 'application/vnd.github+json', Authorization: 'Bearer ' + env.GITHUB_TOKEN, 'User-Agent': 'alu-quotes-worker', 'X-GitHub-Api-Version': '2022-11-28', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
}

async function sha256(s) {
  const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
function b64(s) { const bytes = new TextEncoder().encode(s); let bin = ''; bytes.forEach((b) => { bin += String.fromCharCode(b); }); return btoa(bin); }
function unb64(s) { const bin = atob(String(s).replace(/\s/g, '')); return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0))); }
