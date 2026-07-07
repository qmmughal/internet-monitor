/**
 * speedtest.js — Speed test module for WiFi Monitor
 * Uses fetch() timing for download simulation and navigator.connection for hints.
 */

'use strict';

const SpeedTest = (() => {
  let _results = [];
  let _running = false;
  let _animFrame = null;

  /** Measure latency using fetch timing */
  async function measureLatency(samples = 5) {
    const times = [];
    for (let i = 0; i < samples; i++) {
      const start = performance.now();
      try {
        await fetch(`https://www.cloudflare.com/cdn-cgi/trace?_=${Date.now()}`, {
          method: 'HEAD',
          mode: 'no-cors',
          cache: 'no-store',
        });
      } catch (_) {
        // Simulate on failure
        await new Promise(r => setTimeout(r, Sim.int(5, 30)));
      }
      times.push(performance.now() - start);
    }
    times.sort((a, b) => a - b);
    const trimmed = times.slice(1, -1); // trim outliers
    return Math.round(trimmed.reduce((a, b) => a + b, 0) / trimmed.length);
  }

  /** Simulate download test with progress callback */
  async function simulateDownload(onProgress) {
    const targetMbps = Sim.float(50, 400, 1);
    const durationMs = 4000;
    const steps = 40;
    const interval = durationMs / steps;

    let current = 0;
    for (let i = 0; i <= steps; i++) {
      await new Promise(r => setTimeout(r, interval));
      // Simulate gradual ramp-up
      const progress = i / steps;
      const noise = Sim.gaussian(0, targetMbps * 0.05);
      current = Math.max(0, targetMbps * Math.min(1, progress * 1.3) + noise);
      onProgress(Math.round(current * 10) / 10);
    }
    return Math.round(targetMbps * 10) / 10;
  }

  /** Simulate upload test */
  async function simulateUpload(onProgress) {
    const targetMbps = Sim.float(20, 150, 1);
    const durationMs = 3000;
    const steps = 30;
    const interval = durationMs / steps;

    let current = 0;
    for (let i = 0; i <= steps; i++) {
      await new Promise(r => setTimeout(r, interval));
      const progress = i / steps;
      const noise = Sim.gaussian(0, targetMbps * 0.05);
      current = Math.max(0, targetMbps * Math.min(1, progress * 1.2) + noise);
      onProgress(Math.round(current * 10) / 10);
    }
    return Math.round(targetMbps * 10) / 10;
  }

  /** Run full speed test */
  async function run(callbacks = {}) {
    if (_running) return;
    _running = true;

    const { onPhase, onProgress, onComplete } = callbacks;

    try {
      // Phase 1: Latency
      onPhase?.('Measuring latency…');
      const ping = await measureLatency();
      const jitter = Sim.int(1, Math.round(ping * 0.2));
      callbacks.onPing?.(ping, jitter);

      // Phase 2: Download
      onPhase?.('Testing download…');
      const download = await simulateDownload(mbps => {
        onProgress?.(mbps, 'download');
        ChartManager.drawSpeedGauge('speed-gauge', mbps);
      });

      // Phase 3: Upload
      onPhase?.('Testing upload…');
      const upload = await simulateUpload(mbps => {
        onProgress?.(mbps, 'upload');
        ChartManager.drawSpeedGauge('speed-gauge', mbps, 200);
      });

      // Done
      const result = { ts: Date.now(), ping, jitter, download, upload };
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

  return {
    run,
    isRunning: () => _running,
    getResults: () => _results,
  };
})();
