from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifest.webmanifest"
WORKER_PATH = ROOT / "service-worker.js"
OFFLINE_PATH = ROOT / "offline.html"

EXPECTED_SHELL_ASSETS = {
    "/companion",
    "/offline.html",
    "/manifest.webmanifest",
    "/assets/nova_app_icon.svg",
    "/assets/nova_foundation_ui.js",
    "/assets/nova_companion/companion-shell.css",
    "/assets/nova_companion/companion-app.js",
    "/assets/nova_companion/companion-api.js",
    "/assets/nova_companion/companion-store.js",
    "/assets/nova_companion/companion-presence.js",
    "/assets/nova_companion/companion-conversation.js",
    "/assets/nova_companion/companion-composer.js",
    "/assets/nova_companion/companion-spark.js",
    "/assets/nova_companion/companion-senses.js",
    "/assets/nova_companion/companion-trust.js",
}


WORKER_HARNESS = r"""
const fs = require("node:fs");
const vm = require("node:vm");

const workerSource = fs.readFileSync(process.argv[1], "utf8");
const origin = "https://nova.local";

function keyOf(value) {
  if (typeof value === "string") {
    if (value.startsWith("http://") || value.startsWith("https://")) {
      const url = new URL(value);
      return `${url.pathname}${url.search}`;
    }
    return value;
  }
  const url = new URL(value.url);
  return `${url.pathname}${url.search}`;
}

function fakeResponse(marker, status = 200) {
  return {
    marker,
    status,
    ok: status >= 200 && status < 300,
    clone() {
      return fakeResponse(marker, status);
    },
  };
}

async function createRuntime({
  network = "ok",
  seededPaths = [],
  existingCaches = [],
  runtimePutFailure = false,
} = {}) {
  const listeners = {};
  const cacheStores = new Map();
  const addAllCalls = [];
  const putCalls = [];
  const deleteCalls = [];
  const fetchCalls = [];
  let seedComplete = false;

  for (const name of existingCaches) {
    cacheStores.set(name, new Map());
  }

  function ensureStore(name) {
    if (!cacheStores.has(name)) cacheStores.set(name, new Map());
    return cacheStores.get(name);
  }

  const caches = {
    async open(name) {
      const store = ensureStore(name);
      return {
        async addAll(paths) {
          addAllCalls.push([...paths]);
          for (const path of paths) {
            store.set(keyOf(path), fakeResponse(`precache:${keyOf(path)}`));
          }
        },
        async put(request, response) {
          const key = keyOf(request);
          putCalls.push(key);
          if (runtimePutFailure && seedComplete) {
            throw new Error("cache write failed");
          }
          store.set(key, response);
        },
        async match(request) {
          return store.get(keyOf(request));
        },
      };
    },
    async match(request) {
      const key = keyOf(request);
      for (const store of cacheStores.values()) {
        if (store.has(key)) return store.get(key);
      }
      return undefined;
    },
    async keys() {
      return [...cacheStores.keys()];
    },
    async delete(name) {
      deleteCalls.push(name);
      return cacheStores.delete(name);
    },
  };

  const self = {
    location: { origin },
    clients: { async claim() {} },
    skipWaiting() {},
    addEventListener(name, callback) {
      listeners[name] = callback;
    },
  };

  const context = {
    URL,
    Promise,
    Response: {
      error() {
        return fakeResponse("response:error", 0);
      },
    },
    caches,
    self,
    fetch: async request => {
      const key = keyOf(request);
      fetchCalls.push(key);
      if (network === "throw") throw new Error("offline");
      return fakeResponse(`network:${key}`);
    },
  };
  vm.runInNewContext(workerSource, context, { filename: "service-worker.js" });

  const cache = await caches.open("test-seed");
  for (const path of seededPaths) {
    await cache.put(path, fakeResponse(`cache:${path}`));
  }
  seedComplete = true;
  putCalls.length = 0;

  return {
    listeners,
    cacheStores,
    addAllCalls,
    putCalls,
    deleteCalls,
    fetchCalls,
  };
}

async function runInstall() {
  const runtime = await createRuntime();
  let pending;
  runtime.listeners.install({
    waitUntil(value) {
      pending = Promise.resolve(value);
    },
  });
  await pending;
  return {
    addAllCalls: runtime.addAllCalls,
    putCalls: runtime.putCalls,
  };
}

async function runActivate() {
  const runtime = await createRuntime({
    existingCaches: [
      "nova-shell-2026-07-01-old",
      "nova-shell-2026-07-17-old",
      "unrelated-app-cache",
    ],
  });
  let pending;
  runtime.listeners.activate({
    waitUntil(value) {
      pending = Promise.resolve(value);
    },
  });
  await pending;
  return {
    deleted: runtime.deleteCalls,
    remaining: [...runtime.cacheStores.keys()],
  };
}

async function runFetch({
  path,
  method = "GET",
  mode = "same-origin",
  authorization = false,
  network = "ok",
  seededPaths = ["/companion", "/offline.html"],
  originOverride = origin,
  runtimePutFailure = false,
}) {
  const runtime = await createRuntime({
    network,
    seededPaths,
    runtimePutFailure,
  });
  const request = {
    method,
    mode,
    url: `${originOverride}${path}`,
    headers: {
      has(name) {
        return authorization && String(name).toLowerCase() === "authorization";
      },
    },
  };
  let responsePromise;
  const event = {
    request,
    respondWith(value) {
      responsePromise = Promise.resolve(value);
    },
  };
  runtime.listeners.fetch(event);
  const response = responsePromise ? await responsePromise : null;
  return {
    handled: Boolean(responsePromise),
    marker: response ? response.marker : null,
    putCalls: runtime.putCalls,
    fetchCalls: runtime.fetchCalls,
  };
}

(async () => {
  const report = {
    install: await runInstall(),
    activate: await runActivate(),
    companionOnline: await runFetch({
      path: "/companion?source=installed",
      mode: "navigate",
    }),
    companionOffline: await runFetch({
      path: "/companion?source=installed",
      mode: "navigate",
      network: "throw",
    }),
    companionCacheWriteFailure: await runFetch({
      path: "/companion?source=installed",
      mode: "navigate",
      runtimePutFailure: true,
    }),
    classicOnline: await runFetch({
      path: "/classic?panel=settings",
      mode: "navigate",
    }),
    classicOffline: await runFetch({
      path: "/classic",
      mode: "navigate",
      network: "throw",
    }),
    allowedAsset: await runFetch({
      path: "/assets/nova_companion/companion-app.js",
    }),
    unlistedAsset: await runFetch({
      path: "/assets/private-result.png",
    }),
    authorizedAsset: await runFetch({
      path: "/assets/nova_companion/companion-app.js",
      authorization: true,
    }),
    postAsset: await runFetch({
      path: "/assets/nova_companion/companion-app.js",
      method: "POST",
    }),
    crossOriginAsset: await runFetch({
      path: "/assets/nova_companion/companion-app.js",
      originOverride: "https://example.invalid",
    }),
    privatePaths: {},
  };
  for (const path of [
    "/api/chat",
    "/nova/v1/chat",
    "/status",
    "/health",
    "/healthz",
  ]) {
    report.privatePaths[path] = await runFetch({ path });
  }
  process.stdout.write(JSON.stringify(report));
})().catch(error => {
  process.stderr.write(error.stack || String(error));
  process.exitCode = 1;
});
"""


@pytest.fixture(scope="module")
def worker_report() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for service-worker behavior tests")
    result = subprocess.run(
        [node, "-e", WORKER_HARNESS, str(WORKER_PATH)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_manifest_opens_companion_and_preserves_classic_routes():
    """Catch installed launches or shortcuts bypassing the Companion/Classic boundary."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["start_url"] == "/companion?source=installed"
    assert manifest["display"] == "standalone"
    assert manifest["scope"] == "/"
    assert manifest["icons"][0]["src"] == "/assets/nova_app_icon.svg"
    shortcuts = {item["name"]: item["url"] for item in manifest["shortcuts"]}
    assert shortcuts == {
        "Nova Companion": "/companion",
        "Nova Classic": "/classic",
        "Nova Settings": "/classic?panel=settings",
    }


def test_install_precaches_only_the_public_companion_shell(worker_report):
    """Catch private, Classic, or unrelated legacy assets entering the install cache."""
    assert worker_report["install"]["addAllCalls"] == [
        sorted(EXPECTED_SHELL_ASSETS)
    ]
    assert worker_report["install"]["putCalls"] == []


def test_companion_navigation_is_network_first_with_canonical_shell_fallback(
    worker_report,
):
    """Catch query-specific/private navigation caching or loss of offline Companion."""
    online = worker_report["companionOnline"]
    offline = worker_report["companionOffline"]

    assert online["handled"] is True
    assert online["marker"] == "network:/companion?source=installed"
    assert online["putCalls"] == ["/companion"]
    assert offline["handled"] is True
    assert offline["marker"] == "cache:/companion"
    assert offline["putCalls"] == []


def test_successful_network_response_survives_cache_storage_write_failure(
    worker_report,
):
    """Catch a Cache Storage quota/error replacing fresh Companion HTML."""
    result = worker_report["companionCacheWriteFailure"]

    assert result["handled"] is True
    assert result["marker"] == "network:/companion?source=installed"
    assert result["putCalls"] == ["/companion"]


def test_classic_is_never_cached_and_falls_back_to_public_offline_page(worker_report):
    """Catch Nova Classic HTML being copied into the service-worker cache."""
    online = worker_report["classicOnline"]
    offline = worker_report["classicOffline"]

    assert online["marker"] == "network:/classic?panel=settings"
    assert online["putCalls"] == []
    assert offline["marker"] == "cache:/offline.html"
    assert offline["putCalls"] == []


def test_only_allowlisted_same_origin_gets_can_enter_runtime_cache(worker_report):
    """Catch uploads, generated assets, authenticated requests, or writes being cached."""
    allowed = worker_report["allowedAsset"]
    assert allowed["handled"] is True
    assert allowed["putCalls"] == [
        "/assets/nova_companion/companion-app.js"
    ]

    for scenario in (
        "unlistedAsset",
        "authorizedAsset",
        "postAsset",
        "crossOriginAsset",
    ):
        result = worker_report[scenario]
        assert result["handled"] is False, scenario
        assert result["putCalls"] == [], scenario


def test_private_runtime_routes_are_never_intercepted_or_cached(worker_report):
    """Catch conversations, memory, health, or Nova API payloads entering Cache Storage."""
    for path, result in worker_report["privatePaths"].items():
        assert result["handled"] is False, path
        assert result["putCalls"] == [], path


def test_activation_removes_only_older_nova_shell_caches(worker_report):
    """Catch stale private shell caches surviving or unrelated caches being deleted."""
    activation = worker_report["activate"]
    assert set(activation["deleted"]) == {
        "nova-shell-2026-07-01-old",
        "nova-shell-2026-07-17-old",
    }
    assert "unrelated-app-cache" in activation["remaining"]


def test_offline_recovery_is_truthful_and_links_both_experiences():
    """Catch misleading activity claims or an offline dead end."""
    source = OFFLINE_PATH.read_text(encoding="utf-8").lower()

    assert "cannot reach nova" in source
    assert "no private content is stored" in source
    assert "retry" in source
    assert 'href="/companion"' in source
    assert 'href="/classic"' in source
    assert "thinking" not in source
    assert "responding" not in source
