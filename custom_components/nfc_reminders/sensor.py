"""Sensors for NFC Reminders."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
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
    async_add_entities(
        [
            NFCReminderLastScanSensor(data),
            NFCReminderLastScannedBySensor(data),
            NFCReminderDaysSinceSensor(data),
            NFCReminderProgressSensor(data),
            NFCReminderDaysRemainingSensor(data),
        ]
    )


class NFCReminderLastScanSensor(NFCReminderEntity, SensorEntity):
    _attr_name = "Last Scan"
    _attr_icon = "mdi:nfc-variant"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, data: ReminderData) -> None:
        super().__init__(data, "last_scan")

    @property
    def native_value(self) -> datetime | None:
        return self._data.last_scan

    @property
    def extra_state_attributes(self) -> dict:
        return {"scanned_by": self._data.last_scanned_by}


class NFCReminderLastScannedBySensor(NFCReminderEntity, SensorEntity):
    _attr_name = "Last Scanned By"
    _attr_icon = "mdi:account-check"

    def __init__(self, data: ReminderData) -> None:
        super().__init__(data, "last_scanned_by")

    @property
    def native_value(self) -> str | None:
        return self._data.last_scanned_by


class NFCReminderDaysSinceSensor(NFCReminderEntity, SensorEntity):
    _attr_name = "Days Since Scan"
    _attr_icon = "mdi:calendar-clock"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, data: ReminderData) -> None:
        super().__init__(data, "days_since")

    @property
    def native_value(self) -> float | None:
        return self._data.days_since


class NFCReminderProgressSensor(NFCReminderEntity, SensorEntity):
    _attr_name = "Progress"
    _attr_icon = "mdi:progress-clock"
    _attr_native_unit_of_measurement = "%"

    def __init__(self, data: ReminderData) -> None:
        super().__init__(data, "progress")

    @property
    def native_value(self) -> int:
        return self._data.progress

    @property
    def extra_state_attributes(self) -> dict:
        return self._data.attributes


class NFCReminderDaysRemainingSensor(NFCReminderEntity, SensorEntity):
    _attr_name = "Days Remaining"
    _attr_icon = "mdi:calendar-end"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, data: ReminderData) -> None:
        super().__init__(data, "days_remaining")

    @property
    def native_value(self) -> float | None:
        return self._data.days_remaining
