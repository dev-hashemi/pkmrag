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
