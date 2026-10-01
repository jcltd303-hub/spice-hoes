import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

const PYTHON_BIN = process.env.PYTHON_BIN || process.env.PYTHON || 'python3';
const SPICE_DB = process.env.SPICE_DB || 'data/experiments.sqlite';
const SPICE_PERSONAS = process.env.SPICE_PERSONAS || 'personas';
const MAX_OUTPUT_BYTES = 8 * 1024 * 1024;

export class CoreBridgeError extends Error {
  status: number;
  details?: unknown;

  constructor(message: string, status = 400, details?: unknown) {
    super(message);
    this.name = 'CoreBridgeError';
    this.status = status;
    this.details = details;
  }
}

export function runCore<T = unknown>(action: string, payload: Record<string, unknown> = {}): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, ['-m', 'spicecore.control_plane', action], {
      cwd: ROOT,
      env: {
        ...process.env,
        SPICE_DB,
        SPICE_PERSONAS,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';
    let killedForSize = false;

    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');

    child.stdout.on('data', (chunk: string) => {
      stdout += chunk;
      if (Buffer.byteLength(stdout, 'utf8') > MAX_OUTPUT_BYTES) {
        killedForSize = true;
        child.kill('SIGKILL');
      }
    });

    child.stderr.on('data', (chunk: string) => {
      stderr += chunk;
      if (Buffer.byteLength(stderr, 'utf8') > MAX_OUTPUT_BYTES) {
        stderr = stderr.slice(-MAX_OUTPUT_BYTES);
      }
    });

    child.on('error', (err) => {
      reject(new CoreBridgeError(`Unable to start spicecore: ${err.message}`, 503));
    });

    child.on('close', (code) => {
      if (killedForSize) {
        reject(new CoreBridgeError('spicecore response exceeded safety limit', 502));
        return;
      }

      if (code !== 0) {
        let parsed: any = null;
        const lines = stderr.trim().split(/\r?\n/).filter(Boolean);
        for (let i = lines.length - 1; i >= 0; i -= 1) {
          try {
            parsed = JSON.parse(lines[i]);
            break;
          } catch {
            // Continue looking for the structured control-plane error.
          }
        }
        reject(new CoreBridgeError(parsed?.error || stderr.trim() || `spicecore exited with code ${code}`, 400, parsed));
        return;
      }

      try {
        resolve(JSON.parse(stdout) as T);
      } catch (err: any) {
        reject(new CoreBridgeError(`Invalid spicecore JSON response: ${err.message}`, 502));
      }
    });

    child.stdin.end(JSON.stringify(payload));
  });
}
