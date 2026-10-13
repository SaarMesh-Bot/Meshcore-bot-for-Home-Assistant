#!/usr/bin/env python3
"""Kanaalradar: which hashtag channels are in use around the bot (service: local_service_plugins/channel_radar_service.py,
dashboard: the Channel radar page).

A group message (GRP_TXT) starts with one byte that identifies its channel - the first byte of SHA256(channel key) - and
a 2-byte MAC (HMAC-SHA256 over the encrypted text, key = channel key + 16 zero bytes). The key of a hashtag channel is
the first 16 bytes of SHA256("#name"). So for a list of candidate names the radar can say for certain which channel a
message belongs to (hash and MAC both match; a wrong name passes the MAC only once in 65 536) - without decrypting it.
Messages on channels whose name is not in the list (private channels, names nobody thought of) are counted per channel
byte as "unknown". Nothing is ever sent, and message texts are never read.

Tables (the bot's own database):
  channel_radar        (day, label, messages, last_ts)    per recognised channel per local day
  channel_radar_other  (day, hash, messages, last_ts)     per unknown channel byte per local day
"""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import timedelta
from typing import Any, Iterable, Optional

from .mesh_community import day_start_ts, local_day

PUBLIC_LABEL = "Publiek (kanaal 0)"
PUBLIC_KEY = bytes.fromhex("8b3387e9c5cdea6ac9e5edbaa115cd72")   # MeshCore's well-known public channel

# Names people use or might use in the Netherlands, Belgium and Germany. Anyone can add more on the card.
DEFAULT_NAMES = """
test bot f1 p2000 p2000-nl p2000-zl p2000-li p2000-limburg
ardf vpk nl-noord hunebedronde testnoord afrithonbot
nl be de nederland belgie belgië deutschland europe eu euregio emr benelux
limburg zuid-limburg zuidlimburg zl nl-zuid nl-li nl-lim nl-limburg li lim nl-oost nl-west nl-midden nl-zh nl-nh nl-gld nl-nb
nl-ov nl-ut nl-fl nl-ze nl-gr nl-fr nl-dr brabant noord-brabant gelderland utrecht zeeland friesland drenthe groningen overijssel
parkstad maastricht heerlen sittard geleen roermond venlo weert kerkrade landgraaf eindhoven nijmegen amsterdam rotterdam
denhaag den-haag be-li be-lim limburg-be vlaanderen wallonie antwerpen genk hasselt brussel gent leuven luik liege tongeren
nrw de-nw d-nrw aachen koeln köln eifel heinsberg dusseldorf düsseldorf rheinland
mesh meshcore meshnl mesh-nl meshbe mesh-be meshde nlmesh general algemeen chat praat kletsen gezellig lobby cafe koffie
help hulp vragen support beginners welkom welcome testing testen bots testbot
weer weather wx meteo weerstation storm onweer knmi nieuws news emergency noodgeval nood 112 alarm rampen nlalert sos
ham hamradio radio amateur pa on dl sota pota aprs dx cb 27mc pmr lora lorawan meshtastic ttn
repeater repeaters sysop admin beheer netwerk network tech techniek dev firmware hardware esp32 heltec rak tbeam homeassistant ha
diy events meetup markt tekoop te-koop sport voetbal formule1 racing games spel quiz fun verkeer file ov trein space iss astro
""".split()


# Generated names: every base word with common prefixes and suffixes (mesh-zl, nl-limburg, maastricht-chat, ...).
# Tens of thousands of names, but a message is only checked against the few that share its channel byte. A generated
# name is only shown after 2 messages, so a chance match (1 in 65 536 per name) never makes the list on its own.
GEN_WORDS = """
limburg zuid-limburg zuidlimburg noord-limburg midden-limburg zl li lim maasland parkstad westelijke-mijnstreek mijnstreek heuvelland
maastricht heerlen sittard geleen roermond venlo weert kerkrade brunssum landgraaf valkenburg meerssen stein beek echt susteren gulpen
vaals simpelveld voerendaal nuth schinveld onderbanken hoensbroek born elsloo eijsden margraten venray horst panningen tegelen
aachen aken heinsberg geilenkirchen eschweiler stolberg herzogenrath alsdorf wurselen duren düren koln köln cologne bonn eifel
nrw rheinland euregio emr dreiländereck drielandenpunt genk hasselt tongeren maaseik lanaken maasmechelen bree lommel sint-truiden
luik liege leuven brussel antwerpen gent brugge vlaanderen wallonie limburg-be eindhoven helmond tilburg breda den-bosch nijmegen
arnhem utrecht amsterdam rotterdam denhaag den-haag haarlem leiden zwolle enschede groningen leeuwarden assen almere apeldoorn
nederland holland belgie belgië deutschland nl be de lu eu benelux europe
mesh meshcore meshtastic lora chat general algemeen praat kletsen cafe lobby welkom help hulp vragen info test testen bot bots
weer weather wx meteo nieuws news p2000 112 alarm nood noodgeval emergency rampen sos
ham hamradio radio amateur pa on dl sota pota aprs cb pmr dx contest
repeater repeaters sysop admin beheer netwerk tech dev firmware hardware diy maker homeassistant
events meetup markt sport voetbal f1 formule1 games quiz fun muziek music food eten fietsen motor auto
""".split()
GEN_PREFIXES = ["", "nl-", "be-", "de-", "mesh-", "meshcore-", "nl", "be", "de", "mesh"]
GEN_SUFFIXES = ["", "-nl", "-be", "-de", "nl", "be", "de", "-mesh", "mesh", "-chat", "chat", "-li", "-zl", "-lim",
                "-test", "test", "-bot", "bot", "1", "2", "-1", "-2", "-mc", "mc", "-meshcore", "-lora", "-radio", "-weer", "-info"]


def generated_names() -> list:
    out = []
    for word in GEN_WORDS:
        for pre in GEN_PREFIXES:
            for suf in GEN_SUFFIXES:
                out.append(pre + word + suf)
    return out


def key_for_name(name: str) -> bytes:
    """Key of a hashtag channel: the first 16 bytes of SHA256 of its lowercase name with '#'."""
    name = name.strip().lower()
    if not name.startswith("#"):
        name = "#" + name
    return hashlib.sha256(name.encode("utf-8")).digest()[:16]


def channel_byte(key16: bytes) -> int:
    return hashlib.sha256(key16).digest()[0]


def radio_channels(db: Any) -> list:
    """[(label, key16)] for every channel on the bot's own radio (upstream's `channels` table, filled from the radio):
    hashtag channels as "#name", private channels by their name. The radio knows their keys, so even a private channel is
    recognised for certain. The public channel is left out (it is always there as PUBLIC_LABEL)."""
    out, seen = [], set()
    try:
        with db.connection() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='channels'").fetchone():
                return []
            rows = conn.execute("SELECT channel_name, channel_key_hex FROM channels ORDER BY channel_idx").fetchall()
    except Exception:  # noqa: BLE001 - no radio list yet: only the name lists
        return []
    for name, key_hex in rows:
        name = (name or "").strip()
        if not name:
            continue
        try:
            key = bytes.fromhex(key_hex or "")[:16]
        except ValueError:
            key = b""
        if name.startswith("#"):
            name = name.lower()
            key = key if len(key) == 16 else key_for_name(name)
        if len(key) != 16 or key == PUBLIC_KEY or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append((name, key))
    return out


def card_keys(config: Any) -> list:
    """[(label, key16)] for the channels on the ChannelRadar card's "Known channel keys": open channels without # whose
    key is shared publicly (a forum, a website, a group). 'Name=key' with the key as 32 hex characters, one per entry."""
    if not config.has_section("ChannelRadar"):
        return []
    raw = config.get("ChannelRadar", "known_keys", fallback="") or ""
    out, seen = [], set()
    for part in str(raw).strip("[]").replace("'", "").split(","):
        name, sep, key_hex = part.partition("=")
        if not sep:
            name, sep, key_hex = part.rpartition(":")
        name, key_hex = name.strip(), key_hex.strip().lower().replace(" ", "")
        if not name or len(key_hex) != 32 or name.lower() in seen:
            continue
        try:
            key = bytes.fromhex(key_hex)
        except ValueError:
            continue
        if key == PUBLIC_KEY:
            continue
        seen.add(name.lower())
        out.append((name[:40], key))
    return out


# ---- the dashboard: names added on the radar page, and channels to put on the radio (no restart needed)
NAMES_META = "radar.extra_names"         # JSON list of hashtag names added with 'Name it'
ADD_META = "radar.add_to_radio"          # JSON list of '#names' AutoChannels should put on the radio


def _json_list(db: Any, key: str) -> list:
    import json
    try:
        data = json.loads(db.get_metadata(key) or "[]")
        return [str(x) for x in data if str(x).strip()] if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _save_list(db: Any, key: str, items: list) -> None:
    import json
    db.set_metadata(key, json.dumps(sorted(set(items))))


def dashboard_names(db: Any) -> list:
    return _json_list(db, NAMES_META)


COMMUNITY_META = "radar.community_names"
COMMUNITY_URL = "https://meshcore-analyzer.eu/api/channels"


def community_names(db: Any) -> list:
    """Hashtag names from the community channel list (EU Meshcore Analyzer / Dutch MeshCore toolbox), fetched daily by
    the ChannelRadar service when the card asks for it. Names only: the list's messages and senders are never stored."""
    return _json_list(db, COMMUNITY_META)


def parse_community(data: Any) -> list:
    """Names from the analyzer's /api/channels ({"channels": [{"name": "#x"}]}) or the toolbox's channels-data
    ([{"channel": "#x"}]). Only hashtag names that can be a channel name; sorted, without doubles."""
    items = data.get("channels", []) if isinstance(data, dict) else (data or [])
    out = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        raw = str(it.get("name") or it.get("channel") or "")
        if raw.startswith("#"):
            n = clean_name(raw)
            if n:
                out.add(n)
    return sorted(out)


def clean_name(name: str) -> str:
    """'#Mesh-ZL ' -> 'mesh-zl'; '' when it cannot be a hashtag name."""
    n = str(name or "").strip().lower().lstrip("#").strip()
    return n if n and len(n) <= 40 and not any(c in n for c in " ,=") else ""


def verify_name(db: Any, name: str, ch_hex: str, max_rows: int = 20000) -> int:
    """How many logged group messages on channel byte `ch_hex` really belong to '#name' (byte and MAC both match).
    0 = this name is not that channel (or nothing of it is still in the packet log)."""
    import json
    n = clean_name(name)
    if not n:
        return 0
    key = key_for_name(n)
    try:
        want = int(ch_hex, 16)
    except (TypeError, ValueError):
        return 0
    if channel_byte(key) != want:
        return 0
    table = {want: [("#" + n, key)]}
    hits, seen = 0, set()
    with db.connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='packet_stream'").fetchone():
            return 0
        for (data,) in conn.execute("SELECT data FROM packet_stream WHERE type IN ('packet', 'routing') AND data LIKE '%GRP_TXT%' "
                                    "ORDER BY id DESC LIMIT ?", (max_rows,)):
            try:
                packet = json.loads(data)
            except ValueError:
                continue
            payload = packet.get("payload_hex") or ""
            if packet.get("payload_type_name") != "GRP_TXT" or not payload.startswith(f"{want:02x}"):
                continue
            k = packet.get("packet_hash") or payload[:40]
            if k in seen:
                continue
            seen.add(k)
            if identify(payload, table)[0]:
                hits += 1
    return hits


def add_dashboard_name(db: Any, name: str) -> None:
    _save_list(db, NAMES_META, dashboard_names(db) + [clean_name(name)])


def remove_dashboard_name(db: Any, name: str) -> bool:
    names = dashboard_names(db)
    n = clean_name(name)
    if n not in names:
        return False
    _save_list(db, NAMES_META, [x for x in names if x != n])
    return True


KEYS_META = "radar.known_keys"           # JSON list of {"name", "key"} added on the radar page (channels with their own key)


def dashboard_keys(db: Any) -> list:
    """[(label, key16)] of the channels with a key added on the radar page."""
    import json
    try:
        data = json.loads(db.get_metadata(KEYS_META) or "[]")
    except Exception:  # noqa: BLE001
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        try:
            out.append((str(item["name"])[:40], bytes.fromhex(str(item["key"]))))
        except (KeyError, TypeError, ValueError):
            continue
    return [(n, k) for n, k in out if n and len(k) == 16]


def add_channel(db: Any, name: str, key_hex: str = "") -> str:
    """'Add a channel' on the radar page. '#name' without a key: a hashtag channel (its key follows from the name).
    With a key (32 hex characters): a channel with its own key, any name. Returns the label. ValueError when not valid."""
    import json
    name, key_hex = str(name or "").strip(), str(key_hex or "").strip().lower().replace(" ", "")
    if not key_hex:
        n = clean_name(name)
        if not n:
            raise ValueError("a hashtag name (#name, no spaces), or a name with its key")
        add_dashboard_name(db, n)
        return "#" + n
    if len(key_hex) != 32 or any(c not in "0123456789abcdef" for c in key_hex):
        raise ValueError("the key must be 32 hex characters (0-9, a-f)")
    if not name or len(name) > 40 or any(c in name for c in ",="):
        raise ValueError("give the channel a name (no , or =)")
    if bytes.fromhex(key_hex) == PUBLIC_KEY:
        raise ValueError("that is the public channel, it is always counted")
    if name.startswith("#") and key_for_name(name.lower()).hex() == key_hex:
        add_dashboard_name(db, name)     # a hashtag channel after all: the key is the one from its name
        return "#" + clean_name(name)
    items = [{"name": n, "key": k.hex()} for n, k in dashboard_keys(db) if n.lower() != name.lower()]
    items.append({"name": name, "key": key_hex})
    db.set_metadata(KEYS_META, json.dumps(items))
    return name


def remove_channel(db: Any, label: str) -> bool:
    """Take a channel added on the radar page off again (a name or a channel with a key)."""
    import json
    label = str(label or "").strip()
    keys = dashboard_keys(db)
    left = [(n, k) for n, k in keys if n.lower() != label.lower()]
    if len(left) != len(keys):
        db.set_metadata(KEYS_META, json.dumps([{"name": n, "key": k.hex()} for n, k in left]))
        return True
    return remove_dashboard_name(db, label)


def add_to_radio_requests(db: Any) -> list:
    return _json_list(db, ADD_META)


def request_add_to_radio(db: Any, name: str) -> str:
    n = clean_name(name)
    if not n:
        raise ValueError("only hashtag channels (a name, no spaces)")
    _save_list(db, ADD_META, add_to_radio_requests(db) + ["#" + n])
    return "#" + n


def radio_signature(channels: Iterable[tuple]) -> str:
    return hashlib.sha256("\n".join(sorted(f"{label.lower()}:{key.hex()}" for label, key in channels)).encode()).hexdigest()[:16]


def build_table(names: Iterable[str], generated: Iterable[str] = (), radio: Iterable[tuple] = ()) -> dict:
    """{channel byte: [(label, key16), ...]} for the public channel, the channels on the radio (with their real keys) and
    every name; the radio first and then `names`, so they win over the same generated name."""
    table: dict = {channel_byte(PUBLIC_KEY): [(PUBLIC_LABEL, PUBLIC_KEY)]}
    seen = {PUBLIC_LABEL}
    for label, key in radio:
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        table.setdefault(channel_byte(key), []).append((label, key))
    for raw in list(names) + list(generated):
        name = raw.strip().lower().lstrip("#")
        if not name or "#" + name in seen:
            continue
        seen.add("#" + name)
        key = key_for_name(name)
        table.setdefault(channel_byte(key), []).append(("#" + name, key))
    return table


def identify(payload_hex: str, table: dict) -> tuple:
    """(label or None, channel byte as 2-hex) for one GRP_TXT payload. Never decrypts."""
    try:
        raw = bytes.fromhex(payload_hex)
    except (ValueError, TypeError):
        return None, None
    if len(raw) < 4:
        return None, None
    ch, mac, ciphertext = raw[0], raw[1:3], raw[3:]
    for label, key in table.get(ch, []):
        calc = hmac.new(key + bytes(16), ciphertext, hashlib.sha256).digest()[:2]
        if hmac.compare_digest(calc, mac):
            return label, f"{ch:02x}"
    return None, f"{ch:02x}"


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS channel_radar (
        day TEXT NOT NULL, label TEXT NOT NULL, messages INTEGER NOT NULL DEFAULT 0, last_ts INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, label))""",
    """CREATE TABLE IF NOT EXISTS channel_radar_other (
        day TEXT NOT NULL, hash TEXT NOT NULL, messages INTEGER NOT NULL DEFAULT 0, last_ts INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, hash))""",
]


def ensure_tables(db: Any) -> None:
    with db.connection() as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()


def record(conn: Any, day: str, label: Optional[str], ch_hex: str, ts: int) -> None:
    if label:
        conn.execute("""INSERT INTO channel_radar (day, label, messages, last_ts) VALUES (?,?,1,?)
                        ON CONFLICT(day, label) DO UPDATE SET messages = messages + 1, last_ts = MAX(last_ts, excluded.last_ts)""",
                     (day, label, ts))
    else:
        conn.execute("""INSERT INTO channel_radar_other (day, hash, messages, last_ts) VALUES (?,?,1,?)
                        ON CONFLICT(day, hash) DO UPDATE SET messages = messages + 1, last_ts = MAX(last_ts, excluded.last_ts)""",
                     (day, ch_hex, ts))


def main_names(bot: Any) -> set:
    """Labels that are shown from the first message: the built-in list and the names on the card."""
    extra = ""
    if bot.config.has_section("ChannelRadar"):
        extra = bot.config.get("ChannelRadar", "extra_names", fallback="") or ""
    names = list(DEFAULT_NAMES) + [n for n in str(extra).split(",") if n.strip()] + dashboard_names(bot.db_manager)
    radio = ({label for label, _ in radio_channels(bot.db_manager)} | {label for label, _ in card_keys(bot.config)}
             | {label for label, _ in dashboard_keys(bot.db_manager)})
    try:
        from .bot_network import network_channels
        names += network_channels(bot)
    except Exception:  # noqa: BLE001
        pass
    return {PUBLIC_LABEL} | {"#" + n.strip().lower().lstrip("#") for n in names} | radio


def _hunt_status(db: Any) -> dict:
    try:
        from .name_hunt import status
        return status(db)
    except Exception:  # noqa: BLE001
        return {}


def _watched(bot: Any) -> dict:
    """{label: source} of the channels the owner added that the radar looks for, also before a first message.
    source: 'card' (ChannelRadar card: names), 'card-key' (card: Name=key), 'page' (radar page: name), 'page-key'."""
    extra = bot.config.get("ChannelRadar", "extra_names", fallback="") if bot.config.has_section("ChannelRadar") else ""
    out: dict = {}
    for n in str(extra).strip("[]").replace("'", "").split(","):
        if n.strip():
            out.setdefault("#" + n.strip().lower().lstrip("#"), "card")
    for n, _ in card_keys(bot.config):
        out.setdefault(n, "card-key")
    for n in dashboard_names(bot.db_manager):
        out.setdefault("#" + n, "page")
    for n, _ in dashboard_keys(bot.db_manager):
        out.setdefault(n, "page-key")
    return out


def names_signature(names: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(set(n.strip().lower().lstrip("#") for n in names))).encode()).hexdigest()[:16]


def summary(bot: Any, now_ts: Optional[float] = None) -> dict:
    """What the dashboard page shows: every recognised channel with today / 7 days / 30 days / last seen, and the unknown ones."""
    now_ts = time.time() if now_ts is None else now_ts
    today = local_day(bot, now_ts)
    d7, d30 = (today - timedelta(days=6)).isoformat(), (today - timedelta(days=29)).isoformat()
    ensure_tables(bot.db_manager)
    with bot.db_manager.connection() as conn:
        rows = conn.execute(
            """SELECT label, SUM(CASE WHEN day = ? THEN messages ELSE 0 END), SUM(CASE WHEN day >= ? THEN messages ELSE 0 END),
                      SUM(messages), MAX(last_ts), MIN(day)
               FROM channel_radar WHERE day >= ? GROUP BY label ORDER BY 3 DESC, 4 DESC""",
            (today.isoformat(), d7, d30)).fetchall()
        other = conn.execute(
            """SELECT hash, SUM(CASE WHEN day >= ? THEN messages ELSE 0 END), SUM(messages), MAX(last_ts)
               FROM channel_radar_other WHERE day >= ? GROUP BY hash ORDER BY 2 DESC, 3 DESC""", (d7, d30)).fetchall()
        first = conn.execute("SELECT MIN(day) FROM channel_radar").fetchone()[0]
        first_ever = dict(conn.execute("SELECT label, MIN(day) FROM channel_radar GROUP BY label").fetchall())
        first_other = conn.execute("SELECT MIN(day) FROM channel_radar_other").fetchone()[0]
    since = min(d for d in (first, first_other) if d) if (first or first_other) else None
    main = main_names(bot)
    hunt = _hunt_status(bot.db_manager)
    # found by the name hunt: also marked on that day and the day after (the hunt counts back through the log, so the
    # channel's first day is old and the 'found' rule below would never see it as new)
    since_ts = day_start_ts(bot, today - timedelta(days=1))
    hunted = {str(f.get("name", "")).lower() for f in hunt.get("found", []) or [] if (f.get("ts") or 0) >= since_ts}
    # community list names: like generated names only shown from 2 messages (with ~2000 extra names the 2-byte check code
    # now and then matches a private message by chance), but not labelled 'found'
    community = {"#" + n for n in community_names(bot.db_manager)}
    return {
        "generated_at": int(now_ts),
        "since": since,
        "channels": [{"label": r[0], "today": int(r[1] or 0), "week": int(r[2] or 0), "month": int(r[3] or 0),
                      "last_ts": int(r[4] or 0), "first_day": r[5],
                      # 'found' (a generated name, not on any list) only on the day it was first heard and the day after
                      "found": r[0] not in main and r[0] not in community
                               and (first_ever.get(r[0]) or "") >= (today - timedelta(days=1)).isoformat(),
                      "hunted": r[0].lower() in hunted}
                     for r in rows if r[0] in main or int(r[3] or 0) >= 2],
        "unknown": [{"hash": r[0], "week": int(r[1] or 0), "month": int(r[2] or 0), "last_ts": int(r[3] or 0)} for r in other],
        "added_names": ["#" + n for n in dashboard_names(bot.db_manager)] + [n for n, _ in dashboard_keys(bot.db_manager)],
        "watching": [{"label": label, "source": source} for label, source in sorted(_watched(bot).items(), key=lambda kv: kv[0].lower())
                     if label not in {r[0] for r in rows}],
        "add_to_radio": add_to_radio_requests(bot.db_manager),
        "name_hunt": hunt,
    }
