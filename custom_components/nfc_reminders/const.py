"""Constants for NFC Reminders."""

DOMAIN = "nfc_reminders"

CONF_REMINDER_NAME = "reminder_name"
CONF_NFC_TAG_IDS = "nfc_tag_ids"  # comma separated
CONF_INTERVAL = "interval"
CONF_INTERVAL_UNIT = "interval_unit"

INTERVAL_UNITS = ["minutes", "hours", "days"]
UNIT_SECONDS = {"minutes": 60, "hours": 3600, "days": 86400}
DEFAULT_INTERVAL = 7
DEFAULT_INTERVAL_UNIT = "days"

# v1 stored a single tag under one of these keys, checked in order.
LEGACY_CONF_NFC_TAG_IDS = ("nfc_tag_id", "nfc_tag", "tag_id")

EVENT_TAG_SCANNED = "tag_scanned"
SERVICE_MARK_DONE = "mark_done"

STORAGE_VERSION = 1

# Seconds between refreshes of the time based values.
UPDATE_INTERVAL_SECONDS = 60

# Progress percent where status goes from "good" to "warning".
WARNING_PERCENT = 80

DEFAULT_SCANNER = "NFC Scan"

# v1 unique IDs were "{slug}_{suffix}", v2 uses "{entry_id}_{key}".
# This maps each v1 suffix to its v2 key.
LEGACY_UNIQUE_ID_SUFFIXES = {
    "last_scan_display": "last_scan",
    "last_scan": "last_scan",
    "days_since_scan": "days_since",
    "days_since": "days_since",
    "progress": "progress",
}
