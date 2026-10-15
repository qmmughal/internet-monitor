/**
 * unit.test.js — Unit tests for WiFi Monitor utility functions
 * 
 * Run with: node tests/unit.test.js
 * Or: npm test
 */

'use strict';

let passed = 0;
let failed = 0;
const errors = [];

/* ── Minimal test framework ─────────────────────────────────────── */
function test(name, fn) {
  try {
    fn();
    console.log(`  ✅ ${name}`);
    passed++;
  } catch (err) {
    console.log(`  ❌ ${name}`);
    console.log(`     ${err.message}`);
    failed++;
    errors.push({ name, error: err.message });
  }
}

function expect(val) {
  return {
    toBe: (expected) => {
      if (val !== expected) {
        throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(val)}`);
      }
    },
    toBeCloseTo: (expected, tolerance = 2) => {
      if (Math.abs(val - expected) > tolerance) {
        throw new Error(`Expected ${expected} ± ${tolerance}, got ${val}`);
      }
    },
    toBeGreaterThan: (n) => {
      if (val <= n) throw new Error(`Expected ${val} > ${n}`);
    },
    toBeLessThan: (n) => {
      if (val >= n) throw new Error(`Expected ${val} < ${n}`);
    },
    toBeGreaterThanOrEqual: (n) => {
      if (val < n) throw new Error(`Expected ${val} >= ${n}`);
    },
    toBeLessThanOrEqual: (n) => {
      if (val > n) throw new Error(`Expected ${val} <= ${n}`);
    },
    toBeTruthy: () => {
      if (!val) throw new Error(`Expected truthy, got ${val}`);
    },
    toBeFalsy: () => {
      if (val) throw new Error(`Expected falsy, got ${val}`);
    },
    toMatch: (regex) => {
      if (!regex.test(val)) throw new Error(`Expected ${val} to match ${regex}`);
    },
    toEqual: (expected) => {
      const a = JSON.stringify(val), b = JSON.stringify(expected);
      if (a !== b) throw new Error(`Expected ${b}, got ${a}`);
    },
  };
}

/* ── Load the shipped browser modules (no DOM required) ────────── */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const { SignalUtils, escapeHTML, arrayToCSV } = require('../src/js/utils.js');
const { dbmToPercent, qualityLabel, qualityClass, channelBand } = SignalUtils;

/** Load browser scripts into one sandbox and return the named globals. */
function loadBrowserModules(files, names, extraGlobals = {}) {
  const ctx = vm.createContext({ console, setTimeout, clearTimeout, ...extraGlobals });
  for (const f of files) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'src', 'js', f), 'utf8'), ctx, { filename: f });
  }
  return vm.runInContext(`({ ${names.join(', ')} })`, ctx);
}

/* ═══════════════════════════════════════════════════════════════
   TEST SUITES
   ═══════════════════════════════════════════════════════════════ */

console.log('\n📡 WiFi Monitor — Unit Tests\n');

/* ── dbmToPercent ────────────────────────────────────────────── */
console.log('SignalUtils.dbmToPercent');
test('returns 100 at -50 dBm (excellent)', () => expect(dbmToPercent(-50)).toBe(100));
test('returns 100 for values above -50', () => expect(dbmToPercent(-30)).toBe(100));
test('returns 0 at -100 dBm (no signal)', () => expect(dbmToPercent(-100)).toBe(0));
test('returns 0 for values below -100', () => expect(dbmToPercent(-110)).toBe(0));
test('returns 50 at -75 dBm (midpoint)', () => expect(dbmToPercent(-75)).toBe(50));
test('returns 80 at -60 dBm', () => expect(dbmToPercent(-60)).toBe(80));
test('returns 40 at -80 dBm', () => expect(dbmToPercent(-80)).toBe(40));
test('returns an integer', () => expect(Number.isInteger(dbmToPercent(-65))).toBe(true));

/* ── qualityLabel ────────────────────────────────────────────── */
console.log('\nSignalUtils.qualityLabel');
test('returns Excellent at -45 dBm', () => expect(qualityLabel(-45)).toBe('Excellent'));
test('returns Good at -55 dBm', () => expect(qualityLabel(-55)).toBe('Good'));
test('returns Fair at -65 dBm', () => expect(qualityLabel(-65)).toBe('Fair'));
test('returns Poor at -80 dBm', () => expect(qualityLabel(-80)).toBe('Poor'));
test('boundary: -60 returns Good', () => expect(qualityLabel(-60)).toBe('Good'));
test('boundary: -70 returns Fair', () => expect(qualityLabel(-70)).toBe('Fair'));

/* ── qualityClass ────────────────────────────────────────────── */
console.log('\nSignalUtils.qualityClass');
test('returns excellent at -50', () => expect(qualityClass(-50)).toBe('excellent'));
test('returns good at -59', () => expect(qualityClass(-59)).toBe('good'));
test('returns fair at -69', () => expect(qualityClass(-69)).toBe('fair'));
test('returns poor at -71', () => expect(qualityClass(-71)).toBe('poor'));

/* ── channelBand ─────────────────────────────────────────────── */
console.log('\nSignalUtils.channelBand');
test('ch 1 is 2.4 GHz', () => expect(channelBand(1)).toBe('2.4 GHz'));
test('ch 6 is 2.4 GHz', () => expect(channelBand(6)).toBe('2.4 GHz'));
test('ch 11 is 2.4 GHz', () => expect(channelBand(11)).toBe('2.4 GHz'));
test('ch 36 is 5 GHz', () => expect(channelBand(36)).toBe('5 GHz'));
test('ch 149 is 5 GHz', () => expect(channelBand(149)).toBe('5 GHz'));

/* ── arrayToCSV ──────────────────────────────────────────────── */
console.log('\nArrayToCSV');
test('produces correct CSV header', () => {
  const csv = arrayToCSV(['A', 'B'], [['1', '2']]);
  expect(csv.split('\n')[0]).toBe('A,B');
});
test('quotes values in rows', () => {
  const csv = arrayToCSV(['X'], [['hello']]);
  expect(csv.split('\n')[1]).toBe('"hello"');
});
test('handles multiple rows', () => {
  const csv = arrayToCSV(['A', 'B'], [['1', '2'], ['3', '4']]);
  const lines = csv.trim().split('\n');
  expect(lines.length).toBe(3);
});

/* ── Monotonicity and boundary checks ────────────────────────── */
console.log('\nMonotonicity / Boundary');
test('percent increases as dBm increases', () => {
  const vals = [-100, -80, -70, -60, -50];
  const percents = vals.map(dbmToPercent);
  for (let i = 1; i < percents.length; i++) {
    if (percents[i] < percents[i-1]) {
      throw new Error(`Percent not monotonic at index ${i}`);
    }
  }
});
test('percent is always 0–100', () => {
  for (let dbm = -110; dbm <= -20; dbm++) {
    const p = dbmToPercent(dbm);
    if (p < 0 || p > 100) {
      throw new Error(`Out of range at ${dbm}: ${p}`);
    }
  }
});


/* ── Frequency maths (regression: 5 GHz used to be wrong) ─────── */
console.log('\nSignalUtils.channelToMHz / channelToFreq');
test('ch 1 is 2412 MHz', () => expect(SignalUtils.channelToMHz(1)).toBe(2412));
test('ch 14 is 2484 MHz', () => expect(SignalUtils.channelToMHz(14)).toBe(2484));
test('ch 36 is 5180 MHz', () => expect(SignalUtils.channelToMHz(36)).toBe(5180));
test('ch 149 is 5745 MHz', () => expect(SignalUtils.channelToMHz(149)).toBe(5745));
test('6 GHz ch 37 is 6135 MHz', () => expect(SignalUtils.channelToMHz(37, '6 GHz')).toBe(6135));
test('label for ch 36', () => expect(SignalUtils.channelToFreq(36)).toBe('5.180 GHz'));
test('channel 181 alone is ambiguous', () => expect(channelBand(181)).toBe(null));

/* ── HTML escaping ───────────────────────────────────────────── */
console.log('\nescapeHTML');
test('escapes tags and quotes', () =>
  expect(escapeHTML(`<img src=x onerror="a">'`)).toBe('&lt;img src=x onerror=&quot;a&quot;&gt;&#39;'));
test('null becomes empty string', () => expect(escapeHTML(null)).toBe(''));
test('numbers are stringified', () => expect(escapeHTML(-60)).toBe('-60'));

/* ── CSV safety ──────────────────────────────────────────────── */
console.log('\narrayToCSV safety');
const csvRow = cells => arrayToCSV(['X'], [cells]).split('\n')[1];
test('doubles embedded quotes', () => expect(csvRow(['a"b'])).toBe('"a""b"'));
test('neutralises formula injection', () => expect(csvRow(['=HYPERLINK("x")'])).toBe(`"'=HYPERLINK(""x"")"`));
test('keeps negative numbers intact', () => expect(csvRow([-60])).toBe('"-60"'));

/* ── Scanner rendering (XSS regression with attacker-controlled SSIDs) ── */
console.log('\nNetworkScanner.renderNetworkRow');
const { NetworkScanner } = loadBrowserModules(['utils.js', 'scanner.js'], ['NetworkScanner'], {
  DataSource: { usesApi: () => true },
  document: { getElementById: () => null },
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
});
const evil = '<img src=x onerror=alert(1)>';
const row = NetworkScanner.renderNetworkRow({
  ssid: evil, bssid: '02:00:00:00:00:01', channel: 6, band: '2.4 GHz', security: '<b>WPA2</b>',
  signal: -60, signalMode: 'estimated', quality: 80, connected: false,
});
test('SSID is escaped', () => expect(row.includes(evil)).toBe(false));
test('escaped SSID is present', () => expect(row.includes('&lt;img src=x onerror=alert(1)&gt;')).toBe(true));
test('security text is escaped', () => expect(row.includes('<b>WPA2</b>')).toBe(false));
test('estimated signal is marked', () => expect(row.includes('≈')).toBe(true));
const hiddenRow = NetworkScanner.renderNetworkRow({ ssid: null, bssid: null, channel: null, band: null, signal: null, quality: null });
test('hidden SSID and missing signal render placeholders', () => {
  expect(hiddenRow.includes('&lt;hidden&gt;')).toBe(true);
  expect(hiddenRow.includes('null')).toBe(false);
});

/* ── Live features: AI/rule-based answers are escaped ───────────── */
console.log('\nLiveFeatures.renderAnswer');
const { LiveFeatures } = loadBrowserModules(['utils.js', 'api.js', 'live.js'], ['LiveFeatures'], {
  document: { getElementById: () => null },
  location: { protocol: 'file:' },
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
});
const answerHtml = LiveFeatures.renderAnswer({
  source: 'ai', provider: '<i>p</i>', model: 'm',
  answer: {
    summary: '<script>alert(1)</script>',
    observations: [{ fact: '<b>x</b>', evidence: 'y' }],
    hypotheses: [{ cause: 'c', confidence: 'low', evidence: 'e' }],
    recommendations: [{ action: '<img src=x onerror=alert(2)>', why: 'w', risk: 'low' }],
    limitations: ['<u>l</u>'],
  },
});
test('summary script tag is escaped', () => expect(answerHtml.includes('<script>')).toBe(false));
test('recommendation markup is escaped', () => expect(answerHtml.includes('<img')).toBe(false));
test('provider name is escaped', () => expect(answerHtml.includes('<i>p</i>')).toBe(false));
test('recommendations are labelled as not applied', () => expect(answerHtml.includes('not applied automatically')).toBe(true));
test('features are off without the API', () => expect(LiveFeatures.enabled()).toBe(false));

/* ═══════════════════════════════════════════════════════════════
   SUMMARY
   ═══════════════════════════════════════════════════════════════ */
console.log(`\n${'─'.repeat(50)}`);
console.log(`📊 Results: ${passed} passed, ${failed} failed\n`);
if (failed > 0) {
  console.log('❌ Failed tests:');
  errors.forEach(e => console.log(`   · ${e.name}: ${e.error}`));
  process.exit(1);
} else {
  console.log('🎉 All tests passed!\n');
}
