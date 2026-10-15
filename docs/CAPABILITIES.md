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

## Wi-Fi generation and channel width

| | Windows | Linux | macOS |
|---|---|---|---|
| Generation (Wi-Fi 4/5/6/6E/7) | ✅ from `Radio type` | ✅ from `iw` bitrate (HT/VHT/HE/EHT) | ✅ from PHY mode |
| Channel width | ❌ | ✅ from `iw` | ✅ |
| Multi-Link Operation (MLO) | ❌ reported as unavailable | ❌ | ❌ |

These describe the current connection as negotiated, not the router's maximum capability.
Wi-Fi 7 is never inferred from an SSID or a 6 GHz frequency.

## Devices on the network

| | Windows | Linux | macOS |
|---|---|---|---|
| Source | `arp -a` | `ip neigh` | `arp -an` |
| Passive (default) | ✅ no packets sent | ✅ | ✅ |
| Active sweep (`--probe`) | ✅ one ping per address of the private /24 | ✅ | ✅ |
| Vendor names | only with an OUI file (e.g. IEEE `oui.txt` in the config dir) | ✅ if `ieee-data`/nmap/wireshark files are installed | ✅ with nmap/wireshark files |

Randomized (private) MAC addresses are flagged; their vendor is unknowable.

## Throughput

`speedtest` downloads from and uploads to `speed.cloudflare.com` over one HTTPS connection,
capped by data budget (default 50 MB) and time. It reports the largest successful transfer.

## Not available

- Non-English Windows `netsh` parsing (reported as unavailable, not guessed).
- MLO and per-link Wi-Fi 7 data.
- Measured RF interference or channel utilisation (channel scores are neighbour counts).
- Persistent history across restarts (by design in this release).
