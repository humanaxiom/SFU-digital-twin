"use strict";

// Docker-only host-published preview wrapper for the candidate browser gate.
const assert = require("node:assert/strict");
const http = require("node:http");
const { spawn } = require("node:child_process");

assert.ok(require("node:fs").existsSync("/.dockerenv"), "Run this wrapper through Docker.");

const TARGET_HOST = "host.docker.internal";
const TARGET_PORT = 18117;
const LISTEN_HOST = "127.0.0.1";
const LISTEN_PORT = 18118;

function targetRequest(options, callback) {
  return http.request({
    hostname: TARGET_HOST,
    port: TARGET_PORT,
    path: options.path || options.url || "/",
    method: options.method,
    headers: { ...options.headers, host: `${LISTEN_HOST}:${TARGET_PORT}` },
  }, callback);
}

function probe() {
  return new Promise((resolve, reject) => {
    const request = targetRequest({ path: "/demo/v1/health", method: "GET", headers: {} }, response => {
      response.resume();
      response.once("end", () => {
        if (response.statusCode >= 200 && response.statusCode < 300) resolve();
        else reject(new Error(`Host preview health probe returned ${response.statusCode}.`));
      });
    });
    request.once("error", error => reject(new Error(`Host preview is unavailable: ${error.message}`)));
    request.setTimeout(15000, () => request.destroy(new Error("Host preview probe timed out.")));
    request.end();
  });
}

async function main() {
  await probe();
  const server = http.createServer((request, response) => {
    const upstream = targetRequest(request, upstreamResponse => {
      response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    });
    upstream.once("error", error => {
      if (!response.headersSent) response.writeHead(502, { "content-type": "text/plain" });
      response.end(`Preview proxy failed: ${error.message}`);
    });
    request.pipe(upstream);
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(LISTEN_PORT, LISTEN_HOST, resolve);
  });
  const child = spawn("node", ["/workspace/tests/browser/candidate.cjs"], {
    stdio: "inherit",
    env: { ...process.env, WAYFINDING_BROWSER_BASE_URL: `http://${LISTEN_HOST}:${LISTEN_PORT}` },
  });
  const exitCode = await new Promise(resolve => {
    child.once("error", error => {
      console.error(`Browser gate failed to start: ${error.message}`);
      resolve(1);
    });
    child.once("exit", (code, signal) => {
      if (signal) {
        console.error(`Browser gate terminated by ${signal}.`);
        resolve(1);
      } else resolve(code ?? 1);
    });
  });
  await new Promise(resolve => server.close(resolve));
  process.exitCode = exitCode;
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
