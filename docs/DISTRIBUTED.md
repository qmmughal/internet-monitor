# Multi-Machine Monitoring and Integrations

All of this is optional. A single machine needs none of it.

## Prometheus / Grafana (single machine)

`wifi-monitor serve` exposes `http://127.0.0.1:8765/metrics` in Prometheus text format:

| Metric | Meaning |
|---|---|
| `wifi_monitor_connected` | 1 if Wi-Fi is connected (`mode` label: live/simulated/unavailable) |
| `wifi_monitor_signal_dbm` | Signal; `mode="estimated"` when derived from the OS percentage |
| `wifi_monitor_gateway_latency_ms`, `wifi_monitor_gateway_loss_ratio` | Router ping |
| `wifi_monitor_internet_latency_ms` | TCP handshake to 1.1.1.1:443 |
| `wifi_monitor_dns_ms` | System resolver lookup time |
| `wifi_monitor_roams_total`, `wifi_monitor_disconnects_total` | Events since the server started |
| `wifi_monitor_alerts_active` | Unacknowledged alerts |

No SSIDs, BSSIDs or IP addresses are exported. The endpoint is loopback-only like the rest of the
local API; for scraping from another machine use the hub below.

## Hub and agents

```text
 laptop / Raspberry Pi                      monitoring machine
 ┌───────────────────────┐   HTTPS + token   ┌──────────────────────────┐
 │ wifi-monitor agent    │ ────────────────▶ │ wifi-monitor hub serve   │ ◀── Prometheus / curl
 │ (samples every 60 s)  │   POST report     │ per-agent history+alerts │     (viewer token)
 └───────────────────────┘                   └──────────────────────────┘
```

### 1. Create tokens on the hub machine

```bash
wifi-monitor hub token add agents kitchen-pi     # prints the token once
wifi-monitor hub token add viewers grafana
wifi-monitor hub token list
wifi-monitor hub token revoke agents kitchen-pi  # takes effect on the next request
```

Tokens are random 256-bit values; only their SHA-256 hashes are stored (`hub_tokens.json`).

### 2. Run the hub with TLS

```bash
wifi-monitor hub serve --host 0.0.0.0 --port 8766 --tls-cert hub.crt --tls-key hub.key
```

Without TLS the hub refuses to listen on a network address unless you pass `--insecure-http`
(acceptable on an isolated trusted LAN or behind a TLS reverse proxy).

### 3. Run agents

```bash
export WIFI_MONITOR_AGENT_TOKEN=<token from step 1>
wifi-monitor agent --hub https://monitor.lan:8766 --interval 60 [--ca-file hub-ca.pem]
```

Agents omit SSID/BSSID unless `--include-identifiers` is given, queue up to 500 samples while
the hub is unreachable, and refuse plain HTTP to a remote hub without `--insecure-http`.

### 4. Read

```bash
curl -H "Authorization: Bearer $VIEWER_TOKEN" https://monitor.lan:8766/api/v1/agents
```

Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: wifi-monitor
    scheme: https
    authorization: { credentials: <viewer token> }
    static_configs: [{ targets: ["monitor.lan:8766"] }]
```

### Threat model

| Threat | Control |
|---|---|
| Unauthenticated reads or forged reports | Bearer tokens on every endpoint; agent and viewer tokens are separate roles |
| Agent impersonating another agent | Agent identity is the token's registered name, never a client-supplied field |
| Stolen token | `hub token revoke`; tokens stored hashed, shown once |
| Eavesdropping | TLS required off-loopback (or explicit `--insecure-http`) |
| Resource exhaustion | 64 KB request limit, ≤ 50 samples per report, 1 report/s per agent, ≤ 100 agents, bounded history |
| Replay of old reports | Samples not newer than the agent's last sample are ignored; timestamps > 1 day off are rejected |
| Privacy | Identifiers omitted by default; hub keeps data in memory only |

Limitations: no mTLS, no token expiry, hub state is lost on restart.

## MQTT and Home Assistant

```bash
pip install "wifi-monitor[mqtt]"
export WIFI_MONITOR_MQTT_PASSWORD=...
```

`config.json`:

```json
{ "mqtt": { "host": "homeassistant.local", "port": 1883, "username": "wifi",
            "topic_prefix": "wifi_monitor", "home_assistant_discovery": true, "tls": false } }
```

```bash
wifi-monitor serve --mqtt
```

Every sample is published as JSON to `wifi_monitor/<hostname>/state`. With discovery enabled,
Home Assistant creates sensors for signal, router latency, internet latency, DNS time, packet
loss and a "Wi-Fi connected" binary sensor. SSIDs/BSSIDs are not published.
