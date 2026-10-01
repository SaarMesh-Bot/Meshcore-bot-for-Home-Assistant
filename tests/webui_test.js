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
  const navText = Array.from(d.querySelectorAll('.navbar-nav a')).map(a => a.textContent.trim());
  check(navText.includes('Contacten') && navText.includes('Instellingen'), 'menu vertaald: ' + navText.slice(0, 8).join(' | '));
  check(d.body.textContent.includes('Commando\'s zonder antwoord'), 'kaartkop vertaald (Commands without an answer)');
  check(d.title.startsWith('Problemen'), 'paginatitel vertaald: ' + d.title);
  const p = d.createElement('p'); p.textContent = 'No warnings or errors in this period.'; d.body.appendChild(p);
  const s = d.createElement('span'); s.textContent = '5 min ago'; d.body.appendChild(s);
  const inp = d.createElement('input'); inp.setAttribute('placeholder', 'Search contacts...'); d.body.appendChild(inp);
  const name = d.createElement('td'); name.textContent = 'Bot'; name.setAttribute('data-no-i18n', ''); d.body.appendChild(name);
  const code = d.createElement('code'); code.textContent = 'Settings'; d.body.appendChild(code);
  await flush(w);
  check(p.textContent === 'Geen waarschuwingen of fouten in deze periode.', 'later toegevoegde tekst vertaald');
  check(s.textContent === '5 min geleden', 'patroon (5 min ago): ' + s.textContent);
  check(inp.getAttribute('placeholder') === 'Contacten zoeken...', 'placeholder vertaald');
  check(name.textContent === 'Bot' && code.textContent === 'Settings', 'data-no-i18n en <code> blijven ongemoeid');
  p.textContent = 'Saved.'; await flush(w);
  check(p.textContent === 'Opgeslagen.' || p.textContent === 'Saved.', 'gewijzigde tekst opnieuw bekeken (geen lus)');

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
