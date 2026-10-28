/**
 * Unit tests for PkmragClient and token discovery logic.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { PkmragClient } from "../src/client.js";
import { DEFAULT_SETTINGS } from "../src/types.js";

test("PkmragClient headers include Bearer token when configured", () => {
  const client = new PkmragClient({
    ...DEFAULT_SETTINGS,
    authToken: "sample_secret_token",
  });

  // Access private getHeaders via prototype / any casting
  const headers = (client as unknown as { getHeaders: () => Record<string, string> }).getHeaders();
  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers["Authorization"], "Bearer sample_secret_token");
});

test("PkmragClient headers omit Authorization when authToken is empty", () => {
  const client = new PkmragClient({
    ...DEFAULT_SETTINGS,
    authToken: "",
  });

  const headers = (client as unknown as { getHeaders: () => Record<string, string> }).getHeaders();
  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers["Authorization"], undefined);
});

test("PkmragClient autoDiscoverVaultToken reads .pkmrag/server_token", async () => {
  const client = new PkmragClient({ ...DEFAULT_SETTINGS });

  const mockApp = {
    vault: {
      adapter: {
        exists: async (p: string) => p === ".pkmrag/server_token",
        read: async (p: string) => "vault_generated_token_42",
      },
    },
  };

  const tok = await client.autoDiscoverVaultToken(mockApp as any);
  assert.equal(tok, "vault_generated_token_42");
  assert.equal(client.settings.authToken, "vault_generated_token_42");
});

test("PkmragClient autoDiscoverVaultToken handles missing file gracefully", async () => {
  const client = new PkmragClient({ ...DEFAULT_SETTINGS });

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

test("PkmragClient searchVault dispatches POST request with query and near note", async () => {
  const client = new PkmragClient({
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
            chunk_id: "distributed/paxos.md#chunk_0",
            note_path: "distributed/paxos.md",
            note_title: "Paxos Algorithm",
            heading: "# Paxos Algorithm > ## Quorum Intersection",
            text: "Paxos is a family of protocols for reaching consensus...",
            score: 0.94,
            dense_score: 0.12,
            sparse_score: 2.4,
            graph_boost_factor: 1.25,
            hop_distance: 1,
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
    assert.equal(results[0].note_title, "Paxos Algorithm");
    assert.equal(results[0].note_path, "distributed/paxos.md");
    assert.equal(results[0].score, 0.94);
    assert.equal(results[0].graph_boost_factor, 1.25);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("PkmragClient searchVault throws error on non-200 response", async () => {
  const client = new PkmragClient({ ...DEFAULT_SETTINGS });
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
  const dismissed: Record<
    string,
    { sourcePath: string; targetPath: string; targetTitle: string; dismissedAt: number }
  > = {
    "notes/raft.md::notes/byzantine.md": {
      sourcePath: "notes/raft.md",
      targetPath: "notes/byzantine.md",
      targetTitle: "Byzantine Generals",
      dismissedAt: 1,
    },
  };

  const suggestions = [
    { source_path: "notes/raft.md", target_path: "notes/paxos.md" },
    { source_path: "notes/raft.md", target_path: "notes/byzantine.md" },
  ];

  const filtered = suggestions.filter(
    (s) => !dismissed[`${s.source_path}::${s.target_path}`]
  );

  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].target_path, "notes/paxos.md");
});

test("PkmragClient testLlm dispatches POST request with provider and model", async () => {
  const client = new PkmragClient({
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

test("PkmragClient triggerDiscover and triggerIngest dispatch operational requests", async () => {
  const client = new PkmragClient({ ...DEFAULT_SETTINGS });
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

test("PkmragClient estimateDiscover dispatches pre-flight estimation request", async () => {
  const client = new PkmragClient({ ...DEFAULT_SETTINGS });
  const originalFetch = globalThis.fetch;
  let capturedUrl = "";
  let capturedBody = "";

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    capturedUrl = String(input);
    capturedBody = String(init?.body || "{}");
    return new Response(
      JSON.stringify({
        candidate_count: 3,
        evaluated_count: 3,
        estimated_prompt_tokens: 2400,
        estimated_completion_tokens: 360,
        total_tokens: 2760,
        provider: "openai",
        model: "gpt-4o-mini",
        candidate_pairs: [
          {
            source_path: "NoteA.md",
            target_path: "NoteB.md",
            source_title: "Note A",
            target_title: "Note B",
            similarity: 0.88,
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  try {
    const est = await client.estimateDiscover({ note_path: "NoteA.md", limit: 5 });
    assert.ok(capturedUrl.endsWith("/api/v1/discover/estimate"));
    assert.equal(JSON.parse(capturedBody).note_path, "NoteA.md");
    assert.equal(est.candidate_count, 3);
    assert.equal(est.total_tokens, 2760);
    assert.equal(est.candidate_pairs.length, 1);
    assert.equal(est.candidate_pairs[0].similarity, 0.88);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


