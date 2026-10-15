# Privacy

WiFi Monitor is local-first. It has no accounts, no telemetry and no analytics.

## What stays on your machine

- All Wi-Fi measurements (SSIDs, BSSIDs, signal, channels) and network details (gateway, local IP).
- CLI logs — only written when you pass `-o FILE` or answer the export prompt.
- Dashboard history and alerts — stored in your browser's `localStorage` for the dashboard's
  origin; cleared with **History → Clear** / **Alerts → Clear All**.

## What leaves your machine

Nothing is uploaded, but some features make network requests:

| Feature | Destination | What is sent |
|---|---|---|
| `wifi-monitor diagnose` / dashboard Connectivity Check | DNS lookups of `www.google.com`, `www.cloudflare.com`, `www.microsoft.com`; HTTPS GET to `https://www.google.com/generate_204`, `https://cp.cloudflare.com/generate_204`, `https://www.microsoft.com/`; TCP handshakes to `1.1.1.1:443`, `8.8.8.8:443` | Ordinary requests with User-Agent `wifi-monitor-diagnostics`. No measurement data. |
| Router check | ICMP ping / TCP connect to your default gateway | Nothing beyond the probe |
| Dashboard latency test | `https://www.cloudflare.com/cdn-cgi/trace` (HEAD) | Ordinary browser request |
| Dashboard page load | `cdn.jsdelivr.net` (Chart.js), `fonts.googleapis.com` / `fonts.gstatic.com` | Ordinary browser requests (your IP is visible to these CDNs) |

Those providers see that a request came from your IP address, as with any web request.

## The local API

`wifi-monitor serve` listens on `127.0.0.1` only. It returns SSIDs, BSSIDs and your local IP
to pages served from that address. It rejects requests whose `Host` header is not a loopback
name and sends no CORS headers, so other websites you visit cannot read it.

## Future optional features

Planned AI explanations and integrations will be **off by default**, require explicit
configuration, and will document exactly what is sent before anything leaves your machine.
