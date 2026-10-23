"""NFC Reminders Integration - Enhanced."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .common import ReminderData
from .const import (
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_NFC_TAG_IDS,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DEFAULT_SCANNER,
    DOMAIN,
    EVENT_TAG_SCANNED,
    LEGACY_CONF_NFC_TAG_IDS,
    LEGACY_UNIQUE_ID_SUFFIXES,
    SERVICE_MARK_DONE,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

MARK_DONE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def async_mark_done(call: ServiceCall) -> None:
        config_entry_ids: set[str] = set()

        ent_reg = er.async_get(hass)
        for entity_id in call.data.get(ATTR_ENTITY_ID, []):
            entity_entry = ent_reg.async_get(entity_id)
            if entity_entry and entity_entry.config_entry_id:
                config_entry_ids.add(entity_entry.config_entry_id)

        dev_reg = dr.async_get(hass)
        for device_id in call.data.get(ATTR_DEVICE_ID, []):
            device = dev_reg.async_get(device_id)
            if device:
                config_entry_ids.update(device.config_entries)

        reminders = hass.data.get(DOMAIN, {})
        targets = [reminders[eid] for eid in config_entry_ids if eid in reminders]
        if not targets:
            _LOGGER.warning(
                "NFC Reminders: mark_done did not match any reminder (%s)",
                dict(call.data),
            )
            return

        who = await _async_user_name(hass, call.context.user_id) or "Manual"
        for data in targets:
            await data.async_record_scan(who)

    hass.services.async_register(
        DOMAIN, SERVICE_MARK_DONE, async_mark_done, schema=MARK_DONE_SCHEMA
    )
    return True


async def _async_user_name(hass: HomeAssistant, user_id: str | None) -> str | None:
    if not user_id:
        return None
    user = await hass.auth.async_get_user(user_id)
    if user and user.name:
        return user.name
    return None


def _device_name(hass: HomeAssistant, device_id: str | None) -> str | None:
    if not device_id:
        return None
    device = dr.async_get(hass).async_get(device_id)
    if device:
        return device.name_by_user or device.name
    return None


def _make_scan_handler(hass: HomeAssistant, data: ReminderData):
    async def handle_tag_scanned(event: Event) -> None:
        tag_id = event.data.get("tag_id")
        _LOGGER.debug(
            "NFC Reminders: tag_scanned received for '%s': tag_id=%r configured=%r",
            data.reminder_name,
            tag_id,
            data.tags,
        )
        if not tag_id:
            return
        configured = {tag.upper() for tag in data.tags}
        if str(tag_id).strip().upper() not in configured:
            return

        # User first, then the scanning device, then a generic label.
        who = (
            await _async_user_name(hass, event.context.user_id)
            or _device_name(hass, event.data.get("device_id"))
            or DEFAULT_SCANNER
        )
        _LOGGER.info(
            "NFC Reminders: Tag %s scanned for '%s' by %s",
            tag_id,
            data.reminder_name,
            who,
        )
        await data.async_record_scan(who)

    return handle_tag_scanned


@callback
def _async_migrate_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry, safe_name: str
) -> None:
    """Switch v1 unique IDs to v2 ones so entity IDs and history stay put."""
    ent_reg = er.async_get(hass)
    old_to_key = {
        f"{safe_name}_{suffix}": key
        for suffix, key in LEGACY_UNIQUE_ID_SUFFIXES.items()
    }
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        key = old_to_key.get(entity_entry.unique_id)
        if key is None:
            continue
        new_unique_id = f"{entry.entry_id}_{key}"
        duplicate = ent_reg.async_get_entity_id(
            entity_entry.domain, DOMAIN, new_unique_id
        )
        if duplicate:
            # A v2 entity already exists next to the old one. Drop it and
            # keep the original.
            ent_reg.async_remove(duplicate)
            _LOGGER.info("NFC Reminders: Removed duplicate entity %s", duplicate)
        ent_reg.async_update_entity(
            entity_entry.entity_id, new_unique_id=new_unique_id
        )
        _LOGGER.info(
            "NFC Reminders: Migrated unique_id of %s", entity_entry.entity_id
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = ReminderData(hass, entry)
    _async_migrate_unique_ids(hass, entry, data.safe_name)
    await data.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data
    data.async_start()

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_TAG_SCANNED, _make_scan_handler(hass, data))
    )
    # Reload on Configure so a new interval or tag list applies right away.
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data: ReminderData | None = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data:
            # Write out anything still waiting in the delayed save.
            await data.async_save()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the stored state. Entities and the device are removed by HA."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
    _LOGGER.info("NFC Reminders: Removed stored data for '%s'", entry.title)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate v1 entries (one tag) to v2 (comma separated tags)."""
    if entry.version > 2:
        return False

    if entry.version < 2:
        data = {**entry.data}
        legacy_tags = []
        for legacy_key in LEGACY_CONF_NFC_TAG_IDS:
            value = data.pop(legacy_key, None)
            if value:
                legacy_tags.append(str(value).strip())
        if not data.get(CONF_NFC_TAG_IDS):
            data[CONF_NFC_TAG_IDS] = ", ".join(tag for tag in legacy_tags if tag)
        data.setdefault(CONF_INTERVAL, DEFAULT_INTERVAL)
        data.setdefault(CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT)
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.info("NFC Reminders: Migrated '%s' to version 2", entry.title)

    return True
