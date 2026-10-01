"""Dashboard users: an admin (the add-on's web viewer password, as before) plus named accounts made on the Users page.

A named account is an admin (everything, like the password) or a viewer: read-only, only the pages ticked for it, and on
the Repeater page only the repeaters (or repeater groups) chosen for it. The web viewer enforces it on the server (see
patch_webviewer_users.py); hiding menu items in the browser is only a convenience.

Kept in the bot's database:

    web_users    name (case-insensitive), password hash, role, pages, repeaters, groups (JSON lists), created/last login
    web_groups   name, repeaters (JSON list of repeater keys)

Passwords are stored as PBKDF2-SHA256 with a random salt (never the password itself). Failed logins are limited per
address (LOGIN_MAX_FAILS within LOGIN_WINDOW_S), because the port may be reachable from the internet.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from typing import Any, Optional

ITERATIONS = 240_000
MIN_PASSWORD = 8
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,31}$")
ROLES = ("admin", "viewer")
LOGIN_MAX_FAILS = 8
LOGIN_WINDOW_S = 900

# Pages a viewer can be given, with the read-only API paths each page needs (exact paths, GET only). Not /api/channels
# (it holds the channel keys): a viewer's Radar page just does not mark which channels are on the radio.
PAGES: dict = {
    "dashboard": {"path": "/", "label": "Dashboard",
                  "api": ["/api/dashboard/summary", "/api/dashboard/series", "/api/dashboard/top", "/api/dashboard/windows",
                          "/api/health"]},
    "repeater": {"path": "/repeater", "label": "Repeater", "api": ["/api/repeater"]},
    "radar": {"path": "/radar", "label": "Radar", "api": ["/api/radar", "/api/radar/repeaters", "/api/radar/observers"]},
    "games": {"path": "/games", "label": "Games", "api": ["/api/games", "/api/games/farm"]},
    "mesh": {"path": "/mesh", "label": "Mesh", "api": ["/api/mesh/nodes", "/api/mesh/edges", "/api/mesh/stats"]},
    "bots": {"path": "/bots", "label": "Bots", "api": ["/api/bots"]},
    "botnet": {"path": "/botnet", "label": "Bot network", "api": ["/api/botnet", "/api/botnet/history"]},
}
# Always allowed for any logged-in user (the banner, the user's own info, the page scripts, logging out).
ALWAYS = ("/logout", "/api/banner-status", "/webui/", "/static/", "/_ingress/", "/favicon", "/apple-touch-icon",
          "/site.webmanifest")

_lock = threading.Lock()
_fails: dict = {}          # address -> [timestamps of failed logins]
_cache: dict = {"at": 0.0, "any": None}


# ---------------------------------------------------------------- passwords
def hash_password(password: str, salt: Optional[bytes] = None, iterations: int = ITERATIONS) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        test = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(test.hex(), digest)
    except (ValueError, TypeError):
        return False


def same_secret(a: str, b: str) -> bool:
    """Constant-time compare for the add-on's own admin password."""
    return bool(a) and bool(b) and hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------------------------------------------------------------- login rate limit
def login_blocked(address: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    with _lock:
        recent = [t for t in _fails.get(address, []) if now - t < LOGIN_WINDOW_S]
        _fails[address] = recent
        return len(recent) >= LOGIN_MAX_FAILS


def login_failed(address: str, now: Optional[float] = None) -> None:
    with _lock:
        _fails.setdefault(address, []).append(time.time() if now is None else now)


def login_ok(address: str) -> None:
    with _lock:
        _fails.pop(address, None)


# ---------------------------------------------------------------- storage
def ensure_tables(conn: Any) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS web_users (
        name TEXT PRIMARY KEY COLLATE NOCASE, pw_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'viewer',
        pages TEXT NOT NULL DEFAULT '[]', repeaters TEXT NOT NULL DEFAULT '[]', groups TEXT NOT NULL DEFAULT '[]',
        created_at INTEGER, last_login INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS web_groups (
        name TEXT PRIMARY KEY COLLATE NOCASE, repeaters TEXT NOT NULL DEFAULT '[]')""")


def _list(value: Any) -> list:
    try:
        out = json.loads(value) if isinstance(value, str) else value
        return [str(x) for x in out] if isinstance(out, list) else []
    except ValueError:
        return []


def _row_to_user(row: Any) -> dict:
    name, role, pages, repeaters, groups, created, last = row
    return {"name": name, "role": role, "pages": _list(pages), "repeaters": _list(repeaters), "groups": _list(groups),
            "created_at": created, "last_login": last}


def any_users(conn_factory: Any, max_age: float = 10.0) -> bool:
    """Whether at least one named account exists (cached briefly; it decides whether the dashboard needs a login)."""
    now = time.time()
    if _cache["any"] is not None and now - _cache["at"] < max_age:
        return _cache["any"]
    try:
        with conn_factory() as conn:
            ensure_tables(conn)
            found = conn.execute("SELECT 1 FROM web_users LIMIT 1").fetchone() is not None
    except Exception:
        found = False
    _cache.update(at=now, any=found)
    return found


def forget_cache() -> None:
    _cache.update(at=0.0, any=None)


def list_users(conn: Any) -> list:
    ensure_tables(conn)
    rows = conn.execute("SELECT name, role, pages, repeaters, groups, created_at, last_login FROM web_users "
                        "ORDER BY name COLLATE NOCASE").fetchall()
    return [_row_to_user(r) for r in rows]


def get_user(conn: Any, name: str) -> Optional[dict]:
    ensure_tables(conn)
    row = conn.execute("SELECT name, role, pages, repeaters, groups, created_at, last_login FROM web_users WHERE name = ?",
                       ((name or "").strip(),)).fetchone()
    return _row_to_user(row) if row else None


def authenticate(conn: Any, name: str, password: str, now: Optional[float] = None) -> Optional[dict]:
    ensure_tables(conn)
    row = conn.execute("SELECT pw_hash FROM web_users WHERE name = ?", ((name or "").strip(),)).fetchone()
    if not row:
        hash_password(password or "x", b"0" * 16)   # same work for an unknown name: no timing hint
        return None
    if not check_password(password or "", row[0]):
        return None
    conn.execute("UPDATE web_users SET last_login = ? WHERE name = ?", (int(now or time.time()), name.strip()))
    conn.commit()
    return get_user(conn, name)


def save_user(conn: Any, data: dict, now: Optional[float] = None) -> dict:
    """Create or change an account. A new account needs a password; an existing one keeps its password when the
    field is empty. Returns the stored user, or raises ValueError with a short reason."""
    ensure_tables(conn)
    name = " ".join(str(data.get("name") or "").split())
    if not NAME_RE.match(name):
        raise ValueError("name: 1-32 letters, digits, space, . _ -")
    if name.lower() == "admin":
        raise ValueError("'admin' is the add-on password; pick another name")
    role = str(data.get("role") or "viewer")
    if role not in ROLES:
        raise ValueError("role must be admin or viewer")
    pages = [p for p in _list(data.get("pages")) if p in PAGES]
    repeaters = sorted({r.strip().lower() for r in _list(data.get("repeaters")) if re.fullmatch(r"[0-9a-fA-F]{2,64}", r.strip())})
    groups = sorted({g.strip() for g in _list(data.get("groups")) if g.strip()})
    password = str(data.get("password") or "")
    existing = get_user(conn, name)
    if password and len(password) < MIN_PASSWORD:
        raise ValueError(f"password: at least {MIN_PASSWORD} characters")
    if not existing and not password:
        raise ValueError("a new user needs a password")
    if existing:
        conn.execute("UPDATE web_users SET role = ?, pages = ?, repeaters = ?, groups = ? WHERE name = ?",
                     (role, json.dumps(pages), json.dumps(repeaters), json.dumps(groups), name))
        if password:
            conn.execute("UPDATE web_users SET pw_hash = ? WHERE name = ?", (hash_password(password), name))
    else:
        conn.execute("INSERT INTO web_users (name, pw_hash, role, pages, repeaters, groups, created_at) VALUES (?,?,?,?,?,?,?)",
                     (name, hash_password(password), role, json.dumps(pages), json.dumps(repeaters), json.dumps(groups),
                      int(now or time.time())))
    conn.commit()
    forget_cache()
    return get_user(conn, name)


def delete_user(conn: Any, name: str) -> bool:
    ensure_tables(conn)
    n = conn.execute("DELETE FROM web_users WHERE name = ?", ((name or "").strip(),)).rowcount
    conn.commit()
    forget_cache()
    return bool(n)


def list_groups(conn: Any) -> list:
    ensure_tables(conn)
    return [{"name": n, "repeaters": _list(r)} for n, r in
            conn.execute("SELECT name, repeaters FROM web_groups ORDER BY name COLLATE NOCASE").fetchall()]


def save_group(conn: Any, name: str, repeaters: Any) -> dict:
    ensure_tables(conn)
    name = " ".join(str(name or "").split())
    if not NAME_RE.match(name):
        raise ValueError("group name: 1-32 letters, digits, space, . _ -")
    keys = sorted({r.strip().lower() for r in _list(repeaters) if re.fullmatch(r"[0-9a-fA-F]{2,64}", r.strip())})
    conn.execute("INSERT INTO web_groups (name, repeaters) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET repeaters = excluded.repeaters",
                 (name, json.dumps(keys)))
    conn.commit()
    return {"name": name, "repeaters": keys}


def delete_group(conn: Any, name: str) -> bool:
    ensure_tables(conn)
    n = conn.execute("DELETE FROM web_groups WHERE name = ?", ((name or "").strip(),)).rowcount
    conn.commit()
    return bool(n)


# ---------------------------------------------------------------- what a user may see
def allowed_repeaters(conn: Any, user: dict) -> Optional[set]:
    """Repeater keys a viewer may see (its own list plus its groups); None = all (admins, or nothing chosen)."""
    if not user or user.get("role") == "admin":
        return None
    keys = {k.lower() for k in user.get("repeaters") or []}
    wanted = {g.lower() for g in user.get("groups") or []}
    if wanted:
        for g in list_groups(conn):
            if g["name"].lower() in wanted:
                keys.update(k.lower() for k in g["repeaters"])
    if not keys and not wanted:
        return None
    return keys


def may_request(user: Optional[dict], method: str, path: str) -> bool:
    """Server-side check for one request. user None or role admin = everything."""
    if not user or user.get("role") == "admin":
        return True
    if path.startswith(ALWAYS) or path == "/login":
        return True
    if method not in ("GET", "HEAD"):
        return False
    pages = [PAGES[p] for p in user.get("pages") or [] if p in PAGES]
    for page in pages:
        if path == page["path"]:
            return True
        if path in page["api"]:
            return True
    return False


def first_page(user: dict) -> Optional[str]:
    for p in user.get("pages") or []:
        if p in PAGES:
            return PAGES[p]["path"]
    return None
