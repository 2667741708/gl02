/**
 * REQ-8093-FRONTEND-PERF-R1: one visibility-aware timer for periodic runtime
 * work. Animation-frame rendering remains owned by the 3D viewer because it
 * has different latency and lifecycle requirements.
 */

const TICK_MS = 100;
const tasks = new Map();
let timer = 0;

function report(error, key) {
  console.error(`shared runtime task failed: ${key}`, error);
}

function runDue(force = false) {
  if (document.hidden && !force) return;
  const now = performance.now();
  for (const task of tasks.values()) {
    if (!force && now < task.nextAt) continue;
    task.nextAt = now + task.intervalMs;
    try {
      task.callback();
    } catch (error) {
      report(error, task.key);
    }
  }
}

function stopTimer() {
  if (!timer) return;
  window.clearInterval(timer);
  timer = 0;
}

function startTimer() {
  if (timer || document.hidden || tasks.size === 0) return;
  timer = window.setInterval(runDue, TICK_MS);
}

function subscribe(key, intervalMs, callback, options = {}) {
  if (!key || typeof callback !== "function") {
    throw new TypeError("scheduler subscription requires key and callback");
  }
  const normalizedInterval = Math.max(TICK_MS, Number(intervalMs) || TICK_MS);
  tasks.set(key, {
    key,
    intervalMs: normalizedInterval,
    callback,
    nextAt: performance.now() + normalizedInterval,
  });
  if (options.runNow) {
    try {
      callback();
    } catch (error) {
      report(error, key);
    }
  }
  startTimer();
  return () => {
    tasks.delete(key);
    if (tasks.size === 0) stopTimer();
  };
}

function onVisibilityChange() {
  if (document.hidden) {
    stopTimer();
    return;
  }
  runDue(true);
  startTimer();
}

document.addEventListener("visibilitychange", onVisibilityChange);

window.__BF_SHARED_SCHEDULER__ = Object.freeze({
  schema: "bf.shared-runtime-scheduler.v1",
  subscribe,
  runDue,
  snapshot: () => ({
    taskCount: tasks.size,
    running: Boolean(timer),
    hidden: document.hidden,
    keys: [...tasks.keys()],
  }),
});

