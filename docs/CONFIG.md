# Configuration

WiFi Monitor works without any configuration. Optional settings live in `config.json` in the
config directory:

| Platform | Directory |
|---|---|
| Windows | `%APPDATA%\wifi-monitor` |
| Linux / macOS | `~/.config/wifi-monitor` |
| Any | `$WIFI_MONITOR_HOME` overrides the above |

Unknown keys and values of the wrong type are ignored. Defaults:

```json
{
  "collector": {
    "interval_s": 10,
    "latency_every": 3,
    "retention_samples": 8640
  },
  "thresholds": {
    "weak_signal_dbm": -75,
    "signal_drop_db": 10,
    "latency_spike_factor": 3.0,
    "latency_min_ms": 50,
    "disconnects_per_hour": 3,
    "dns_slow_ms": 300
  },
  "ai": {
    "enabled": false,
    "provider": "anthropic",
    "model": "claude-opus-5-5",
    "base_url": null,
    "api_key_env": null,
    "send_identifiers": false,
    "timeout_s": 120
  },
  "mqtt": {
    "host": null,
    "port": 1883,
    "username": null,
    "password_env": "WIFI_MONITOR_MQTT_PASSWORD",
    "topic_prefix": "wifi_monitor",
    "home_assistant_discovery": true,
    "tls": false
  }
}
```

- `collector` — used by `serve`: how often to sample, how often to run the latency probes
  (every N samples) and how many samples to keep **in memory** (8640 ≈ 24 h at 10 s).
- `thresholds` — alert rules (see [ARCHITECTURE.md](ARCHITECTURE.md#alerts-and-anomalies)).
- `ai` — see [AI.md](AI.md). Keys are never stored here; `api_key_env` names an environment variable.
- `mqtt` — see [DISTRIBUTED.md](DISTRIBUTED.md).

Other files in the same directory (all plain JSON, safe to delete):

| File | Contents |
|---|---|
| `known_devices.json` | MAC → friendly name, first/last seen (device discovery) |
| `gateway_macs.json` | Router IP → MAC, to notice a changed router |
| `survey.json` | Signal survey points |
| `hub_tokens.json` | Hub token **hashes** (hub machine only) |
| `oui.txt` | Optional IEEE OUI list you can add for vendor names |

Environment variables: see [`.env.example`](../.env.example).
