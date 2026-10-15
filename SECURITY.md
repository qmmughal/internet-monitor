# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅ Yes    |
| < 1.0   | ❌ No     |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Report privately via
[GitHub Security Advisories](https://github.com/qmmughal/wifi-monitor/security/advisories/new)
with the affected version, steps to reproduce, impact, and a suggested fix if you have one.
We aim to acknowledge reports within a few days. This is a volunteer project, so no fixed
response times are guaranteed. Reporters are credited unless they prefer otherwise.

## Scope and threat model

WiFi Monitor consists of a Python CLI, a local HTTP server (`wifi-monitor serve`) and a
browser dashboard. It reads Wi-Fi information through OS tools and never changes system,
network, firewall, DNS or router settings.

Untrusted inputs include **SSIDs and other broadcast data** (anyone nearby can choose an SSID),
OS command output, and HTTP requests to the local server.

Current protections:

- OS commands are run with argument lists (never a shell), with timeouts and output limits.
  No API or CLI parameter is passed to a command; `ping` only accepts validated IP literals.
- The dashboard escapes all dynamic HTML; the CLI escapes Rich markup and strips control
  characters from SSIDs. CSV exports neutralise spreadsheet formulas.
- `wifi-monitor serve` binds to `127.0.0.1` by default and refuses other addresses unless
  `--allow-remote` is given. It rejects non-loopback `Host` headers (DNS rebinding), sends no
  CORS headers, sets a Content-Security-Policy on the page, blocks path traversal, and only
  exposes read-only data. The single POST endpoint (run diagnostics) requires a custom header
  and an absent or loopback `Origin`, and allows one run at a time.
- No credentials are used or stored.

Known limitations:

- The local API is unauthenticated. Any process running as your user (or on your network, if
  you use `--allow-remote`) can read Wi-Fi details from it.
- The dashboard loads Chart.js and fonts from public CDNs.

Out of scope: attacks requiring prior code execution as the user, physical access, or social
engineering.
