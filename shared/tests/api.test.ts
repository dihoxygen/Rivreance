import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { ApiError, createApi, queryKeys } from "../api.ts";

const realFetch = globalThis.fetch;

interface Call {
  url: string;
  headers: Record<string, string>;
}

/** Records the requests the client makes so the URLs it builds can be asserted. */
function stubFetch(body: unknown, status = 200): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = ((input: string | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      headers: (init?.headers ?? {}) as Record<string, string>,
    });
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    });
  }) as typeof globalThis.fetch;
  return calls;
}

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe("createApi", () => {
  it("tolerates a base URL with a trailing slash", async () => {
    const calls = stubFetch({ basins: [] });
    await createApi("http://api.test/api/v1/").basins();
    assert.equal(calls[0]?.url, "http://api.test/api/v1/basins");
  });

  it("unwraps the basins envelope", async () => {
    stubFetch({ basins: [{ huc8: "03160112" }, { huc8: "03160113" }] });
    const basins = await createApi("http://api.test/api/v1").basins();
    assert.deepEqual(
      basins.map((basin) => basin.huc8),
      ["03160112", "03160113"],
    );
  });

  it("sends the activity and stream-order filters as query parameters", async () => {
    const calls = stubFetch({ type: "FeatureCollection", features: [] });
    await createApi("http://api.test/api/v1").segments("03160112", "kayaking", 4);
    assert.equal(
      calls[0]?.url,
      "http://api.test/api/v1/basins/03160112/segments?activity=kayaking&min_order=4",
    );
  });

  it("defaults to the smallest stream order so nothing is hidden by accident", async () => {
    const calls = stubFetch({ type: "FeatureCollection", features: [] });
    await createApi("http://api.test/api/v1").segments("03160112", "fishing");
    assert.match(calls[0]?.url ?? "", /min_order=1$/);
  });

  it("escapes site ids, which carry an agency prefix and a colon", async () => {
    const calls = stubFetch({ points: [] });
    await createApi("http://api.test/api/v1").series("USGS:02458450", "00065");
    assert.equal(
      calls[0]?.url,
      "http://api.test/api/v1/sites/USGS%3A02458450/series?parameter=00065",
    );
  });

  it("asks for JSON", async () => {
    const calls = stubFetch({ status: "ok" });
    await createApi("http://api.test/api/v1").health();
    assert.equal(calls[0]?.headers.Accept, "application/json");
  });

  it("reports the status code when the API refuses", async () => {
    stubFetch({}, 503);
    await assert.rejects(
      () => createApi("http://api.test/api/v1").health(),
      (error: unknown) => {
        assert.ok(error instanceof ApiError);
        assert.equal(error.status, 503);
        assert.match(error.message, /\/health responded 503/);
        return true;
      },
    );
  });
});

describe("queryKeys", () => {
  it("separates cache entries per activity, so switching sport refetches", () => {
    assert.notDeepEqual(
      queryKeys.segments("03160112", "kayaking"),
      queryKeys.segments("03160112", "fishing"),
    );
  });

  it("separates cache entries per basin", () => {
    assert.notDeepEqual(
      queryKeys.sites("03160112", "kayaking"),
      queryKeys.sites("03160113", "kayaking"),
    );
  });
});
