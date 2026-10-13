// The dashboard in the bot's language, in a browser-like DOM: static text, text that appears later, attributes,
// patterns, names left alone, and the menu for a read-only viewer.
const { JSDOM } = require('jsdom');
const fs = require('fs');
const page = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let fails = 0;
const check = (c, m) => { console.log((c ? 'OK   ' : 'FAIL ') + m); if (!c) fails++; };

function load(meOverride) {
  const html = page.html.replace(/<script src="\/webui\/[^"]*"><\/script>/g, '');
  const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'http://localhost/problems' });
  const w = dom.window;
  w.fetch = () => new Promise(() => {});           // the page's own loading never finishes: only our texts matter
  w.eval(meOverride || page.me); w.eval(page.i18n); w.eval(page.webui);
  return w;
}
const flush = (w) => new Promise(r => w.setTimeout(r, 0));

(async () => {
  const w = load();
  await flush(w);
  const d = w.document;
  check(d.documentElement.getAttribute('lang') === 'nl', 'html lang = bottaal');
  const dt = new w.Date(Date.UTC(2026, 9, 2, 12, 0)).toLocaleDateString([], { day: 'numeric', month: 'short' });
  if (Intl.DateTimeFormat.supportedLocalesOf(['nl']).length) {
    check(/okt/.test(dt), 'datums in de bottaal: ' + dt);
  } else {   // this Node has no locale data (small ICU): check that the wrapper is in place instead
    check(w.Date.prototype.toLocaleDateString.__webui === true && w.Number.prototype.toLocaleString.__webui === true,
          'datums en getallen gaan via de bottaal (Node zonder taaldata)');
  }
  const navText = Array.from(d.querySelectorAll('.navbar-nav a')).map(a => a.textContent.trim());
  check(navText.includes('Contacten') && navText.includes('Instellingen'), 'menu vertaald: ' + navText.slice(0, 8).join(' | '));
  check(d.body.textContent.includes('Commando\'s zonder antwoord'), 'kaartkop vertaald (Commands without an answer)');
  check(d.title.startsWith('Problemen'), 'paginatitel vertaald: ' + d.title);
  const p = d.createElement('p'); p.textContent = 'No warnings or errors in this period.'; d.body.appendChild(p);
  const s = d.createElement('span'); s.textContent = '5 min ago'; d.body.appendChild(s);
  const inp = d.createElement('input'); inp.setAttribute('placeholder', 'Search contacts...'); d.body.appendChild(inp);
  const name = d.createElement('td'); name.textContent = 'Bot'; name.setAttribute('data-no-i18n', ''); d.body.appendChild(name);
  const code = d.createElement('code'); code.textContent = 'Settings'; d.body.appendChild(code);
  const r1 = d.createElement('span'); r1.textContent = ' · 1 readings in this period'; d.body.appendChild(r1);
  const r2 = d.createElement('div'); r2.textContent = 'last reply 30 h ago'; d.body.appendChild(r2);
  await flush(w);
  check(r1.textContent === ' · 1 metingen in deze periode' && r2.textContent === 'laatste antwoord 30 u geleden', 'getallen in zinnen: ' + r1.textContent + ' | ' + r2.textContent);
  check(p.textContent === 'Geen waarschuwingen of fouten in deze periode.', 'later toegevoegde tekst vertaald');
  check(s.textContent === '5 min geleden', 'patroon (5 min ago): ' + s.textContent);
  check(inp.getAttribute('placeholder') === 'Contacten zoeken...', 'placeholder vertaald');
  check(name.textContent === 'Bot' && code.textContent === 'Settings', 'data-no-i18n en <code> blijven ongemoeid');
  p.textContent = 'Saved.'; await flush(w);
  check(p.textContent === 'Opgeslagen.' || p.textContent === 'Saved.', 'gewijzigde tekst opnieuw bekeken (geen lus)');

  // confirm boxes and Chart.js texts
  let shown = null;
  const w2 = (function () {
    const html = page.html.replace(/<script src="\/webui\/[^"]*"><\/script>/g, '');
    const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'http://localhost/problems' });
    const x = dom.window;
    x.fetch = () => new Promise(() => {});
    x.confirm = function (t) { shown = t; return true; };
    x.eval(page.me); x.eval(page.i18n); x.eval(page.webui);
    return x;
  })();
  await flush(w2);
  w2.confirm('Stop the bot?\n\nThis shuts the bot down completely, not just the radio link. It will stop responding on the mesh and this web viewer will become unavailable.\n\nIt comes back only if something restarts it (systemd, Docker). If you started it by hand, you will need to start it again the same way.');
  check(shown && shown.startsWith('De bot stoppen?') && shown.includes('Dit sluit de bot helemaal af'), 'bevestigingsvenster vertaald: ' + shown);
  // a Chart.js that arrives after webui.js: the plugin is registered and translates labels and axis titles
  let plugin = null;
  w2.Chart = { register: function (p) { plugin = p; } };
  const cfg = { data: { labels: ['REQ', 'Other'], datasets: [{ label: 'Flood packets (last 3d)' }] },
                options: { scales: { x: { title: { text: 'Hops away' } }, y: { title: { text: '% of series' } } } } };
  plugin && plugin.beforeUpdate({ config: cfg });
  check(plugin && cfg.data.datasets[0].label === 'Flood-pakketten (laatste 3d)' && cfg.options.scales.x.title.text === 'Hops ver'
        && cfg.options.scales.y.title.text === '% van de reeks' && cfg.data.labels[1] === 'Overig' && cfg.data.labels[0] === 'REQ',
        'grafiekteksten vertaald: ' + JSON.stringify(cfg.data) + ' ' + JSON.stringify(cfg.options));
  const tip = d.createElement('div'); tip.setAttribute('data-bs-original-title', 'Hops away'); d.body.appendChild(tip);
  await flush(w);
  check(tip.getAttribute('data-bs-original-title') === 'Hops ver', 'tooltip-tekst (data-bs) vertaald');
  // Bot network froze (2026-10-12): a title whose translation equals the text was written back for ever
  const same = d.createElement('span');
  let writes = 0;
  const realSet = same.setAttribute.bind(same);
  same.setAttribute = (k, v) => { if (++writes > 200) throw new Error('loop'); realSet(k, v); };
  realSet('title', 'node a1b2c3 · build 07-Jun-2026');
  d.body.appendChild(same);
  await flush(w); await flush(w);
  check(writes === 0, 'gelijke vertaling wordt niet teruggeschreven (geen eindeloze lus): ' + writes + ' keer');
  const heard = d.createElement('span'); heard.setAttribute('title', 'last heard 2 days ago'); d.body.appendChild(heard);
  await flush(w);
  check(heard.getAttribute('title') === 'laatst gehoord 2 dagen geleden', 'stuk binnen een patroon ook vertaald: ' + heard.getAttribute('title'));
  const long = Object.keys(JSON.parse(page.i18n.replace(/^window\.WEBUI_I18N = /, '').replace(/;\s*$/, ''))).find(k => k.length > 400);
  const lt = d.createElement('div'); lt.textContent = long; d.body.appendChild(lt);
  await flush(w);
  check(long && lt.textContent !== long, 'lange tooltip (>400 tekens) vertaald');

  // English bot: nothing changes
  const en = load(page.me.replace('"lang": "nl"', '"lang": "en"'));
  await flush(en);
  check(Array.from(en.document.querySelectorAll('.navbar-nav a')).some(a => a.textContent.trim() === 'Contacts'), 'bottaal en: geen vertaling');

  // viewer: only its pages in the menu, plus Log out
  const v = load('window.WEBUI_ME = {"auth": true, "user": "Kijker", "role": "viewer", "pages": ["/repeater"], "lang": "nl"};');
  await flush(v);
  const links = Array.from(v.document.querySelectorAll('.navbar-nav a')).filter(a => {
    for (let n = a; n; n = n.parentElement) if (n.style && n.style.display === 'none') return false; return true; });
  const visible = links.map(a => a.getAttribute('href'));
  check(visible.includes('/repeater') && !visible.includes('/contacts') && !visible.includes('/config'), 'kijker ziet alleen zijn pagina\'s: ' + visible.join(' '));
  check(visible.includes('/logout') && v.document.body.textContent.includes('Uitloggen'), 'Uitloggen (Kijker) in het menu');
  console.log(`\n${fails} fouten`);
  process.exit(fails ? 1 : 0);
})();
