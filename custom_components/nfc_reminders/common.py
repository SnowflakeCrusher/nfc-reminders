"""Reminder state and the shared entity base class.

The last scan is kept in .storage by the integration. If input_datetime /
input_text helpers with the old v1 names exist, they are kept in sync so
existing cards keep working.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify

from .const import (
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_NFC_TAG_IDS,
    CONF_REMINDER_NAME,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DOMAIN,
    STORAGE_VERSION,
    UNIT_SECONDS,
    UPDATE_INTERVAL_SECONDS,
    WARNING_PERCENT,
)

_LOGGER = logging.getLogger(__name__)

_INVALID_STATES = (STATE_UNKNOWN, STATE_UNAVAILABLE, "")


def parse_tags(value: Any) -> list[str]:
    """Turn "a, b" into ["a", "b"]."""
    if not value:
        return []
    return [tag.strip() for tag in str(value).split(",") if tag.strip()]


def parse_datetime(value: str | None) -> datetime | None:
    """Parse a datetime string, treating naive values as local time."""
    if not value or value in _INVALID_STATES:
        return None
    try:
        parsed = dt_util.parse_datetime(value)
    except ValueError:
        return None
    if parsed is None:
        return None
    # input_datetime states have no tzinfo and are in local time.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed


class ReminderData:
    """State and calculations for one reminder."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.reminder_name: str = entry.data[CONF_REMINDER_NAME]
        self.safe_name = slugify(self.reminder_name)
        self.datetime_helper = f"input_datetime.{self.safe_name}_last_scan"
        self.text_helper = f"input_text.{self.safe_name}_last_cleaned_by"
        self.signal = f"{DOMAIN}_update_{entry.entry_id}"
        self.last_scan: datetime | None = None
        self.last_scanned_by: str | None = None
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    @property
    def interval(self) -> int:
        return self.entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL)

    @property
    def unit(self) -> str:
        return self.entry.data.get(CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT)

    @property
    def tags(self) -> list[str]:
        return parse_tags(self.entry.data.get(CONF_NFC_TAG_IDS, ""))

    @property
    def threshold(self) -> timedelta:
        return timedelta(seconds=self.interval * UNIT_SECONDS.get(self.unit, 86400))

    def _store_payload(self) -> dict[str, Any]:
        return {
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "last_scanned_by": self.last_scanned_by,
        }

    async def async_save(self) -> None:
        await self._store.async_save(self._store_payload())

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self.last_scan = parse_datetime(stored.get("last_scan"))
        self.last_scanned_by = stored.get("last_scanned_by")
        changed = False

        # First start after upgrading from v1: pull the values from the
        # helpers if they exist.
        if self.last_scan is None:
            state = self.hass.states.get(self.datetime_helper)
            seeded = parse_datetime(state.state if state else None)
            if seeded:
                self.last_scan = seeded
                changed = True
                _LOGGER.info(
                    "NFC Reminders: Imported last scan for '%s' from %s",
                    self.reminder_name,
                    self.datetime_helper,
                )

        if not self.last_scanned_by:
            state = self.hass.states.get(self.text_helper)
            if state and state.state not in _INVALID_STATES + ("Unknown",):
                self.last_scanned_by = state.state
                changed = True

        if changed:
            await self.async_save()

    @callback
    def async_start(self) -> None:
        """Start watching the helper for manual edits."""
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, [self.datetime_helper], self._async_helper_changed
            )
        )

    @callback
    def _async_helper_changed(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        helper_dt = parse_datetime(new_state.state if new_state else None)
        if helper_dt is None:
            return
        # Helper showing up after startup shouldn't overwrite what we have.
        if old_state is None and self.last_scan is not None:
            return
        # Skip the change we caused ourselves.
        if (
            self.last_scan is not None
            and abs((helper_dt - self.last_scan).total_seconds()) < 1
        ):
            return
        _LOGGER.info(
            "NFC Reminders: %s was edited, updating '%s'",
            self.datetime_helper,
            self.reminder_name,
        )
        self.last_scan = helper_dt
        self._store.async_delay_save(self._store_payload, 1)
        async_dispatcher_send(self.hass, self.signal)

    async def async_record_scan(
        self, who: str | None = None, when: datetime | None = None
    ) -> None:
        self.last_scan = (when or dt_util.now()).replace(microsecond=0)
        if who:
            self.last_scanned_by = who
        await self.async_save()
        async_dispatcher_send(self.hass, self.signal)
        await self._async_mirror_helpers()
        _LOGGER.info(
            "NFC Reminders: Recorded '%s' (by %s)",
            self.reminder_name,
            self.last_scanned_by,
        )

    async def _async_mirror_helpers(self) -> None:
        """Write to the helpers if the user has them."""
        if self.last_scan and self.hass.states.get(self.datetime_helper):
            try:
                await self.hass.services.async_call(
                    "input_datetime",
                    "set_datetime",
                    {
                        "entity_id": self.datetime_helper,
                        "datetime": dt_util.as_local(self.last_scan).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    },
                    blocking=True,
                )
            except (HomeAssistantError, vol.Invalid) as err:
                _LOGGER.warning(
                    "NFC Reminders: Could not update %s: %s",
                    self.datetime_helper,
                    err,
                )
        if self.last_scanned_by and self.hass.states.get(self.text_helper):
            try:
                await self.hass.services.async_call(
                    "input_text",
                    "set_value",
                    {
                        "entity_id": self.text_helper,
                        "value": self.last_scanned_by,
                    },
                    blocking=True,
                )
            except (HomeAssistantError, vol.Invalid) as err:
                _LOGGER.warning(
                    "NFC Reminders: Could not update %s: %s",
                    self.text_helper,
                    err,
                )

    @property
    def next_due(self) -> datetime | None:
        if self.last_scan is None:
            return None
        return self.last_scan + self.threshold

    @property
    def days_since(self) -> float | None:
        if self.last_scan is None:
            return None
        return round((dt_util.now() - self.last_scan).total_seconds() / 86400, 1)

    @property
    def days_remaining(self) -> float | None:
        due = self.next_due
        if due is None:
            return None
        return round((due - dt_util.now()).total_seconds() / 86400, 1)

    @property
    def progress(self) -> int:
        """Percent of the interval used, capped at 100. Never scanned is 100."""
        if self.last_scan is None:
            return 100
        threshold = self.threshold.total_seconds()
        if threshold <= 0:
            return 100
        elapsed = (dt_util.now() - self.last_scan).total_seconds()
        return max(0, min(100, round(elapsed / threshold * 100)))

    @property
    def is_overdue(self) -> bool:
        due = self.next_due
        return due is None or dt_util.now() >= due

    @property
    def status(self) -> str:
        if self.is_overdue:
            return "overdue"
        if self.progress >= WARNING_PERCENT:
            return "warning"
        return "good"

    @property
    def attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "status": self.status,
            "never_scanned": self.last_scan is None,
            "interval": self.interval,
            "interval_unit": self.unit,
            CONF_NFC_TAG_IDS: self.tags,
            "last_scanned_by": self.last_scanned_by,
        }
        if self.last_scan is not None:
            attrs["last_scan"] = dt_util.as_local(self.last_scan).isoformat()
            attrs["next_due"] = dt_util.as_local(self.next_due).isoformat()
            attrs["days_since"] = self.days_since
            attrs["days_remaining"] = self.days_remaining
        return attrs


class NFCReminderEntity(Entity):
    """Base for all reminder entities. Updates on scans and once a minute."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, data: ReminderData, key: str) -> None:
        self._data = data
        self._attr_unique_id = f"{data.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data.entry.entry_id)},
            name=data.reminder_name,
            manufacturer="NFC Reminders",
            model="Reminder",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _refresh(*_args: Any) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._data.signal, _refresh)
        )
        # Progress, days remaining and overdue change without any scan.
        self.async_on_remove(
            async_track_time_interval(
                self.hass, _refresh, timedelta(seconds=UPDATE_INTERVAL_SECONDS)
            )
        )
