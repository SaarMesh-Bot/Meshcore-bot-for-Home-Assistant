#!/usr/bin/env python3
"""Source patch: MapUploader counts its uploads instead of logging two lines per node.

Upstream logs "Uploading {...}" and "Upload successful: {...}" at INFO for every repeater advert it sends to
map.meshcore.dev: hundreds of lines a day that push real messages out of view, and they do not say whether the uploads
help (a duplicate the map already had is only logged at debug). Now those two lines are debug, every result is counted
per day (modules/map_upload_stats.py: sent, new, duplicate, failed) and one summary line is logged an hour. Failures
keep their own warning line. The Repeater radar shows today's numbers.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")



FILE = "modules/service_plugins/map_uploader_service.py"

patch(FILE, """            self.logger.info(f"Uploading {node_info}")""",
      """            self.logger.debug(f"Uploading {node_info}")
            self._addon_count("sent")""")
patch(FILE, """                    self.logger.warning(f"Upload failed (status {response.status}): {error_text} (JSON parse error: {e})")""",
      """                    self.logger.warning(f"Upload failed (status {response.status}): {error_text} (JSON parse error: {e})")
                    self._addon_count("failed")""")
patch(FILE, """                                f"Map API already had this advert (node {node}...); {err} ({code})"
                            )""",
      """                                f"Map API already had this advert (node {node}...); {err} ({code})"
                            )
                            self._addon_count("duplicate")""")
patch(FILE, """                                f"Upload failed for node {node}...: {err} (code: {code})"
                            )""",
      """                                f"Upload failed for node {node}...: {err} (code: {code})"
                            )
                            self._addon_count("failed")""")
patch(FILE, """                        self.logger.info(f"Upload successful: {result}")""",
      """                        self.logger.debug(f"Upload successful: {result}")
                        self._addon_count("new")""")
patch(FILE, """                    self.logger.warning(f"Upload failed (status {response.status}): {error_text}")""",
      """                    self.logger.warning(f"Upload failed (status {response.status}): {error_text}")
                    self._addon_count("failed")""")
patch(FILE, """            self.logger.warning("Upload timeout")""",
      """            self.logger.warning("Upload timeout")
            self._addon_count("failed")""")
patch(FILE, """            self.logger.error(f"Error uploading to map: {e}", exc_info=True)""",
      """            self.logger.error(f"Error uploading to map: {e}", exc_info=True)
            self._addon_count("failed")""")
patch(FILE, """    def _sign_data(self, data: dict[str, Any]) -> dict[str, Any]:""",
      """    def _addon_count(self, kind: str) -> None:
        \"\"\"(add-on) count one upload result per day, and log one summary line an hour.\"\"\"
        try:
            from ..map_upload_stats import HourlySummary, record
            if not hasattr(self, "_addon_hourly"):
                self._addon_hourly = HourlySummary()
            self._addon_hourly.add(kind, self.logger)
            record(self.bot.db_manager, kind)
        except Exception as e:  # counting must never stop an upload
            self.logger.debug(f"Map upload count failed: {e}")

    def _sign_data(self, data: dict[str, Any]) -> dict[str, Any]:""")
