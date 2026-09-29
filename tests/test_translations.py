"""Vertalingen van de add-onopties: nl en en hebben dezelfde sleutels, en elke optie in config.yaml heeft een tekst."""
import pathlib as _pl, sys
import yaml
ADDON = _pl.Path(__file__).resolve().parent.parent / "meshcore-bot"
fails = []
def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c: fails.append(m)

def keys(tree, prefix=""):
    out = set()
    for k, v in (tree or {}).items():
        if k in ("name", "description") and not isinstance(v, dict): out.add(prefix.rstrip(".") + ":" + k); continue
        if isinstance(v, dict): out |= keys(v, f"{prefix}{k}.")
    return out

nl = yaml.safe_load(open(ADDON / "translations/nl.yaml"))["configuration"]
en = yaml.safe_load(open(ADDON / "translations/en.yaml"))["configuration"]
cfg = yaml.safe_load(open(ADDON / "config.yaml"))
check(keys(nl) == keys(en), f"nl en en hebben precies dezelfde sleutels ({sorted(keys(nl) ^ keys(en))[:6]})")
missing = []
for group, fields in cfg["schema"].items():
    if isinstance(fields, dict):
        for f in fields:
            for t, tree in (("nl", nl), ("en", en)):
                node = (((tree.get(group) or {}).get("fields") or {}).get(f) or {})
                if not node.get("name") or not node.get("description"): missing.append(f"{t}:{group}.{f}")
    else:
        for t, tree in (("nl", nl), ("en", en)):
            if not (tree.get(group) or {}).get("name"): missing.append(f"{t}:{group}")
check(not missing, f"elke optie in config.yaml heeft naam en uitleg in nl en en {missing[:8]}")
opt = cfg["options"]; sch = cfg["schema"]
check(opt["bot"]["language"] == "en" and sch["bot"]["language"] == "list(nl|en|de|fr)?" and opt["bot"]["rate_limit_seconds"] == 4,
      "opties: taal standaard en (nieuwe installaties), keuze nl/en/de/fr, zendgrens 4 seconden")
check(not any(k.strip().lower().startswith("ping") for k in opt["advanced"]["keywords"]), "geen vast ping-trefwoord: ping antwoordt vertaald met de tip over test")
print(f"\n{len(fails)} fouten"); sys.exit(1 if fails else 0)
