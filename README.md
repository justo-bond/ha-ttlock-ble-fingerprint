# TTLock BLE Fingerprint for Home Assistant

Experimental Home Assistant custom integration for local TTLock BLE fingerprint management.

This repository combines:

- `custom_components/ttlock_ble`: the Home Assistant integration.
- `ttlock-ble`: the patched Python BLE SDK used by the integration.

The integration is based on `roquerodrigo/ha-ttlock-ble` and the SDK is based on
`roquerodrigo/ttlock-ble`.

## What is added

- Add a fingerprint locally over BLE.
- List fingerprints.
- Update fingerprint validity dates.
- Delete one fingerprint.
- Clear all fingerprints.

## Install with HACS

1. HACS -> Integrations -> three-dot menu -> Custom repositories.
2. Add this repository URL:

   `https://github.com/justo-bond/ha-ttlock-ble-fingerprint`

3. Category: Integration.
4. Install `TTLock BLE Fingerprint`.
5. Restart Home Assistant.

## Services

Example:

```yaml
service: ttlock_ble.add_fingerprint
data:
  lock_mac: "AA:BB:CC:DD:EE:FF"
  start_date: "202607071200"
  end_date: "209912312359"
  scan_timeout: 60
```

Dates are lock-local time in `YYYYMMDDHHmm` or `YYMMDDHHmm` format.

Available services:

- `ttlock_ble.add_fingerprint`
- `ttlock_ble.list_fingerprints`
- `ttlock_ble.update_fingerprint`
- `ttlock_ble.delete_fingerprint`
- `ttlock_ble.clear_fingerprints`

## Safety

This is experimental and has not yet been validated on every lock model. Test near
the door and keep a mechanical key or another backup entry method available.

Camera recording is not handled by the TTLock BLE protocol in this integration.
If the lock exposes a separate RTSP/ONVIF/local camera stream, add it to Home
Assistant as a normal camera entity and record it with HA automations.
