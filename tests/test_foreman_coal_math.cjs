'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const coalMath = require(path.resolve(__dirname, '..', '高炉前端数据', 'assets', 'foreman-coal-math.js'));

function iso(minute, second = 0) {
  return `2026-08-06T11:${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}+08:00`;
}

// A 40 t/h rate observed every five seconds for one minute must yield
// 40/60 t, not twelve copies of 40/60 t.
{
  const timestamps = [];
  const values = [];
  for (let second = 0; second <= 60; second += 5) {
    timestamps.push(second === 60 ? iso(1, 0) : iso(0, second));
    values.push(40);
  }
  const result = coalMath.integrateRateSeries(
    timestamps,
    values,
    Date.parse(iso(0)),
    Date.parse(iso(1))
  );
  assert.ok(Math.abs(result.amount - 40 / 60) < 1e-9, JSON.stringify(result));
  assert.equal(result.coverageRatio, 1);
}

// 11:00-11:19 at 41.37 t/h is 13.1005 t.
{
  const timestamps = Array.from({ length: 20 }, (_, index) => iso(index));
  const values = timestamps.map(() => 41.37);
  const result = coalMath.integrateRateSeries(
    timestamps,
    values,
    Date.parse(iso(0)),
    Date.parse(iso(19))
  );
  assert.ok(Math.abs(result.amount - 41.37 * 19 / 60) < 1e-9, JSON.stringify(result));
  assert.equal(result.coverageRatio, 1);
}

// A long telemetry gap is not silently filled for the whole missing window.
{
  const result = coalMath.integrateRateSeries(
    [iso(0), iso(10)],
    [40, 40],
    Date.parse(iso(0)),
    Date.parse(iso(10)),
    { maxGapMs: 120000 }
  );
  assert.ok(Math.abs(result.amount - 40 * 2 / 60) < 1e-9, JSON.stringify(result));
  assert.ok(Math.abs(result.coverageRatio - 0.2) < 1e-9, JSON.stringify(result));
}

process.stdout.write(JSON.stringify({ passed: true, semantic: 'timestamp_rate_integral_tph_to_t' }) + '\n');
