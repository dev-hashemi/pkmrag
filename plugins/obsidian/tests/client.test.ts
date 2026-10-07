/**
 * Unit tests for OrbitClient and token discovery logic.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { OrbitClient } from "../src/client.js";
import { DEFAULT_SETTINGS } from "../src/types.js";

test("OrbitClient headers include Bearer token when configured", () => {
  const client = new OrbitClient({
    ...DEFAULT_SETTINGS,
    authToken: "sample_secret_token",
  });

  // Access private getHeaders via prototype / any casting
  const headers = (client as unknown as { getHeaders: () => Record<string, string> }).getHeaders();
  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers["Authorization"], "Bearer sample_secret_token");
});

test("OrbitClient headers omit Authorization when authToken is empty", () => {
  const client = new OrbitClient({
    ...DEFAULT_SETTINGS,
    authToken: "",
  });

  const headers = (client as unknown as { getHeaders: () => Record<string, string> }).getHeaders();
  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers["Authorization"], undefined);
});

test("OrbitClient autoDiscoverVaultToken reads .orbit/server_token", async () => {
  const client = new OrbitClient({ ...DEFAULT_SETTINGS });

  const mockApp = {
    vault: {
      adapter: {
        exists: async (p: string) => p === ".orbit/server_token",
        read: async (p: string) => "vault_generated_token_42",
      },
    },
  };

  const tok = await client.autoDiscoverVaultToken(mockApp as any);
  assert.equal(tok, "vault_generated_token_42");
  assert.equal(client.settings.authToken, "vault_generated_token_42");
});

test("OrbitClient autoDiscoverVaultToken handles missing file gracefully", async () => {
  const client = new OrbitClient({ ...DEFAULT_SETTINGS });

  const mockApp = {
    vault: {
      adapter: {
        exists: async () => false,
        read: async () => "",
      },
    },
  };

  const tok = await client.autoDiscoverVaultToken(mockApp as any);
  assert.equal(tok, null);
  assert.equal(client.settings.authToken, "");
});

test("OrbitClient searchVault dispatches POST request with query and near note", async () => {
  const client = new OrbitClient({
    ...DEFAULT_SETTINGS,
    serverUrl: "http://127.0.0.1:3747",
    authToken: "search_token_123",
  });

  const originalFetch = globalThis.fetch;
  let interceptedUrl = "";
  let interceptedInit: RequestInit | undefined;

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    interceptedUrl = String(input);
    interceptedInit = init;
    return new Response(
      JSON.stringify({
        query: "distributed consensus",
        results: [
          {
            title: "Paxos Algorithm",
            score: 0.94,
            chunk_text: "Paxos is a family of protocols for reaching consensus...",
            metadata: { path: "distributed/paxos.md" },
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  try {
    const results = await client.searchVault("distributed consensus", "raft.md", 5);
    assert.equal(interceptedUrl, "http://127.0.0.1:3747/api/v1/search");
    assert.equal(interceptedInit?.method, "POST");
    const sentBody = JSON.parse(String(interceptedInit?.body));
    assert.deepEqual(sentBody, {
      query: "distributed consensus",
      limit: 5,
      near: "raft.md",
    });
    const headers = interceptedInit?.headers as Record<string, string>;
    assert.equal(headers["Authorization"], "Bearer search_token_123");

    assert.equal(results.length, 1);
    assert.equal(results[0].title, "Paxos Algorithm");
    assert.equal(results[0].score, 0.94);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("OrbitClient searchVault throws error on non-200 response", async () => {
  const client = new OrbitClient({ ...DEFAULT_SETTINGS });
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async (): Promise<Response> => {
    return new Response("Internal Server Error", { status: 500 });
  };

  try {
    await assert.rejects(
      async () => {
        await client.searchVault("query");
      },
      {
        message: "Search failed with HTTP 500",
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Dismissed suggestions filter removes dismissed items matching source and target", () => {
  const dismissed = [
    {
      source_path: "notes/raft.md",
      target_title: "Byzantine Generals",
      dismissed_at: "2026-10-05T12:00:00Z",
    },
  ];

  const suggestions = [
    { target_title: "Paxos", target_path: "notes/paxos.md" },
    { target_title: "Byzantine Generals", target_path: "notes/byzantine.md" },
  ];

  const sourcePath = "notes/raft.md";
  const filtered = suggestions.filter(
    (s) =>
      !dismissed.some(
        (d) => d.source_path === sourcePath && d.target_title === s.target_title
      )
  );

  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].target_title, "Paxos");
});

test("OrbitClient testLlm dispatches POST request with provider and model", async () => {
  const client = new OrbitClient({
    ...DEFAULT_SETTINGS,
    llmProvider: "custom",
    llmBaseUrl: "https://api.test.com/v1",
    llmModel: "test-model",
    llmApiKey: "test-key",
  });

  const originalFetch = globalThis.fetch;
  let capturedBody = "";

  globalThis.fetch = async (url: string | URL | Request, init?: RequestInit): Promise<Response> => {
    capturedBody = String(init?.body || "");
    return new Response(
      JSON.stringify({
        success: true,
        message: "Connected to test-model",
        latency_ms: 42.5,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  try {
    const res = await client.testLlm();
    assert.equal(res.success, true);
    assert.equal(res.latency_ms, 42.5);
    const parsed = JSON.parse(capturedBody);
    assert.equal(parsed.provider, "custom");
    assert.equal(parsed.model, "test-model");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("OrbitClient triggerDiscover and triggerIngest dispatch operational requests", async () => {
  const client = new OrbitClient({ ...DEFAULT_SETTINGS });
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async (): Promise<Response> => {
    return new Response(JSON.stringify({ status: "started", message: "Job initiated" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const discRes = await client.triggerDiscover({ limit: 5 });
    assert.equal(discRes.status, "started");

    const ingRes = await client.triggerIngest({ rebuild: true });
    assert.equal(ingRes.status, "started");
  } finally {
    globalThis.fetch = originalFetch;
  }
});


