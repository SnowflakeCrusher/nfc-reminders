"""Config flow for NFC Reminders."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify

from .common import parse_tags
from .const import (
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_NFC_TAG_IDS,
    CONF_REMINDER_NAME,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DOMAIN,
    INTERVAL_UNITS,
)


def _user_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_REMINDER_NAME,
                default=defaults.get(CONF_REMINDER_NAME, vol.UNDEFINED),
            ): cv.string,
            vol.Required(
                CONF_NFC_TAG_IDS,
                default=defaults.get(CONF_NFC_TAG_IDS, vol.UNDEFINED),
            ): cv.string,
            vol.Required(
                CONF_INTERVAL, default=defaults.get(CONF_INTERVAL, DEFAULT_INTERVAL)
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Required(
                CONF_INTERVAL_UNIT,
                default=defaults.get(CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT),
            ): vol.In(INTERVAL_UNITS),
        }
    )


class NFCRemindersConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            name = user_input[CONF_REMINDER_NAME].strip()
            slug = slugify(name)
            tags = parse_tags(user_input[CONF_NFC_TAG_IDS])

            if not slug:
                errors[CONF_REMINDER_NAME] = "invalid_name"
            elif any(
                slugify(entry.data.get(CONF_REMINDER_NAME, "")) == slug
                for entry in self._async_current_entries()
            ):
                # Entity IDs come from the slug, so compare slugs.
                errors["base"] = "name_exists"

            if not tags:
                errors[CONF_NFC_TAG_IDS] = "no_tags"

            if not errors:
                await self.async_set_unique_id(slug)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data={
                        **user_input,
                        CONF_REMINDER_NAME: name,
                        CONF_NFC_TAG_IDS: ", ".join(tags),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NFCRemindersOptionsFlow()


class NFCRemindersOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            tags = parse_tags(user_input[CONF_NFC_TAG_IDS])
            if not tags:
                errors[CONF_NFC_TAG_IDS] = "no_tags"
            else:
                # Not a coroutine. The update listener reloads the entry.
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        **self.config_entry.data,
                        **user_input,
                        CONF_NFC_TAG_IDS: ", ".join(tags),
                    },
                )
                return self.async_create_entry(title="", data={})

        current = {
            CONF_NFC_TAG_IDS: self.config_entry.data.get(CONF_NFC_TAG_IDS, ""),
            CONF_INTERVAL: self.config_entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL),
            CONF_INTERVAL_UNIT: self.config_entry.data.get(
                CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT
            ),
        }
        defaults = user_input or current
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NFC_TAG_IDS, default=defaults[CONF_NFC_TAG_IDS]
                    ): cv.string,
                    vol.Required(
                        CONF_INTERVAL, default=defaults[CONF_INTERVAL]
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                    vol.Required(
                        CONF_INTERVAL_UNIT, default=defaults[CONF_INTERVAL_UNIT]
                    ): vol.In(INTERVAL_UNITS),
                }
            ),
            errors=errors,
        )
