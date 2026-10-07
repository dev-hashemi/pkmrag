/**
 * Server-Sent Events subscriber for PKMRAG client.
 */

export function connectEventStream(
  serverUrl: string,
  authToken: string,
  onEvent: (event: string, data: Record<string, unknown>) => void
): EventSource | null {
  if (typeof EventSource === "undefined") {
    return null;
  }
  try {
    const base = serverUrl.replace(/\/+$/, "");
    const tokenParam = authToken ? `?token=${encodeURIComponent(authToken)}` : "";
    const source = new EventSource(`${base}/api/v1/events${tokenParam}`);

    const topics = [
      "reindex",
      "sync",
      "discover_progress",
      "discover_complete",
      "ingest_progress",
      "ingest_complete",
    ];

    for (const topic of topics) {
      source.addEventListener(topic, (e: MessageEvent) => {
        try {
          onEvent(topic, JSON.parse(e.data));
        } catch {}
      });
    }

    return source;
  } catch (err) {
    console.warn("[PKMRAG] Could not establish EventSource stream:", err);
    return null;
  }
}
