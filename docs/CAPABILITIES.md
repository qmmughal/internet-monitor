# Capability Matrix

What WiFi Monitor can measure on each platform, where the data comes from, and
how it is labelled. Run `wifi-monitor capabilities` to see what your system reports.

## Provenance labels

| Label | Meaning | Example |
|---|---|---|
| `live` | Read directly from the OS in native units | Linux `iw` signal −57 dBm |
| `estimated` | Derived from a real observation | dBm computed from Windows' 0–100 % signal |
| `simulated` | Generated for demos/tests; only with `--demo` or browser demo mode | Demo access points |
| `unavailable` | Could not be obtained; `error` and often `hint` explain why | No Wi-Fi adapter |

The percentage→dBm estimate uses `dBm ≈ % / 2 − 100`, the linear mapping Windows and
NetworkManager use. Vendors deviate from it, so estimated values carry `confidence: low`.

## Wi-Fi link

| Metric | Windows (`netsh wlan show interfaces`) | Linux (`nmcli`, `iw`) | macOS (`system_profiler`) |
|---|---|---|---|
| Interface state | ✅ | ✅ | ✅ |
| SSID | ✅ | ✅ | ⚠️ `<redacted>` without Location permission → reported as unknown |
| BSSID | ✅ | ✅ | ❌ (only legacy `airport`, removed in 14.4) |
| Signal dBm | `live` from `Rssi` (newer builds) else `estimated` | `live` via `iw` else `estimated` | `live` |
| Signal % | ✅ | ✅ | ❌ |
| Noise floor | ❌ | ❌ | ✅ |
| Channel / band / frequency | ✅ (frequency derived) | ✅ | ✅ (frequency derived) |
| Radio type (802.11ax…) | ✅ | ❌ | ✅ |
| Security | ✅ | ✅ | ✅ |
| Link rate (negotiated, **not** throughput) | ✅ rx/tx | ✅ rx/tx with `iw` | tx only |

## Access point list

| | Windows | Linux | macOS |
|---|---|---|---|
| Source | `netsh wlan show networks mode=bssid` | `nmcli device wifi list --rescan auto` | `system_profiler SPAirPortDataType` |
| Fresh scan? | No — Windows' cached list (≤ ~1 min old) | May trigger a rescan (up to ~15 s) | Cached; 2–10 s to run |
| BSSID | ✅ | ✅ | ❌ |
| Signal | `estimated` from % | `estimated` from % | `live` |
| Hidden networks | shown as `<hidden>` | shown as `<hidden>` | shown as `<hidden>` |

Channel counts in the dashboard are **counts of access points**, not measured RF
utilization or interference.

## Network and diagnostics (all platforms)

| Check | Method | Notes |
|---|---|---|
| Default gateway | Windows `route print` (numeric rows only, locale-independent); Linux `/proc/net/route`; macOS `route get default` | IPv4 only |
| Local IP | UDP socket source-address lookup (no packets sent) | |
| Router reachability | ICMP `ping` (4 probes), then TCP 53/80/443 | A refused TCP connection counts as reachable. Many routers ignore ping; that alone is not reported as a problem |
| Packet loss | ICMP to the router only | With 4 probes one loss = 25 %; confidence is reported as medium |
| DNS | System resolver, 3 hostnames, bounded timeout | May be answered from cache |
| HTTPS | 3 endpoints, redirects not followed | A redirect from a `generate_204` endpoint suggests a captive portal |
| Internet latency / jitter | TCP handshake to `1.1.1.1:443` and `8.8.8.8:443`, 5 samples each | Independent of DNS; not ICMP |
| Windows `ping` `time<1ms` | Recorded as 1.0 ms (upper bound) | |

## Permissions

| Platform | Requirement |
|---|---|
| Windows 11 24H2+ | Settings → Privacy & security → Location → on, and *Let desktop apps access your location*. Without it `netsh wlan` refuses and WiFi Monitor reports the hint. |
| Windows (any) | `netsh` output must be English to be parsed. Other locales are reported as unavailable rather than guessed. |
| Linux | NetworkManager running. `iw` (package `iw`) for live dBm. No root required. |
| macOS 14+ | Location permission for the terminal app to see SSIDs. |

No feature requires administrator/root rights.

## Not yet available

- Real download/upload throughput measurement.
- LAN device discovery (ARP / neighbour table).
- Wi-Fi 6E/7 capability detection, MLO, channel width (only the band/channel is reported).
- Non-English Windows parsing.
