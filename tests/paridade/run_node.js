// Executa o jsCode de um nó da v28 com entradas simuladas (para comparar com o Python).
// Uso: node run_node.js  < {"wf": caminho, "no": nome, "input": [...], "nodes": {nome: [...]}, "now": ISO}
const fs = require('fs');
const req = JSON.parse(fs.readFileSync(0, 'utf8'));
const wf = JSON.parse(fs.readFileSync(req.wf, 'utf8'));
const n = wf.nodes.find(x => x.name === req.no);
if (!n) { console.log(JSON.stringify({ erro: 'nó não existe: ' + req.no })); process.exit(0); }
const base = req.now ? new Date(req.now) : new Date();
const RealDate = Date;
// congela o relógio
class FakeDate extends RealDate { constructor(...a) { if (a.length === 0) super(base.getTime()); else super(...a); } static now() { return base.getTime(); } }
global.Date = FakeDate;
function mkNow(d) {
  const o = {
    _d: d,
    setZone() { return o; }, setLocale() { return o; },
    toISO() { const sp = new RealDate(d.getTime() - 3 * 3600e3); return sp.toISOString().replace('Z', '-03:00'); },
    toFormat(f) {
      const sp = new RealDate(d.getTime() - 3 * 3600e3); const p = x => String(x).padStart(2, '0');
      return f.replace('yyyy', sp.getUTCFullYear()).replace('LL', p(sp.getUTCMonth() + 1)).replace('MM', p(sp.getUTCMonth() + 1))
        .replace('dd', p(sp.getUTCDate())).replace('HH', p(sp.getUTCHours())).replace('mm', p(sp.getUTCMinutes())).replace('ss', p(sp.getUTCSeconds()));
    },
    plus({ hours = 0, days = 0, minutes = 0 } = {}) { return mkNow(new RealDate(d.getTime() + hours * 3600e3 + days * 86400e3 + minutes * 60e3)); },
    toMillis() { return d.getTime(); },
    get weekday() { const sp = new RealDate(d.getTime() - 3 * 3600e3); return sp.getUTCDay() || 7; },
    get hour() { return new RealDate(d.getTime() - 3 * 3600e3).getUTCHours(); },
  };
  return o;
}
const DateTime = { fromJSDate: d => mkNow(d), now: () => mkNow(base) };
const wrap = a => (a || []).map(j => (j && j.json ? j : { json: j }));
const inp = wrap(req.input);
const nodes = Object.fromEntries(Object.entries(req.nodes || {}).map(([k, v]) => [k, wrap(v)]));
const mk$ = idx => name => {
  if (!(name in nodes)) {
    const err = () => { throw new Error('Referência a nó não executado: ' + name); };
    return { first: err, all: err, get item() { return err(); }, itemMatching: err, isExecuted: false };
  }
  const arr = nodes[name];
  return { first: () => arr[0], all: (o) => arr, get item() { return arr[idx] ?? arr[0]; }, itemMatching: i => arr[i], isExecuted: true };
};
const code = n.parameters.jsCode;
const each = n.parameters.mode === 'runOnceForEachItem';
const declara = v => new RegExp('\\b(const|let|var)\\s+' + v.replace('$', '\\$') + '\\b').test(code);
const exec = (idx, $json) => {
  const $input = { all: () => inp, first: () => inp[0], item: inp[idx] };
  const nomes = ['$input', '$', '$json', '$now', '$today', 'DateTime', '$itemIndex', 'items', '$prevNode'];
  const vals = [$input, mk$(idx), $json, mkNow(base), mkNow(base), DateTime, idx, inp, { name: req.prevNode || '' }];
  const usar = nomes.map((n, i) => [n, vals[i]]).filter(([n]) => !declara(n));
  const f = new Function(...usar.map(x => x[0]), code);
  return f(...usar.map(x => x[1]));
};
try {
  let out;
  if (each) out = inp.map((it, i) => { const r = exec(i, it.json); return r && r.json ? r : { json: r }; });
  else { out = exec(0, inp[0] && inp[0].json); if (!Array.isArray(out)) out = [out]; out = out.map(x => (x && x.json ? x : { json: x })); }
  console.log(JSON.stringify({ ok: out.map(x => x.json) }));
} catch (e) { console.log(JSON.stringify({ erro: String(e && e.message || e) })); }
