/**
 * speedtest.js — Latency test for WiFi Monitor
 *
 * Latency/jitter: real HTTP round-trip timings measured by the browser
 * (includes HTTP overhead, so higher than ICMP ping). Failed requests are
 * excluded, never replaced with invented numbers.
 *
 * Download/upload: a real throughput test is not implemented yet. In demo
 * modes an animated SIMULATED result is shown and labelled; with live data
 * these values are reported as not measured.
 */

'use strict';

const SpeedTest = (() => {
  const LATENCY_URL = 'https://www.cloudflare.com/cdn-cgi/trace';
  let _results = [];
  let _running = false;

  /** Measure HTTP round-trip latency. Returns null values when nothing succeeded. */
  async function measureLatency(samples = 6) {
    const times = [];
    let failures = 0;
    for (let i = 0; i < samples; i++) {
      const start = performance.now();
      try {
        await fetch(`${LATENCY_URL}?_=${Date.now()}`, { method: 'HEAD', mode: 'no-cors', cache: 'no-store' });
        if (i > 0) times.push(performance.now() - start); // first request includes TLS setup
      } catch (_) {
        failures++;
      }
    }
    if (times.length < 2) {
      return { ping: null, jitter: null, samples: times.length, failures, error: 'Latency endpoint unreachable' };
    }
    const sorted = [...times].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    let diffSum = 0;
    for (let i = 1; i < times.length; i++) diffSum += Math.abs(times[i] - times[i - 1]);
    return {
      ping: Math.round(median),
      jitter: Math.round(diffSum / (times.length - 1)),
      samples: times.length,
      failures,
      error: null,
    };
  }

  /** SIMULATED throughput animation for demo modes. */
  async function simulateTransfer(onProgress, minMbps, maxMbps, durationMs) {
    const targetMbps = Sim.float(minMbps, maxMbps, 1);
    const steps = Math.round(durationMs / 100);
    for (let i = 0; i <= steps; i++) {
      await new Promise(r => setTimeout(r, 100));
      const noise = Sim.gaussian(0, targetMbps * 0.05);
      onProgress(Math.max(0, Math.round((targetMbps * Math.min(1, (i / steps) * 1.3) + noise) * 10) / 10));
    }
    return Math.round(targetMbps * 10) / 10;
  }

  async function run(callbacks = {}) {
    if (_running) return null;
    _running = true;
    const { onPhase, onProgress, onComplete } = callbacks;
    const simulatedThroughput = DataSource.isSimulated();

    try {
      onPhase?.('Measuring latency…');
      const lat = await measureLatency();
      callbacks.onPing?.(lat);

      let download = null;
      let upload = null;
      if (simulatedThroughput) {
        onPhase?.('Download (simulated)…');
        download = await simulateTransfer(mbps => {
          onProgress?.(mbps, 'download');
          ChartManager.drawSpeedGauge('speed-gauge', mbps);
        }, 50, 400, 4000);
        onPhase?.('Upload (simulated)…');
        upload = await simulateTransfer(mbps => {
          onProgress?.(mbps, 'upload');
          ChartManager.drawSpeedGauge('speed-gauge', mbps, 200);
        }, 20, 150, 3000);
      }

      const result = {
        ts: Date.now(),
        ping: lat.ping,
        jitter: lat.jitter,
        latencyError: lat.error,
        latencyMethod: 'browser HTTP round-trip',
        download,
        upload,
        throughputSimulated: simulatedThroughput,
      };
      _results.push(result);
      onPhase?.('Complete');
      onProgress?.(0, 'idle');
      ChartManager.drawSpeedGauge('speed-gauge', 0);
      onComplete?.(result);
      return result;
    } finally {
      _running = false;
    }
  }

  return { run, isRunning: () => _running, getResults: () => _results };
})();
