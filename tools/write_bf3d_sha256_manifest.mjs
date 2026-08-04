import { createHash } from "node:crypto";
import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

function argument(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const rootArgument = argument("--root");
if (!rootArgument) throw new Error("必须提供 --root <目录>");
const root = path.resolve(rootArgument);
const output = path.resolve(argument("--output", path.join(root, "artifact_sha256.json")));

async function filesUnder(directory) {
  const records = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) records.push(...await filesUnder(absolute));
    else if (entry.isFile() && path.resolve(absolute) !== output) records.push(absolute);
  }
  return records;
}

const rootStat = await stat(root);
if (!rootStat.isDirectory()) throw new Error(`--root 不是目录：${root}`);
const files = (await filesUnder(root)).sort((a, b) => a.localeCompare(b, "zh-CN"));
const artifacts = [];
for (const absolute of files) {
  const payload = await readFile(absolute);
  artifacts.push({
    path: path.relative(root, absolute).replaceAll("\\", "/"),
    bytes: payload.byteLength,
    sha256: createHash("sha256").update(payload).digest("hex"),
  });
}
const manifest = {
  schema: "bf3d.artifact_sha256.v1",
  generatedAt: new Date().toISOString(),
  root,
  excludedSelf: path.relative(root, output).replaceAll("\\", "/"),
  fileCount: artifacts.length,
  totalBytes: artifacts.reduce((sum, item) => sum + item.bytes, 0),
  artifacts,
};
await writeFile(output, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify({
  output,
  fileCount: manifest.fileCount,
  totalBytes: manifest.totalBytes,
})}\n`);
