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

/* ── Inline implementations for testing (no DOM required) ─────── */

function dbmToPercent(dbm) {
  if (dbm >= -50) return 100;
  if (dbm <= -100) return 0;
  return Math.round(((dbm + 100) / 50) * 100);
}

function qualityLabel(dbm) {
  if (dbm >= -50) return 'Excellent';
  if (dbm >= -60) return 'Good';
  if (dbm >= -70) return 'Fair';
  return 'Poor';
}

function qualityClass(dbm) {
  if (dbm >= -50) return 'excellent';
  if (dbm >= -60) return 'good';
  if (dbm >= -70) return 'fair';
  return 'poor';
}

function channelBand(ch) {
  if (ch >= 1 && ch <= 14) return '2.4 GHz';
  if (ch >= 36 && ch <= 177) return '5 GHz';
  return 'Unknown';
}

function arrayToCSV(headers, rows) {
  const header = headers.join(',');
  const body = rows.map(r => r.map(c => `"${c}"`).join(',')).join('\n');
  return `${header}\n${body}`;
}

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
