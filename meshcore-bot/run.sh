#!/usr/bin/with-contenv bashio
set -e

# Read by the notification service so it can say which version started.
export ADDON_VERSION=$(bashio::addon.version)

# The add-on's own address on Home Assistant's internal network: where the sidebar (ingress) connects.
# Used to close the viewer port to the local network (webviewer.lan_access: false).
export MESHCORE_VIEWER_BIND=$(bashio::addon.ip_address)

# Moving the bot: export to /share/meshcore-bot/export/ when /share/meshcore-bot/EXPORT exists, and import from
# /share/meshcore-bot/import/ on a new installation (see data_transfer.py). Never stops the start.
python3 /opt/data_transfer.py /data /share/meshcore-bot || true

# All option handling lives in generate_config.py (tested separately, copes
# with lists and nested groups, and falls back to defaults for anything missing).
# /config is the add-on's own folder (/addon_configs/..._meshcore_bot in the File Editor): a copy of config.ini to
# look at (config-current.ini) and override.ini for your own lines.
python3 /opt/generate_config.py /data/options.json /data/config.ini /data /config

BOT_NAME=$(jq -r '.bot.name // "MeshCoreBot"' /data/options.json)
CONNECTION_TYPE=$(jq -r '.connection.type // "tcp"' /data/options.json)
bashio::log.info "Starting meshcore-bot '${BOT_NAME}' via ${CONNECTION_TYPE}..."

cd /opt/meshcore-bot
exec python3 meshcore_bot.py --config /data/config.ini
