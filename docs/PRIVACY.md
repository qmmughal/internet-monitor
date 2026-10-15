# Privacy

Internet Monitor is local-first. It has no accounts, no telemetry and no analytics.

## What stays on your machine

- All Wi-Fi measurements (SSIDs, BSSIDs, signal, channels) and network details (gateway, local IP).
- History and alerts collected by `serve` — **in memory only**, gone when it stops; clear earlier
  with **History → Clear** or `POST /api/v1/history/clear`.
- CLI logs — only written when you pass `-o FILE`, `history --export`, or answer the export prompt.
- Browser-demo history — stored in your browser's `localStorage`; cleared with **History → Clear**.
- Per-app usage and open connections (app names, remote IP addresses) — read from the OS on demand,
  shown locally, never stored by Internet Monitor.
- Small JSON files in the config directory: known devices and names, router MAC, survey points,
  hub token hashes ([CONFIG.md](CONFIG.md)). Delete them at any time.

## What leaves your machine

Nothing is uploaded, but some features make network requests:

| Feature | Destination | What is sent |
|---|---|---|
| `internet-monitor diagnose` / dashboard Connectivity Check | DNS lookups of `www.google.com`, `www.cloudflare.com`, `www.microsoft.com`; HTTPS GET to `https://www.google.com/generate_204`, `https://cp.cloudflare.com/generate_204`, `https://www.microsoft.com/`; TCP handshakes to `1.1.1.1:443`, `8.8.8.8:443` | Ordinary requests with User-Agent `internet-monitor-diagnostics`. No measurement data. |
| Router check | ICMP ping / TCP connect to your default gateway | Nothing beyond the probe |
| `serve` background collector (every 3rd sample, default every 30 s) | ping to your router, one TCP handshake to `1.1.1.1:443`, one DNS lookup of `www.cloudflare.com` | A few hundred bytes; no measurement data. Disable with `serve --no-collect` |
| `speedtest` | `speed.cloudflare.com` | Download/upload of zero-filled data, up to the `--max-mb` budget (default 50 MB) |
| `devices --probe` (opt-in) | One ping to each address of your local private /24 | Nothing beyond the probe; never leaves your LAN |
| AI explanations (off by default) | The provider you configure (Anthropic API, or your OpenAI-compatible/local server) | A summary of measurements with SSIDs, MACs, device names and private IPs **redacted** by default; includes current upload/download rates and the names of the 5 busiest apps (no remote addresses). Preview with `ask --preview` |
| `connections --resolve` (opt-in) | Your DNS resolver | Reverse-DNS (PTR) queries for the remote IPs shown |
| Agents (opt-in) | Your own hub | Samples without SSID/BSSID unless `--include-identifiers` |
| MQTT (opt-in) | Your broker | Metrics only; no SSID/BSSID |
| Dashboard latency test | `https://www.cloudflare.com/cdn-cgi/trace` (HEAD) | Ordinary browser request |
| Dashboard page load | `cdn.jsdelivr.net` (Chart.js), `fonts.googleapis.com` / `fonts.gstatic.com` | Ordinary browser requests (your IP is visible to these CDNs) |

Those providers see that a request came from your IP address, as with any web request.

## The local API

`internet-monitor serve` listens on `127.0.0.1` only. It returns SSIDs, BSSIDs and your local IP
to pages served from that address. It rejects requests whose `Host` header is not a loopback
name and sends no CORS headers, so other websites you visit cannot read it.

## Optional features

AI explanations, the hub/agents and MQTT are **off by default** and need explicit configuration.
See [AI.md](AI.md) and [DISTRIBUTED.md](DISTRIBUTED.md) for exactly what each one sends.
