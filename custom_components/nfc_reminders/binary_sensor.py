"""Overdue binary sensor for NFC Reminders."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .common import NFCReminderEntity, ReminderData
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: ReminderData = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([NFCReminderOverdueSensor(data)])


class NFCReminderOverdueSensor(NFCReminderEntity, BinarySensorEntity):
    _attr_name = "Overdue"
    _attr_icon = "mdi:alert-circle"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, data: ReminderData) -> None:
        super().__init__(data, "overdue")

    @property
    def is_on(self) -> bool:
        return self._data.is_overdue

    @property
    def extra_state_attributes(self) -> dict:
        return self._data.attributes
