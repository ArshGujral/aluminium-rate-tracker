// Cloudflare Worker for the Aluminium Rate Tracker: checks the PIN and keeps the supplier quotes and markup private.
//
// The quotes and markup live in this worker's KV namespace (binding ATTEMPTS, key "store:doc"), not in the public
// GitHub repository, so only someone with the PIN can read or change them. The PIN is the secret PIN (set in
// Cloudflare, never in the page or the repository); PIN_HASH (its SHA-256) is accepted only until PIN is set.
// Wrong PINs are counted per visitor in the same namespace, and a visitor is refused for an hour after 10 of them.
//
// On the first request after an upgrade from the GitHub-stored version, the quotes are copied once from the
// repository's quotes.json (this needs GITHUB_TOKEN; afterwards the token can be removed from the worker).
//
// Requests (JSON POST to the worker's address):
//   { pin, op: "check" }                    unlock: answers the quotes and markup
//   { pin, op: "add", quote: {date, supplier, gauge, rate, mcxAtQuote?, note} }
//   { pin, op: "delete", id }
//   { pin, op: "markup", markup: {markupPct, markup33, markup38, learn} }
// Each answers { ok: true, quotes, markup } or { ok: false, error } with a matching HTTP status.

const REPO = 'ArshGujral/aluminium-rate-tracker';
const ORIGINS = ['https://arshgujral.github.io'];
const MAX_WRONG = 10;
const DOC = 'store:doc';

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const cors = {
      'Access-Control-Allow-Origin': ORIGINS.includes(origin) ? origin : ORIGINS[0],
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400',
      'Cache-Control': 'no-store',
      Vary: 'Origin',
    };
    const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'POST') return reply(405, { ok: false, error: 'Use POST.' });
    if (!env.ATTEMPTS) return reply(500, { ok: false, error: 'The worker is not set up: the ATTEMPTS storage is not connected.' });
    if (!env.PIN && !/^[0-9a-f]{64}$/.test(env.PIN_HASH || '')) return reply(500, { ok: false, error: 'The worker is not set up: no PIN.' });

    let body;
    try { body = await request.json(); } catch { return reply(400, { ok: false, error: 'Send JSON.' }); }

    // PIN check, with a limit on wrong guesses per visitor
    const who = 'wrong:' + (request.headers.get('CF-Connecting-IP') || 'unknown');
    const wrong = Number(await env.ATTEMPTS.get(who)) || 0;
    if (wrong >= MAX_WRONG) return reply(429, { ok: false, error: 'Too many wrong PINs. Try again in an hour.' });
    if (!(await pinMatches(String(body.pin ?? ''), env))) {
      await env.ATTEMPTS.put(who, String(wrong + 1), { expirationTtl: 3600 });
      return reply(403, { ok: false, error: 'Wrong PIN.' });
    }

    const change = makeChange(body);
    if (typeof change === 'string') return reply(400, { ok: false, error: change });

    let doc = await loadDoc(env);
    if (!doc) return reply(502, { ok: false, error: 'The quotes could not be loaded. Try again.' });
    if (change) {
      doc = change(doc);
      await env.ATTEMPTS.put(DOC, JSON.stringify(doc));
    }
    return reply(200, { ok: true, quotes: doc.quotes, markup: doc.markup || null });
  },
};

async function pinMatches(pin, env) {
  if (env.PIN) return same(await sha256(pin), await sha256(String(env.PIN)));
  return same(await sha256(pin), env.PIN_HASH);
}
// Compares two hex strings without stopping at the first difference.
function same(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

// The stored quotes and markup; copied once from the repository's quotes.json if the store is still empty.
async function loadDoc(env) {
  const raw = await env.ATTEMPTS.get(DOC);
  if (raw) return JSON.parse(raw);
  let doc = { quotes: [], markup: null };
  if (env.GITHUB_TOKEN) {
    const r = await fetch('https://api.github.com/repos/' + REPO + '/contents/quotes.json?ref=main', {
      headers: { Accept: 'application/vnd.github+json', Authorization: 'Bearer ' + env.GITHUB_TOKEN, 'User-Agent': 'alu-quotes-worker', 'X-GitHub-Api-Version': '2022-11-28' },
    });
    if (r.ok) {
      const f = await r.json();
      const d = JSON.parse(unb64(f.content));
      doc = { quotes: Array.isArray(d.quotes) ? d.quotes : [], markup: d.markup || null };
    } else if (r.status !== 404) return null;
  }
  await env.ATTEMPTS.put(DOC, JSON.stringify(doc));
  return doc;
}

// Turns a request into a function doc -> doc, null for a plain check, or an error string.
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
    return (d) => ({ ...d, quotes: [...d.quotes, quote].slice(-500) });
  }
  if (body.op === 'delete') {
    const id = text(body.id, 40);
    if (!id) return 'Say which quote to delete.';
    return (d) => ({ ...d, quotes: d.quotes.filter((q) => q.id !== id) });
  }
  if (body.op === 'markup') {
    const m = body.markup || {};
    const markup = { markupPct: num(m.markupPct, 0, 300), markup33: num(m.markup33, 0, 300), markup38: num(m.markup38, 0, 300), learn: m.learn !== false };
    if (markup.markupPct === null || markup.markup33 === null || markup.markup38 === null) return 'Markups must be between 0 and 300.';
    return (d) => ({ ...d, markup });
  }
  return 'Unknown request.';
}

async function sha256(s) {
  const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
function unb64(s) { const bin = atob(String(s).replace(/\s/g, '')); return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0))); }
