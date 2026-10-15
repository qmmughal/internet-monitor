# Troubleshooting Internet Monitor

## "running scripts is disabled on this system" (Windows PowerShell)

`.\.venv\Scripts\Activate.ps1` is blocked by the execution policy. Run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

or use the environment without activating: `.\.venv\Scripts\internet-monitor serve`.

## "internet-monitor is not recognized" / "command not found"

The virtual environment is not active in this terminal. `cd` into the project folder and run
`.\.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (Linux/macOS). To use
it from anywhere, see "Run it from any folder" in [INSTALLATION.md](INSTALLATION.md).

## `serve` fails because the port is in use

Another program (or a second `serve`) uses port 8765. Stop it, or pick another port:
`internet-monitor serve --port 8770` and open `http://127.0.0.1:8770`.

## "no Wi-Fi interface found on this computer"

The OS reports no wireless adapter. Common on desktops using Ethernet. Diagnostics still
work over any connection; only Wi-Fi-specific fields are unavailable.

## "location permission denied" (Windows)

Windows 11 24H2+ blocks `netsh wlan` without Location access. Open **Settings → Privacy &
security → Location**, enable *Location services* and *Let desktop apps access your
location*, then retry.

## "Wi-Fi adapter … is not working" (Windows)

Windows has stopped the adapter because of a device or driver problem (shown with the Device
Manager code). Open **Device Manager › Network adapters**, check the device, try updating or
reinstalling the driver, or restart. Everything except Wi-Fi-specific readings keeps working over
other connections (e.g. Ethernet).

## Per-app list is empty or misses the last minute

On Windows the per-app numbers come from the system's usage records, which are updated about every
30–60 seconds. Wait a minute and refresh. On Linux, only TCP traffic of your own processes is
attributed unless you run as root. "psutil is not installed" means run `pip install psutil`.

## "unrecognised netsh output" (Windows)

`netsh` labels are translated on non-English Windows and Internet Monitor only parses English
labels, so it reports the data as unavailable rather than guessing. Workarounds: use an
English display language for your account, or contribute a sample of
`netsh wlan show interfaces` from your locale (remove the SSID/MAC addresses first).

## "the WLAN AutoConfig service is not running" (Windows)

Start **WLAN AutoConfig** in `services.msc` (or `sc start wlansvc` from an admin prompt).

## "'nmcli' is not installed" (Linux)

Internet Monitor needs NetworkManager. Systems using `iwd`, `wpa_supplicant` alone or
`systemd-networkd` are not supported yet. Install `network-manager`, or open an issue.

## The scan lists only my own network (Windows)

Some adapters, notably USB Wi-Fi dongles, do not scan in the background while connected, so
Windows' saved list goes stale. Internet Monitor asks Windows for a fresh scan first; if the list is
still short, wait a few seconds and run `internet-monitor scan` again.

## Signal is "estimated"

The OS only reported a 0–100 % quality value. Install `iw` on Linux for a real dBm reading;
on Windows the `Rssi` field is only printed by newer builds.

## SSID shows "—" or "Name hidden by OS" (macOS)

macOS hides SSIDs from apps without Location permission. Grant it to your terminal app in
**System Settings → Privacy & Security → Location Services**.

## Dashboard says "Demo mode"

The page could not reach the local API. Start `internet-monitor serve` and open the URL it
prints (`http://127.0.0.1:8765`). Opening `index.html` from disk is always demo mode.

## Dashboard: "Local API unreachable"

The `serve` process stopped. Restart it; the page recovers on the next poll.

## `serve` refuses to start: "Refusing to bind"

You passed a non-loopback `--host`. The API has no authentication, so this requires
`--allow-remote` and should only be used on a trusted network.

## Diagnostics say the router does not answer ping

Many routers drop ICMP. When the internet is reachable this is reported as information,
not a problem.

## Diagnostics take long

Each probe has a timeout (default 2 s; change with `--timeout`). A full run normally takes
5–15 s and is bounded even when everything times out.

## `history` / `alerts`: "Could not reach the Internet Monitor server"

History and alerts are collected by a running `internet-monitor serve`; start it first. They are kept
in memory, so they start empty after each restart.

## Device list is short

Without `--probe` only devices this computer has recently talked to appear (the OS neighbour
table). `internet-monitor devices --probe` pings the local /24 first — only on networks you own or are
authorised to scan. Phones with private MAC addresses may appear as new after reconnecting.

## Vendor shows "—"

No OUI database was found. Download the IEEE list (`oui.txt`) and place it in the config
directory ([CONFIG.md](CONFIG.md)).

## Speed test results look low

The test uses one connection to the nearest Cloudflare edge and the whole path (Wi-Fi, router,
ISP). Pause other downloads, and try a larger budget: `internet-monitor speedtest --max-mb 200`.

## `ask` says "AI is disabled" or "AI unavailable"

That is the rule-based answer. To enable AI see [AI.md](AI.md). "AI unavailable" includes the
reason (missing key, provider unreachable, invalid answer) — the rule-based answer is shown instead.

## Hub returns 401

The token is missing, wrong, revoked, or of the wrong role (agent tokens can only report; viewer
tokens can only read). Check `internet-monitor hub token list`.

## MQTT: "MQTT disabled"

`serve --mqtt` needs `pip install "internet-monitor[mqtt]"` and `mqtt.host` in `config.json`.
