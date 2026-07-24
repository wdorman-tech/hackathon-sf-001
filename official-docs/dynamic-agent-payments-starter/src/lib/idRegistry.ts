import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

/** Tracks agent IDs added at runtime, on top of a fixed seed list. */
export function createIdRegistry(path: string, seed: readonly string[]) {
  async function readExtra(): Promise<string[]> {
    try {
      return JSON.parse(await readFile(path, "utf8")) as string[];
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw error;
    }
  }

  return {
    async list(): Promise<string[]> {
      return [...new Set([...seed, ...(await readExtra())])];
    },
    async register(id: string): Promise<void> {
      const extra = await readExtra();
      if (seed.includes(id) || extra.includes(id)) return;
      extra.push(id);
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, JSON.stringify(extra, null, 2));
    },
  };
}
