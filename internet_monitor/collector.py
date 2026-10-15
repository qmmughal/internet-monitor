"""Background sampling loop used by ``serve`` and ``agent``.

Each cycle reads the Wi-Fi link (cheap OS call). Every ``latency_every``
cycles it also measures router ping (3 probes), one TCP handshake to
1.1.1.1:443 and one DNS lookup — a few hundred bytes of traffic. In demo mode
no network probes run and every sample is marked simulated.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

from . import netinfo, probes
from .history import History, Sample
from .models import SIMULATED
from .traffic import InterfaceSampler


class Collector:
    def __init__(self, provider, history: History, interval_s: float = 10, latency_every: int = 3,
                 demo: bool = False, route_fn=netinfo.default_route, ping_fn=probes.ping,
                 tcp_fn=probes.tcp_latency, dns_fn=probes.resolve, traffic: Optional[InterfaceSampler] = None) -> None:
        self.provider = provider
        self.history = history
        self.interval_s = max(2.0, float(interval_s))
        self.latency_every = max(1, int(latency_every))
        self.demo = demo
        self._route, self._ping, self._tcp, self._dns = route_fn, ping_fn, tcp_fn, dns_fn
        self.traffic = traffic if traffic is not None else (InterfaceSampler() if not demo else None)
        if self.traffic is not None:
            self.traffic.sample()  # baseline reading so the first cycle has a rate
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cycle = 0
        self.listeners: List[Callable[[Sample], None]] = []
        self.last_error: Optional[str] = None

    def measure(self) -> Sample:
        res = self.provider.connected_interface()
        now = time.time()
        if res.ok:
            i = res.data
            s = Sample(ts=now, mode=res.mode, connected=True, ssid=i.ssid, bssid=i.bssid,
                       signal_dbm=i.signal_dbm.value if i.signal_dbm else None,
                       signal_mode=i.signal_dbm.mode if i.signal_dbm else None,
                       channel=i.channel, band=i.band)
        else:
            s = Sample(ts=now, mode=res.mode, connected=False, error=res.error)

        if self.traffic is not None:
            t = self.traffic.sample()
            if t.get("mode") == "live":
                s.iface, s.iface_type = t.get("primary"), t.get("primary_type")
                s.rx_bps, s.tx_bps = t.get("rx_bps"), t.get("tx_bps")

        if not self.demo and self._cycle % self.latency_every == 0:
            route = self._route()
            gw = (route.data or {}).get("gateway") if route.ok else None
            if gw:
                p = self._ping(gw, count=3, timeout_s=1.0)
                if p.sent:
                    s.gateway_ms, s.gateway_loss_pct = p.median_ms, p.loss_pct
            t = self._tcp("1.1.1.1", 443, count=1, timeout_s=2.0)
            s.internet_ms = t.median_ms
            d = self._dns("www.cloudflare.com", timeout_s=3.0)
            s.dns_ms = d.get("ms") if d.get("ok") else None
        self._cycle += 1
        return s

    def tick(self) -> Sample:
        s = self.measure()
        self.history.add(s)
        for fn in list(self.listeners):
            try:
                fn(s)
            except Exception as exc:  # an integration failing must not stop collection
                self.last_error = f"{type(exc).__name__}: {exc}"
        return s

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.tick()
                self.last_error = None
            except Exception as exc:  # keep collecting; surface the error in /api/v1/history/stats
                self.last_error = f"{type(exc).__name__}: {exc}"
            self._stop.wait(max(0.5, self.interval_s - (time.monotonic() - started)))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="internet-monitor-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict:
        return {"running": self.running, "interval_s": self.interval_s, "latency_every": self.latency_every,
                "mode": SIMULATED if self.demo else "live", "last_error": self.last_error}
