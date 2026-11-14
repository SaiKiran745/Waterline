import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const VERSION = "26.5.4_webgl-708-g332adb66f5";
const URL = `https://static.matterport.com/showcase-sdk/bundle/${VERSION}/showcase-bundle.zip`;
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const target = path.join(frontend, "public", "matterport-bundle");
const temporary = await mkdtemp(path.join(tmpdir(), "waterline-matterport-"));
const archive = path.join(temporary, "bundle.zip");
const extracted = path.join(temporary, "extracted");

try {
  const response = await fetch(URL);
  if (!response.ok) throw new Error(`Matterport Bundle download failed (${response.status}).`);
  await writeFile(archive, Buffer.from(await response.arrayBuffer()));
  await mkdir(extracted);
  execFileSync("unzip", ["-q", archive, "-d", extracted], { stdio: "inherit" });
  await rm(target, { recursive: true, force: true });
  await mkdir(path.dirname(target), { recursive: true });
  await rename(extracted, target);
  await writeFile(path.join(target, ".gitignore"), "*\n!.gitignore\n");
  console.log(`Matterport Bundle ${VERSION} is ready in public/matterport-bundle (git-ignored).`);
} finally {
  await rm(temporary, { recursive: true, force: true });
}
