#!/usr/bin/env node

import { Buffer } from "node:buffer";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const LIB_ROOT = "file:///D:/文件/网络登录服务器管理/reliable-ssh-mcp/src";
const { parseConfig } = await import(`${LIB_ROOT}/config.js`);
const { ReliableSshClient } = await import(`${LIB_ROOT}/ssh-client.js`);
const { verifyIdentity } = await import(`${LIB_ROOT}/identity.js`);
const { verifyConfiguredRoute } = await import(`${LIB_ROOT}/route-check.js`);
const { decodeCapturedStream } = await import(`${LIB_ROOT}/remote-runner.js`);
const { createAuditLogger } = await import(`${LIB_ROOT}/audit.js`);

const WORKSPACE_ROOT = path.resolve("D:/文件/冀南钢铁运行中第二版本");
const config = parseConfig([
  "--ssh-target", "administrator@10.30.220.12",
  "--ssh-flavor", "plink",
  "--ssh-command", "C:/Users/hmw20/.local/bin/plink.exe",
  "--remote-python", "python",
  "--password-file", "C:/Users/hmw20/.codex/secrets/reliable-ssh-10-30-220-12.password",
  "--host-key", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDYkfg0Zva6XyQP1pSRwxOcUozBc6p3ltK8YcAaHipzf",
  "--connect-timeout", "8",
  "--command-timeout", "240",
  "--max-output-bytes", "1048576",
  "--transfer-timeout", "30",
  "--audit-log", "C:/Users/hmw20/.codex/logs/reliable-ssh-10-30-220-12.jsonl",
]);
const client = new ReliableSshClient(config);
const audit = createAuditLogger(config);
let verifiedIdentity = null;
let routeVerified = false;

async function ensureVerified() {
  if (!routeVerified) {
    await verifyConfiguredRoute(config);
    routeVerified = true;
  }
  if (!verifiedIdentity) {
    verifiedIdentity = verifyIdentity(await client.invoke({ operation: "probe_identity" }), config);
  }
  return verifiedIdentity;
}

function parseArgs(argv) {
  const values = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (!value.startsWith("--")) {
      values._.push(value);
      continue;
    }
    const key = value.slice(2).replaceAll("-", "_");
    const next = argv[index + 1];
    if (next == null || next.startsWith("--")) values[key] = true;
    else {
      values[key] = next;
      index += 1;
    }
  }
  return values;
}

function required(args, key) {
  const value = args[key];
  if (typeof value !== "string" || !value) throw new Error(`Missing --${key.replaceAll("_", "-")}`);
  return value;
}

function localPath(raw) {
  const resolved = path.resolve(raw);
  const relative = path.relative(WORKSPACE_ROOT, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Local path is outside the approved workspace: ${resolved}`);
  }
  return resolved;
}

async function verifiedInvoke(tool, toolArgs, payload) {
  const startedAt = Date.now();
  try {
    const identity = await ensureVerified();
    const result = await client.invoke(payload);
    await audit({ tool, args: toolArgs, allowed: true, result, startedAt });
    return { identity, result };
  } catch (error) {
    await audit({ tool, args: toolArgs, allowed: true, error, startedAt });
    throw error;
  }
}

async function readRemote(args) {
  const remote = required(args, "remote");
  const local = localPath(required(args, "local"));
  const maximum = Number(args.max_bytes || 2_000_000);
  const { identity, result } = await verifiedInvoke(
    "read_file",
    { path: remote, max_bytes: maximum },
    { operation: "read_file", path: remote, max_bytes: maximum },
  );
  if (result.truncated) throw new Error(`Remote file exceeds --max-bytes: ${remote}`);
  await writeFile(local, Buffer.from(result.data_b64, "base64"));
  return { ok: true, command: "read", identity, remote, local, bytes: result.returned_bytes };
}

async function applyPackage(args) {
  const localPackage = localPath(required(args, "package"));
  const remotePackage = required(args, "remote_package");
  const stageRoot = required(args, "stage_root");
  const timeout = Number(args.timeout || 240);
  const bytes = await readFile(localPackage);
  const writeCall = await verifiedInvoke(
    "write_file",
    { path: remotePackage, bytes: bytes.length, atomic: true },
    {
      operation: "write_file",
      path: remotePackage,
      data_b64: bytes.toString("base64"),
      create_parents: true,
      atomic: true,
    },
  );
  const launch = [
    "$ErrorActionPreference='Stop'",
    `Expand-Archive -LiteralPath '${remotePackage.replaceAll("'", "''")}' -DestinationPath '${stageRoot.replaceAll("'", "''")}' -Force`,
    `& powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${stageRoot.replaceAll("'", "''")}\\remote_deploy_diag_rules.ps1' -ManifestPath '${stageRoot.replaceAll("'", "''")}\\manifest.json'`,
    "exit $LASTEXITCODE",
  ].join("; ");
  const execCall = await verifiedInvoke(
    "exec_argv",
    { program: "powershell.exe", cwd: "F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW", timeout_seconds: timeout },
    {
      operation: "process",
      program: "powershell.exe",
      args: ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", launch],
      cwd: "F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW",
      env: {},
      stdin_b64: "",
      timeout_seconds: timeout,
      max_output_bytes: 1_048_576,
    },
  );
  const stdout = decodeCapturedStream(execCall.result.stdout);
  const stderr = decodeCapturedStream(execCall.result.stderr);
  if (execCall.result.timed_out || execCall.result.exit_code !== 0) {
    throw new Error(
      `Remote deployment failed: exit=${execCall.result.exit_code} timed_out=${execCall.result.timed_out}\n${stderr || stdout}`,
    );
  }
  return {
    ok: true,
    command: "apply-package",
    identity: execCall.identity,
    upload: writeCall.result,
    execution: {
      exit_code: execCall.result.exit_code,
      timed_out: execCall.result.timed_out,
      duration_ms: execCall.result.duration_ms,
      stdout,
      stderr,
    },
  };
}

async function probe() {
  const startedAt = Date.now();
  try {
    const identity = await ensureVerified();
    await audit({ tool: "probe_identity", args: { force: true }, allowed: true, result: identity, startedAt });
    return { ok: true, command: "probe", identity };
  } catch (error) {
    await audit({ tool: "probe_identity", args: { force: true }, allowed: true, error, startedAt });
    throw error;
  }
}

const args = parseArgs(process.argv.slice(2));
const command = args._[0] || "help";
try {
  let result;
  if (command === "probe") result = await probe();
  else if (command === "read") result = await readRemote(args);
  else if (command === "apply-package") result = await applyPackage(args);
  else {
    throw new Error(
      "Usage: reliable_ssh_22012_cli.mjs probe | read --remote PATH --local PATH | " +
        "apply-package --package PATH --remote-package PATH --stage-root PATH [--timeout 240]",
    );
  }
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
}
