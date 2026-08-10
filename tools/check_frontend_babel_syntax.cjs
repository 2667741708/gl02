"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
}

const root = path.resolve(__dirname, "..");
const target = path.resolve(process.argv[2] || path.join(root, "高炉前端数据", "frontend_dashboard_v3.server.html"));
const babelPath = path.join(root, "高炉前端数据", "libs", "babel.min.js");

if (!fs.existsSync(target)) {
  fail(`Target HTML not found: ${target}`);
} else if (!fs.existsSync(babelPath)) {
  fail(`Babel standalone not found: ${babelPath}`);
} else {
  const html = fs.readFileSync(target, "utf8");
  const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)]
    .filter((match) => /type=["']text\/babel["']/i.test(match[1] || ""));
  if (!scripts.length) {
    fail(`No text/babel script found in ${target}`);
  } else {
    const context = { console, setTimeout, clearTimeout };
    context.self = context;
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(babelPath, "utf8"), context, { filename: babelPath });
    scripts.forEach((match, index) => {
      context.Babel.transform(match[2], {
        filename: `${path.basename(target)}#text-babel-${index + 1}`,
        presets: ["typescript", "react"],
        sourceType: "script",
      });
    });
    process.stdout.write(`Babel syntax OK: ${scripts.length} script(s) in ${target}\n`);
  }
}
