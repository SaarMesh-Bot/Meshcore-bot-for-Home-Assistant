/* MeshCore Bot add-on: the dashboard in the bot's language, and the menu per account (see patch_webviewer_users.py).
 * window.WEBUI_ME   {auth, user, role, pages, lang}   from /webui/me.js
 * window.WEBUI_I18N {"English text": "translation", ..., "__patterns": [[regex, replacement], ...]}  from /webui/i18n.js
 * Texts are matched whole (after trimming and collapsing spaces); a trailing ":" or "..." is kept. Text that
 * appears later (lists, tables filled by the page) is translated as it arrives. Only text, never values or code. */
(function () {
  'use strict';
  var ME = window.WEBUI_ME || {};
  var DICT = window.WEBUI_I18N || {};
  var PATTERNS = (DICT.__patterns || []).map(function (p) {
    try { return [new RegExp('^' + p[0] + '$'), p[1]]; } catch (e) { return null; }
  }).filter(Boolean);
  var ON = ME.lang && ME.lang !== 'en' && Object.keys(DICT).length > 1;

  // Dates, times and numbers in the bot's language too ("2 okt. 04:47" instead of "Oct 2 04:47 AM"), on every page:
  // calls without a locale (or with []) get the bot's language; an explicit locale is left alone.
  if (ON) {
    var LOCALE = ME.lang;
    var wrap = function (proto, name) {
      var orig = proto[name];
      if (!orig || orig.__webui) return;
      var f = function (loc, opts) {
        if (loc === undefined || loc === null || (Array.isArray(loc) && !loc.length)) loc = LOCALE;
        return orig.call(this, loc, opts);
      };
      f.__webui = true;
      proto[name] = f;
    };
    ['toLocaleString', 'toLocaleDateString', 'toLocaleTimeString'].forEach(function (n) { wrap(Date.prototype, n); });
    wrap(Number.prototype, 'toLocaleString');
  }
  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, CODE: 1, PRE: 1, NOSCRIPT: 1, CANVAS: 1, SVG: 1 };
  var ATTRS = ['placeholder', 'title', 'aria-label', 'alt', 'data-bs-original-title', 'data-bs-title', 'data-bs-content'];

  function lookup(text) {
    if (!text) return null;
    var key = text.replace(/\s+/g, ' ').trim();
    if (!key || key.length > 3000 || !/[A-Za-z]/.test(key)) return null;
    if (Object.prototype.hasOwnProperty.call(DICT, key) && key !== '__patterns') return DICT[key];
    var m = /^(.*?)(\s*[:：]|\s*\.\.\.|\s*…)$/.exec(key);
    if (m && m[1] && Object.prototype.hasOwnProperty.call(DICT, m[1])) return DICT[m[1]] + m[2];
    return byPattern(key, 0);
  }

  // A pattern keeps what it captured ("last heard (.+) ago"); a captured piece that is itself a known text or pattern
  // ("2 days", "just now") is translated too, one level deep.
  function byPattern(key, depth) {
    for (var i = 0; i < PATTERNS.length; i++) {
      var m = PATTERNS[i][0].exec(key);
      if (!m) continue;
      return PATTERNS[i][1].replace(/\$(\d)/g, function (_, n) {
        var g = m[+n] === undefined ? '' : m[+n];
        if (depth < 1 && /[A-Za-z]/.test(g)) {
          var t = Object.prototype.hasOwnProperty.call(DICT, g) && g !== '__patterns' ? DICT[g] : byPattern(g, depth + 1);
          if (t !== null && t !== undefined) return t;
        }
        return g;
      });
    }
    return null;
  }

  function skipped(el) {
    for (var n = el; n && n.nodeType === 1; n = n.parentNode) {
      if (SKIP[n.nodeName.toUpperCase()] || n.isContentEditable || (n.hasAttribute && n.hasAttribute('data-no-i18n'))) return true;
    }
    return false;
  }

  // per element and attribute: the last value we looked at (ours or the page's) - so a value is translated once
  var DONE = (function () {
    var m = typeof WeakMap === 'function' ? new WeakMap() : null;
    return {
      get: function (el, k) { var o = m && m.get(el); return o ? o[k] : undefined; },
      set: function (el, k, v) { if (!m) return; var o = m.get(el); if (!o) { o = {}; m.set(el, o); } o[k] = v; }
    };
  })();

  function doText(node) {
    var v = node.nodeValue;
    if (!v || !/[A-Za-z]/.test(v) || DONE.get(node, 'text') === v || skipped(node.parentNode)) return;
    var t = lookup(v);
    if (t !== null && t !== v.trim()) {
      var lead = /^\s*/.exec(v)[0], tail = /\s*$/.exec(v)[0];
      node.nodeValue = lead + t + tail;
    }
    DONE.set(node, 'text', node.nodeValue);
  }

  function doEl(el, force) {
    if (!force && skipped(el)) return;
    // Only write a real change, and never translate our own output again: writing an attribute is itself a mutation,
    // so writing the same text back (a translation equal to the original, e.g. "node … · build …") made the observer
    // run forever and froze the page (Bot network, found 2026-10-12).
    for (var i = 0; i < ATTRS.length; i++) {
      var a = el.getAttribute && el.getAttribute(ATTRS[i]);
      if (!a || DONE.get(el, ATTRS[i]) === a) continue;
      var t = lookup(a);
      if (t !== null && t !== a) { el.setAttribute(ATTRS[i], t); DONE.set(el, ATTRS[i], t); }
      else DONE.set(el, ATTRS[i], a);
    }
    if (el.nodeName === 'INPUT' && /^(submit|button)$/i.test(el.type || '') && el.value) {
      var tv = lookup(el.value); if (tv !== null && tv !== el.value) el.value = tv;
    }
  }

  // A chart's canvas (or an svg) has no text to translate, but its aria-label/title is read out: do those.
  function canvasLabel(el) {
    if (/^(CANVAS|SVG)$/i.test(el.nodeName) && !skipped(el.parentNode)) doEl(el, true);
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) { if (skipped(root)) { canvasLabel(root); return; } doEl(root); }
    var w = document.createTreeWalker(root, 5 /* element + text */, null);
    var n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) doText(n); else if (skipped(n)) canvasLabel(n); else doEl(n);
    }
  }

  function translateAll() {
    if (!ON) return;
    var full = lookup(document.title);
    if (full !== null) document.title = full;
    else {
      var m = /^(.*?)(\s+-\s+MeshCore Bot.*)$/.exec(document.title);
      var t = m ? lookup(m[1]) : null;
      if (t !== null) document.title = t + m[2];
    }
    walk(document.body);
    var busy = false;
    new MutationObserver(function (list) {
      if (busy) return;
      busy = true;
      try {
        for (var i = 0; i < list.length; i++) {
          var r = list[i];
          if (r.type === 'characterData') doText(r.target);
          else if (r.type === 'attributes') { if (skipped(r.target)) canvasLabel(r.target); else doEl(r.target); }
          else for (var j = 0; j < r.addedNodes.length; j++) walk(r.addedNodes[j]);
        }
      } finally { busy = false; }
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }

  // ---- texts outside the page: confirm/alert/prompt boxes, and Chart.js (it draws its texts on a canvas)
  function message(text) {
    if (typeof text !== 'string' || !ON) return text;
    var whole = lookup(text);
    if (whole !== null) return whole;
    // paragraphs ("Stop the bot?\n\nThis shuts ...") are translated one by one
    return text.split(/(\n+)/).map(function (part) {
      if (/^\n+$/.test(part)) return part;
      var t = lookup(part);
      if (t !== null) return t;
      var bits = part.split(/(?<=[.?!])\s+/);   // or sentence by sentence
      return bits.map(function (b) { var tb = lookup(b); return tb === null ? b : tb; }).join(' ');
    }).join('');
  }
  if (ON) {
    ['confirm', 'alert', 'prompt'].forEach(function (name) {
      var orig = window[name];
      if (typeof orig !== 'function') return;
      window[name] = function (text) {
        var args = Array.prototype.slice.call(arguments);
        args[0] = message(text);
        return orig.apply(window, args);
      };
    });
  }

  var chartPlugin = {
    id: 'webuiI18n',
    beforeUpdate: function (chart) {
      var tr = function (v) { if (typeof v !== 'string') return v; var t = lookup(v); return t === null ? v : t; };
      try {
        var data = chart.config && chart.config.data;
        if (data) {
          (data.datasets || []).forEach(function (ds) { if (ds && typeof ds.label === 'string') ds.label = tr(ds.label); });
          if (Array.isArray(data.labels)) data.labels = data.labels.map(tr);
        }
        var o = chart.config && chart.config.options;
        if (o && o.scales) Object.keys(o.scales).forEach(function (k) {
          var t = o.scales[k] && o.scales[k].title;
          if (t && typeof t.text === 'string') t.text = tr(t.text);
        });
        if (o && o.plugins && o.plugins.title && typeof o.plugins.title.text === 'string') o.plugins.title.text = tr(o.plugins.title.text);
      } catch (e) { /* never break a chart over a translation */ }
    }
  };
  function hookChart(C) {
    try { if (C && C.register && !C.__webui) { C.register(chartPlugin); C.__webui = true; } } catch (e) { /* older Chart.js */ }
    return C;
  }
  if (ON) {
    if (window.Chart) hookChart(window.Chart);
    else {
      var held;
      try {
        Object.defineProperty(window, 'Chart', {
          configurable: true,
          get: function () { return held; },
          set: function (v) { held = hookChart(v); }
        });
      } catch (e) { /* fall back to the check below */ }
    }
    document.addEventListener('DOMContentLoaded', function () { if (window.Chart) hookChart(window.Chart); });
  }

  // ---- menu per account
  function prefix() {
    var s = document.querySelector('script[data-prefix]');
    return s ? (s.getAttribute('data-prefix') || '') : '';
  }
  function pathOf(a) {
    try {
      var p = new URL(a.getAttribute('href'), location.href).pathname, pre = prefix();
      if (pre && p.indexOf(pre) === 0) p = p.slice(pre.length) || '/';
      return p;
    } catch (e) { return null; }
  }
  function menu() {
    var nav = document.querySelector('.navbar-nav');
    if (!nav) return;
    if (ME.role === 'viewer') {
      var allowed = ME.pages || [];
      nav.querySelectorAll('a.nav-link, a.dropdown-item').forEach(function (a) {
        if (a.classList.contains('dropdown-toggle')) return;
        var p = pathOf(a);
        if (p && allowed.indexOf(p) === -1) {
          var li = a.closest('li'); (li || a).style.display = 'none';
        }
      });
      nav.querySelectorAll('.dropdown').forEach(function (d) {
        var visible = Array.prototype.some.call(d.querySelectorAll('a.dropdown-item'), function (a) {
          var li = a.closest('li'); return (li || a).style.display !== 'none';
        });
        if (!visible) d.style.display = 'none';
      });
      var brand = document.querySelector('a.navbar-brand');
      if (brand && allowed.indexOf('/') === -1 && allowed.length) brand.setAttribute('href', prefix() + allowed[0]);
    }
    if (ME.auth && ME.user) {
      var li = document.createElement('li');
      li.className = 'nav-item';
      var a = document.createElement('a');
      a.className = 'nav-link';
      a.href = prefix() + '/logout';
      var icon = document.createElement('i');
      icon.className = 'fas fa-right-from-bracket me-1';
      a.appendChild(icon);
      a.appendChild(document.createTextNode('Log out'));
      var who = document.createElement('span');
      who.className = 'ms-1 small opacity-75';
      who.setAttribute('data-no-i18n', '');
      who.textContent = '(' + ME.user + ')';
      a.appendChild(who);
      li.appendChild(a);
      nav.appendChild(li);
    }
  }

  function start() {
    if (ME.lang) document.documentElement.setAttribute('lang', ME.lang);
    try { menu(); } catch (e) { /* the menu is only a convenience; the server decides */ }
    try { translateAll(); } catch (e) { /* never break a page over a translation */ }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
