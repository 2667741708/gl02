/*
 * Timestamp-aware coal-rate integration for the foreman trend page.
 *
 * PCI_rate is expressed in t/h.  The 8770 stream can update every few
 * seconds while the 8768 history normally updates once per minute, so a
 * sample-count based sum would overstate the amount whenever second-level
 * values are present.  This helper integrates each rate over its real time
 * span and refuses to fill an unobserved gap indefinitely.
 */
(function exposeForemanCoalMath(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.BF_FOREMAN_COAL_MATH = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function createForemanCoalMath() {
  'use strict';

  const DEFAULT_MAX_GAP_MS = 150000;

  function finite(value) {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function integrateRateSeries(timestamps, values, startMs, endMs, options = {}) {
    const start = Number(startMs);
    const end = Number(endMs);
    const maxGapMs = Math.max(1000, finite(options.maxGapMs) || DEFAULT_MAX_GAP_MS);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      return { amount: null, coveredMs: 0, coverageRatio: 0, sampleCount: 0 };
    }

    const samplesByTime = new Map();
    const count = Math.min(Array.isArray(timestamps) ? timestamps.length : 0, Array.isArray(values) ? values.length : 0);
    for (let index = 0; index < count; index += 1) {
      const timestampMs = new Date(timestamps[index]).getTime();
      const rate = finite(values[index]);
      if (!Number.isFinite(timestampMs) || rate === null || timestampMs > end || timestampMs < start - maxGapMs) continue;
      samplesByTime.set(timestampMs, rate);
    }
    const samples = [...samplesByTime.entries()]
      .map(([timestampMs, rate]) => ({ timestampMs, rate }))
      .sort((left, right) => left.timestampMs - right.timestampMs);

    let activeRate = null;
    let cursorMs = start;
    let amount = 0;
    let coveredMs = 0;
    for (const sample of samples) {
      if (sample.timestampMs <= start) {
        activeRate = sample.rate;
        continue;
      }
      if (sample.timestampMs >= end) break;
      if (activeRate !== null) {
        const durationMs = Math.max(0, sample.timestampMs - cursorMs);
        const usableMs = Math.min(durationMs, maxGapMs);
        amount += activeRate * usableMs / 3600000;
        coveredMs += usableMs;
      }
      cursorMs = sample.timestampMs;
      activeRate = sample.rate;
    }

    if (activeRate !== null && cursorMs < end) {
      const usableMs = Math.min(end - cursorMs, maxGapMs);
      amount += activeRate * usableMs / 3600000;
      coveredMs += usableMs;
    }

    const windowMs = end - start;
    return {
      amount: coveredMs > 0 ? amount : null,
      coveredMs,
      coverageRatio: Math.min(1, coveredMs / windowMs),
      sampleCount: samples.length
    };
  }

  return Object.freeze({ DEFAULT_MAX_GAP_MS, integrateRateSeries });
});
