# NFC Reminders for Home Assistant

Track recurring chores (litter box, furnace filter, watering plants, pet meds) with an NFC tag. Scan the tag when you do the chore. Home Assistant records the time and who did it, and flags the chore as overdue when the interval runs out.

Everything is set up from the UI. You don't need to write YAML or create helpers.

## How it works

1. You create a reminder with a name, one or more tag IDs, and an interval, such as 90 days.
2. Scanning a tag makes Home Assistant fire a `tag_scanned` event.
3. If the tag ID matches one of the reminder's tags, the reminder saves the current time as its last scan, along with who scanned it.
4. Once the interval has passed since the last scan, the reminder is overdue.

You can also mark a reminder done without a tag by using the `nfc_reminders.mark_done` action.

## Installation

### HACS

1. In HACS, open the three dot menu and choose Custom repositories.
2. Add `https://github.com/SnowflakeCrusher/nfc-reminders` as an Integration.
3. Download NFC Reminders and restart Home Assistant.

### Manual

Copy `custom_components/nfc_reminders` into your Home Assistant `custom_components` folder and restart.

Requires Home Assistant 2024.12.0 or newer.

## Adding a reminder

Go to Settings > Devices & services > Add integration and pick NFC Reminders. Fill in:

- **Reminder Name**, for example `Furnace Filter`
- **NFC Tag IDs**, one or more, separated by commas, for example `abc-123, def-456`
- **Interval** and **Interval Unit** (minutes, hours or days)

Tag IDs aren't case sensitive, and spaces around the commas are ignored.

### Finding a tag ID

Go to Settings > Tools > Events. Under Listen to events, enter `tag_scanned`, click Start listening, then scan the tag. The ID is shown as `tag_id`.

(Before Home Assistant 2026.2, Tools was called Developer tools and had its own sidebar entry.)

### Using more than one tag

A reminder can have several tag IDs. Scanning any one of them marks it done. You don't have to scan all of them, and you can't anyway, since a phone or reader reads one tag at a time.

This is handy when the same chore can be done in more than one place, like a tag by the kitchen bin and another by the garage door. It also makes replacing a worn out tag painless: add the new ID next to the old one, and remove the old one later.

## Entities

Each reminder becomes a device. For a reminder named Furnace Filter you get:

| Entity | What it shows |
|---|---|
| `sensor.furnace_filter_last_scan` | When it was last scanned |
| `sensor.furnace_filter_last_scanned_by` | Who scanned it |
| `sensor.furnace_filter_days_since_scan` | Days since the last scan |
| `sensor.furnace_filter_progress` | Percent of the interval used, up to 100 |
| `sensor.furnace_filter_days_remaining` | Days until due, negative once overdue |
| `binary_sensor.furnace_filter_overdue` | On when overdue |

Last Scan is a real timestamp, so Home Assistant displays it in your local time. Days values are rounded to one decimal. Everything refreshes once a minute, so Overdue can lag up to a minute behind the due time.

The Overdue sensor is a problem type sensor. Its state is `on` or `off`, and the UI shows Problem or OK.

### Status

Progress and Overdue both carry a `status` attribute:

| Status | Meaning |
|---|---|
| `good` | Less than 80% of the interval used |
| `warning` | 80% or more used, not due yet |
| `overdue` | The interval has passed, or it has never been scanned |

### A new reminder starts out overdue

There's no scan yet, so a new reminder counts as overdue. Progress is 100, `never_scanned` is true, and Last Scan shows unknown. Scan the tag or run `mark_done` once to start the clock.

### Attributes

Progress and Overdue both have these attributes:

| Attribute | Example | Notes |
|---|---|---|
| `status` | `good` | See above |
| `never_scanned` | `false` | |
| `interval`, `interval_unit` | `90`, `days` | |
| `nfc_tag_ids` | `["abc-123", "def-456"]` | Every configured tag |
| `last_scanned_by` | `SnowflakeCrusher` | |
| `last_scan` | `2026-10-22T08:15:00-05:00` | After the first scan |
| `next_due` | `2027-01-20T08:15:00-05:00` | After the first scan |
| `days_since` | `3.2` | After the first scan |
| `days_remaining` | `86.8` | After the first scan |

## Who scanned

The reminder records the first of these it can find:

1. The Home Assistant user behind the scan, such as the person using the Companion app
2. The name of the device that reported the scan
3. `NFC Scan`

It's stored in `sensor.{name}_last_scanned_by`.

## The mark_done action

`nfc_reminders.mark_done` does what a scan does: it sets the last scan to now and restarts the interval. Point it at any entity or device of the reminder. You can target several reminders in one call.

The name recorded is the user who ran it, or `Manual` when there's no user, such as from an automation.

```yaml
action: nfc_reminders.mark_done
target:
  entity_id: binary_sensor.furnace_filter_overdue
```

A dashboard button for it:

```yaml
type: button
name: Furnace filter done
tap_action:
  action: perform-action
  perform_action: nfc_reminders.mark_done
  target:
    entity_id: binary_sensor.furnace_filter_overdue
```

## Testing without a tag

1. Go to Settings > Tools > Events.
2. Under Fire event, set the event type to `tag_scanned`.
3. Set the event data to your tag ID:

```yaml
tag_id: your-tag-id
```

4. Click Fire event, then look at the reminder's entities on the States tab.

A tag ID that isn't on any reminder is ignored.

## Automations

Notify when a reminder goes overdue:

```yaml
alias: Furnace filter overdue
triggers:
  - trigger: state
    entity_id: binary_sensor.furnace_filter_overdue
    from: "off"
    to: "on"
actions:
  - action: notify.notify
    data:
      title: Furnace filter
      message: >
        The furnace filter is overdue. Last done by
        {{ state_attr('binary_sensor.furnace_filter_overdue', 'last_scanned_by') or 'nobody yet' }}.
```

Nag every morning while it's overdue:

```yaml
alias: Furnace filter daily nag
triggers:
  - trigger: time
    at: "09:00:00"
conditions:
  - condition: state
    entity_id: binary_sensor.furnace_filter_overdue
    state: "on"
actions:
  - action: notify.notify
    data:
      message: "Furnace filter is overdue. Scan the tag when done."
```

Warn before it's due:

```yaml
alias: Furnace filter due soon
triggers:
  - trigger: state
    entity_id: sensor.furnace_filter_progress
    attribute: status
    to: "warning"
actions:
  - action: notify.notify
    data:
      message: >
        Furnace filter due in
        {{ state_attr('sensor.furnace_filter_progress', 'days_remaining') }} days.
```

Say who did it:

```yaml
alias: Furnace filter done
triggers:
  - trigger: state
    entity_id: sensor.furnace_filter_last_scan
    not_from:
      - unknown
      - unavailable
    not_to:
      - unknown
      - unavailable
actions:
  - action: notify.notify
    data:
      message: >
        Furnace filter done by {{ states('sensor.furnace_filter_last_scanned_by') }}.
```

## Upgrading from v1

Back up Home Assistant first.

- Existing reminders carry over. The single tag becomes a one item tag list.
- Last Scan, Days Since Scan and Progress keep their entity IDs and history.
- Last Scanned By, Days Remaining and Overdue are new.
- If you had created `input_datetime.{name}_last_scan` by hand, its value is copied over on the first start. See Old helpers below for cleaning them up.
- If you had no helper, there's no scan to copy. The reminder shows overdue until the next scan or `mark_done`.

## Old helpers

v1 depended on `input_datetime.{name}_last_scan` and `input_text.{name}_last_cleaned_by`. You don't need them anymore. Use `sensor.{name}_last_scan` and `sensor.{name}_last_scanned_by` instead.

On the first start after upgrading, the reminder copies the last scan from the date helper if you have one, so you keep your history. Don't delete the helpers before upgrading, or that value is lost.

Once Last Scan shows the right time, switch any cards or automations over to the sensors and delete the helpers under Settings > Devices & services > Helpers.

If you leave them in place, they mirror the reminder: a scan updates them, and editing the date helper updates the reminder. `{name}` is the reminder name in lowercase with underscores, like `furnace_filter`. The integration never creates or deletes helpers.

## Managing reminders

**Edit tags or interval:** Settings > Devices & services > NFC Reminders, open the reminder and click Configure. The reminder reloads and keeps its history.

**Rename:** the name can't be changed. Delete the reminder and add it again, which clears its history.

**Delete:** Settings > Devices & services > NFC Reminders, open the reminder, then use the three dot menu and Delete. The device, entities and saved data go away. Helpers you made yourself stay.

## Troubleshooting

**A scan does nothing.** Listen for `tag_scanned` in Settings > Tools > Events and make sure it fires. Then compare `tag_id` to the `nfc_tag_ids` attribute on the Overdue sensor. For more detail, turn on debug logging (Settings > Devices & services > NFC Reminders > three dot menu > Enable debug logging). Every scan is logged with the tags it was compared to, and a match logs `scanned for`.

**Last Scan is unknown.** The reminder hasn't been scanned yet.

**Last Scanned By always says NFC Scan.** The scan had no user or device attached. Scans from the Companion app include the user.

**A helper isn't updating.** The entity ID has to match the table above exactly, and an `input_datetime` helper needs both date and time turned on.

## License

MIT. See LICENSE.
