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
  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, CODE: 1, PRE: 1, NOSCRIPT: 1, CANVAS: 1, SVG: 1 };
  var ATTRS = ['placeholder', 'title', 'aria-label', 'alt', 'data-bs-original-title'];

  function lookup(text) {
    if (!text) return null;
    var key = text.replace(/\s+/g, ' ').trim();
    if (!key || key.length > 400 || !/[A-Za-z]/.test(key)) return null;
    if (Object.prototype.hasOwnProperty.call(DICT, key) && key !== '__patterns') return DICT[key];
    var m = /^(.*?)(\s*[:：]|\s*\.\.\.|\s*…)$/.exec(key);
    if (m && m[1] && Object.prototype.hasOwnProperty.call(DICT, m[1])) return DICT[m[1]] + m[2];
    for (var i = 0; i < PATTERNS.length; i++) {
      if (PATTERNS[i][0].test(key)) return key.replace(PATTERNS[i][0], PATTERNS[i][1]);
    }
    return null;
  }

  function skipped(el) {
    for (var n = el; n && n.nodeType === 1; n = n.parentNode) {
      if (SKIP[n.nodeName.toUpperCase()] || n.isContentEditable || (n.hasAttribute && n.hasAttribute('data-no-i18n'))) return true;
    }
    return false;
  }

  function doText(node) {
    var v = node.nodeValue;
    if (!v || !/[A-Za-z]/.test(v) || skipped(node.parentNode)) return;
    var t = lookup(v);
    if (t !== null && t !== v.trim()) {
      var lead = /^\s*/.exec(v)[0], tail = /\s*$/.exec(v)[0];
      node.nodeValue = lead + t + tail;
    }
  }

  function doEl(el) {
    if (skipped(el)) return;
    for (var i = 0; i < ATTRS.length; i++) {
      var a = el.getAttribute && el.getAttribute(ATTRS[i]);
      if (a) { var t = lookup(a); if (t !== null) el.setAttribute(ATTRS[i], t); }
    }
    if (el.nodeName === 'INPUT' && /^(submit|button)$/i.test(el.type || '') && el.value) {
      var tv = lookup(el.value); if (tv !== null) el.value = tv;
    }
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) { if (skipped(root)) return; doEl(root); }
    var w = document.createTreeWalker(root, 5 /* element + text */, null);
    var n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) doText(n); else doEl(n);
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
          else if (r.type === 'attributes') doEl(r.target);
          else for (var j = 0; j < r.addedNodes.length; j++) walk(r.addedNodes[j]);
        }
      } finally { busy = false; }
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
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
