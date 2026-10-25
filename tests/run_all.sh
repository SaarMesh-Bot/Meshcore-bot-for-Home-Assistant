#!/usr/bin/env bash
# Runs every test against a patched copy of the pinned upstream release, without building the add-on.
#
#   tests/run_all.sh            (WORK=/some/dir to choose where the clone, the venv and the copy live)
#
# Needs: git, python3 (with venv), network for the first run. node + npm are optional (browser-like page test).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ADDON="$HERE/../meshcore-bot"
WORK="${WORK:-/tmp/meshcore-tests}"
TAG="$(grep -o -- '--branch v[0-9][0-9.]*' "$ADDON/Dockerfile" | head -1 | awk '{print $2}')"
[ -n "$TAG" ] || { echo "cannot find the upstream tag in the Dockerfile"; exit 2; }
mkdir -p "$WORK"

if [ ! -d "$WORK/upstream-$TAG" ]; then
  echo "== cloning upstream $TAG"
  git clone -q --depth 1 --branch "$TAG" https://github.com/agessaman/meshcore-bot.git "$WORK/upstream-$TAG" || exit 2
fi
if [ ! -x "$WORK/venv/bin/python" ]; then
  echo "== creating the test environment"
  python3 -m venv "$WORK/venv" || exit 2
  "$WORK/venv/bin/pip" install -q flask flask-socketio "flask-compress==1.15" requests pytz python-dateutil aiosqlite \
      geopy maidenhead aiohttp apscheduler feedparser meshcore pyyaml paho-mqtt pynacl pyserial langdetect || exit 2
fi
PY="$WORK/venv/bin/python"
# added later (2.51.6, as in the add-on's Dockerfile): an older test environment gets it too
"$PY" -c "import langdetect" 2>/dev/null || "$WORK/venv/bin/pip" install -q langdetect

echo "== applying the add-on's patches to upstream $TAG (the build fails here if upstream moved)"
rm -rf "$WORK/sim"; mkdir -p "$WORK/sim"; cp -r "$WORK/upstream-$TAG/." "$WORK/sim/"   # a real copy, never a link to the clean clone
"$PY" "$HERE/simulate_build.py" "$WORK/sim" "$ADDON" | tail -25
BUILD=${PIPESTATUS[0]}
export SIM_TREE="$WORK/sim"

fails=0; total=0
run() {   # run <label> <command...>
  local label="$1"; shift
  local out; out="$("$@" 2>&1)"; local code=$?
  total=$((total + 1))
  if [ $code -eq 0 ]; then printf "  ok    %s\n" "$label"; else printf "  FAIL  %s\n" "$label"; echo "$out" | grep -E "^FAIL|Traceback|Error|fouten" | head -8 | sed 's/^/          /'; fails=$((fails + 1)); fi
}
[ "$BUILD" -eq 0 ] || { echo "  FAIL  build simulation"; fails=$((fails + 1)); }

echo "== tests"
cd "$WORK/sim"
run "channel watchdog"                 "$PY" "$HERE/test_channel_watchdog.py"
run "notification rate-limit fix"      "$PY" "$HERE/test_notify_limiter.py"
run "botlist + greeter skips bots"     "$PY" "$HERE/test_botlist_greeter.py"
run "greeter rollout runs once"       "$PY" "$HERE/test_greeter_rollout.py" "$SIM_TREE"
run "greeter: the delayed greeting is sent" "$PY" "$HERE/test_greeter_delayed.py" "$SIM_TREE"
run "bot name recognition"             "$PY" "$HERE/test_bot_names.py"
run "channel hint settings live"       "$PY" "$HERE/test_channel_hint_live.py"
run "repeater parser (meshcore-ha)"    "$PY" "$HERE/test_ha_parser.py"
run "repeater service"                 "$PY" "$HERE/test_ha_service.py" "$SIM_TREE"
run "CoreScope telemetry (HA -> MQTT)"    "$PY" "$HERE/test_corescope_telemetry.py" "$SIM_TREE"
run "rptr, info bot, low-battery notice" "$PY" "$HERE/test_rptr_info_notify.py" "$SIM_TREE"
run "heartbeat service"                "$PY" "$HERE/test_heartbeat.py" "$SIM_TREE"
run "repeater alerts, accu history, rptr accu" "$PY" "$HERE/test_ha_alerts.py" "$SIM_TREE"
run "translations (nl/en, all options)"  "$PY" "$HERE/test_translations.py"
run "German data: DWD/NINA warnings, Pegel, Pegel alarm" "$PY" "$HERE/test_de_data.py" "$SIM_TREE"
run "German data 2: odl, holidays per country, per-country commands" "$PY" "$HERE/test_de_pack2.py" "$SIM_TREE"
run "our own translations (nl/en/de/fr/da)" "$PY" "$HERE/test_local_translations.py"
run "Dutch, German, French, Danish coverage of upstream texts" "$PY" "$HERE/test_nl_completeness.py" "$SIM_TREE"
run "F1: data, texts and posting plan" "$PY" "$HERE/test_f1_data.py"
run "F1: prediction game"            "$PY" "$HERE/test_f1_game.py"
run "F1: service and f1 command"      "$PY" "$HERE/test_f1_service.py" "$SIM_TREE"
run "community commands, games, topu without bots" "$PY" "$HERE/test_community.py" "$SIM_TREE"
run "housekeeping: room login, config keys, contact capacity" "$PY" "$HERE/test_housekeeping.py" "$SIM_TREE"
run "channel radar (Kanaalradar)" "$PY" "$HERE/test_channel_radar.py" "$SIM_TREE"
run "name hunt at quiet hours" "$PY" "$HERE/test_name_hunt.py" "$SIM_TREE"
run "MQTT observers (packets, adverts, radar)" "$PY" "$HERE/test_observers.py" "$SIM_TREE"
run "EU Analyzer observers (regions)" "$PY" "$HERE/test_analyzer_feed.py" "$SIM_TREE"
run "Ping met meer info" "$PY" "$HERE/test_ping_info.py" "$SIM_TREE"
run "Uitgeschakeld commando blijft stil" "$PY" "$HERE/test_disabled_silent.py" "$SIM_TREE"
run "Wort repeater im Kanal ist kein Befehl" "$PY" "$HERE/test_repeater_word.py" "$SIM_TREE"
run "Begroeting en hint in de taal van de afzender" "$PY" "$HERE/test_sender_language.py" "$SIM_TREE"
run "Begroeting via DM" "$PY" "$HERE/test_greeter_dm.py" "$SIM_TREE"
run "path hash tip (1 byte -> 2 bytes)" "$PY" "$HERE/test_hash_hint.py" "$SIM_TREE"
run "language: English by default, help, ping, test bytes" "$PY" "$HERE/test_language.py" "$SIM_TREE"
run "games channel (game commands in one channel)" "$PY" "$HERE/test_games_channel.py" "$SIM_TREE"
run "Farming Idle (farm game)"              "$PY" "$HERE/test_farm_game.py" "$SIM_TREE"
run "Games page speed (Mesh RPG, DX for many names)" "$PY" "$HERE/test_games_speed.py" "$SIM_TREE"
run "issue #1: autosave, airplanes, path" "$PY" "$HERE/test_issue1_fixes.py" "$SIM_TREE"
run "trace (timeout, tracert) and discover" "$PY" "$HERE/test_trace_discover.py" "$SIM_TREE"
run "interval advert survives a restart" "$PY" "$HERE/test_advert_interval.py" "$SIM_TREE"
run "contact cleanup: far repeaters make room" "$PY" "$HERE/test_contact_cleanup.py" "$SIM_TREE"
run "problems page (warnings, errors, unanswered)" "$PY" "$HERE/test_problem_log.py" "$SIM_TREE"
run "web viewer: stop signal, live events" "$PY" "$HERE/test_webviewer_quiet.py" "$SIM_TREE"
run "dashboard: live connection only where used" "$PY" "$HERE/test_lazy_socket.py" "$SIM_TREE"
run "ha: Home Assistant over the mesh (admins)" "$PY" "$HERE/test_ha_command.py" "$SIM_TREE"
run "mailbox (post)" "$PY" "$HERE/test_mailbox.py" "$SIM_TREE"
run "AutoChannels (missing hashtag channels)" "$PY" "$HERE/test_auto_channels.py" "$SIM_TREE"
run "HA sensors"                       "$PY" "$HERE/test_ha_sensors.py" "$SIM_TREE"
run "RepeaterWatch (silent repeaters)"  "$PY" "$HERE/test_repeater_watch.py" "$SIM_TREE"
run "bot network over the internet (signed, trust, schedule)" "$PY" "$HERE/test_bot_network.py" "$SIM_TREE"
run "bot network: only the closest bot answers" "$PY" "$HERE/test_answer_arbitration.py" "$SIM_TREE"
run "night mode (scheduled, feeds, webhook)" "$PY" "$HERE/test_night_mode.py" "$SIM_TREE"
run "export/import via /share (moving the bot)" "$PY" "$HERE/test_data_transfer.py"
run "generate_config (options -> config.ini)" "$PY" "$HERE/test_generator.py"
run "settings cards (Plugins page)"    "$PY" "$HERE/test_cards.py" "$SIM_TREE"
run "Bots page"                        "$PY" "$HERE/test_bots_page.py" "$SIM_TREE"
run "Repeater page"                    "$PY" "$HERE/test_repeater_page.py" "$SIM_TREE"
run "Bot network page"                 "$PY" "$HERE/test_botnet_page.py" "$SIM_TREE"
run "sidebar (ingress), no password"   "$PY" "$HERE/test_ingress.py" "$SIM_TREE" ""
run "sidebar (ingress), with password" "$PY" "$HERE/test_ingress.py" "$SIM_TREE" "secret"
run "dashboard users (admin, viewer, repeaters)" "$PY" "$HERE/test_web_users.py" "$SIM_TREE"
run "proxy: priority port"            "$PY" "$HERE/test_proxy_priority.py"
run "proxy: WiFi companion over TCP" "$PY" "$HERE/test_proxy_wifi.py"

if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  if [ ! -d "$WORK/jsd/node_modules/jsdom" ]; then
    mkdir -p "$WORK/jsd"; ( cd "$WORK/jsd" && npm init -y >/dev/null 2>&1 && npm install --silent --no-audit --no-fund jsdom >/dev/null 2>&1 )
  fi
  "$PY" "$HERE/gen_bots_html.py" "$SIM_TREE" "$WORK/bots.html" >/dev/null 2>&1
  run "Bots page in a browser-like DOM"  env NODE_PATH="$WORK/jsd/node_modules" node "$HERE/ui_test.js" "$WORK/bots.html"
  "$PY" "$HERE/gen_webui_page.py" "$SIM_TREE" "$WORK/webui.json" nl >/dev/null 2>&1
  run "dashboard in the bot language (browser-like DOM)" env NODE_PATH="$WORK/jsd/node_modules" node "$HERE/webui_test.js" "$WORK/webui.json"
else
  echo "  skip  Bots page in a browser-like DOM (node/npm not installed)"
fi

echo "== $((total - fails)) of $total passed"
exit $fails
