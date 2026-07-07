# WiFi Monitor — Architecture Guide

## Overview

WiFi Monitor follows a **zero-build, vanilla JS modular architecture**. The dashboard runs directly from `src/index.html` with no bundler required. Each module is a self-contained IIFE (Immediately Invoked Function Expression) that exposes a public API object.

## Module Dependency Graph

```
app.js (main controller)
├── utils.js          ← shared utilities (no deps)
│   ├── SignalUtils   ← signal math helpers
│   ├── Sim           ← simulation data generators
│   ├── Toast         ← notification system
│   └── EventBus      ← publish/subscribe
├── charts.js         ← visualization layer
│   └── depends on: Chart.js (CDN)
├── scanner.js        ← network scanning engine
│   └── depends on: SignalUtils, Sim, EventBus
├── devices.js        ← device discovery
│   └── depends on: Sim, EventBus
├── speedtest.js      ← speed measurement
│   └── depends on: Sim, ChartManager
└── logger.js         ← history, alerts, export
    └── depends on: SignalUtils, Toast, EventBus, ChartManager
```

## Module API Reference

### `SignalUtils`

| Method | Signature | Returns |
|--------|-----------|---------|
| `dbmToPercent` | `(dbm: number) → number` | 0–100% quality |
| `qualityLabel` | `(dbm: number) → string` | Excellent/Good/Fair/Poor |
| `qualityClass` | `(dbm: number) → string` | CSS class suffix |
| `qualityColor` | `(dbm: number) → string` | CSS color var value |
| `channelToFreq` | `(ch: number) → string` | "2.412 GHz" |
| `channelBand` | `(ch: number) → string` | "2.4 GHz" / "5 GHz" / "6 GHz" |

### `NetworkScanner`

| Method | Signature | Returns |
|--------|-----------|---------|
| `scan` | `() → Promise<Network[]>` | List of nearby networks |
| `getCurrentNetwork` | `() → Network` | Connected network object |
| `getLiveSignal` | `() → number` | Simulated live RSSI |
| `renderNetworkRow` | `(net: Network) → string` | HTML table row |
| `renderChannelMap` | `(currentCh: number) → void` | Renders channel heatmap |

### `DeviceDiscovery`

| Method | Signature | Returns |
|--------|-----------|---------|
| `discover` | `() → Promise<Device[]>` | List of discovered devices |
| `renderDevices` | `(devices, filter?) → void` | Renders device grid |
| `getDevices` | `() → Device[]` | Current device list |

### `SpeedTest`

| Method | Signature | Returns |
|--------|-----------|---------|
| `run` | `(callbacks) → Promise<Result>` | Speed test result |
| `isRunning` | `() → boolean` | Test in progress |
| `getResults` | `() → Result[]` | Historical results |

### `Logger`

| Method | Signature | Returns |
|--------|-----------|---------|
| `logSignal` | `(net, signal) → Entry` | New history entry |
| `checkAlerts` | `(signal, net, latency?) → void` | Triggers alerts |
| `exportCSV` | `() → void` | Downloads CSV file |
| `exportJSON` | `() → void` | Downloads JSON file |
| `setRule` | `(key, enabled, threshold?) → void` | Configure alert rule |

### `EventBus`

| Event | Payload | Emitted By |
|-------|---------|------------|
| `newDevice` | `{ name, ip, mac }` | DeviceDiscovery |
| `alert` | `AlertObject` | Logger |

---

## Replacing Simulation with Native APIs

The browser simulation layer is designed to be swapped out with native data sources. 

### Node.js / Electron

```javascript
// Replace scanner.js simulation with node-wifi
const wifi = require('node-wifi');
wifi.init({ iface: null });

async function scan() {
  return wifi.scan();
}
async function getCurrentNetwork() {
  const connections = await wifi.getCurrentConnections();
  return connections[0];
}
```

### Python FastAPI Backend

```python
# backend.py
import subprocess
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/signal")
def get_signal():
    # Linux
    result = subprocess.run(
        ["nmcli", "-t", "-f", "SIGNAL,ACTIVE", "dev", "wifi"],
        capture_output=True, text=True
    )
    # Parse and return
    return {"dbm": -65, "ssid": "MyNetwork"}
```

Then in `scanner.js`, replace `_generateNetworks()` with:
```javascript
const res = await fetch('http://localhost:8000/api/signal');
return res.json();
```

---

## Design Decisions

### No Build Step
The dashboard uses native ES modules loaded via `<script>` tags. This ensures:
- Zero toolchain complexity for contributors
- Works offline with just a file open
- No webpack/vite configuration maintenance

### IIFE Module Pattern
Each module uses an IIFE (not ES modules) for maximum browser compatibility without a bundler:

```javascript
const MyModule = (() => {
  // private state
  let _private = 0;
  
  function publicMethod() { return ++_private; }
  
  // expose only public API
  return { publicMethod };
})();
```

### Simulation-First Architecture
The simulation layer allows:
- Full feature demos without native hardware
- Offline development and testing
- CI/CD testing without WiFi access
- Progressive enhancement to native APIs
