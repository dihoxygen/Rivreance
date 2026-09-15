import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  formatAge,
  formatFlow,
  formatNumber,
  formatOrdinal,
  STATUS_COLORS,
  STATUS_DESCRIPTIONS,
  STATUS_LABELS,
  thresholdPosition,
} from "../format.ts";
import type { Status } from "../types.ts";

const STATUSES: Status[] = ["green", "yellow", "red", "gray"];

describe("status vocabulary", () => {
  it("labels, describes, and colours every status the API can return", () => {
    for (const status of STATUSES) {
      assert.ok(STATUS_LABELS[status]);
      assert.ok(STATUS_DESCRIPTIONS[status]);
      assert.match(STATUS_COLORS[status], /^#[0-9a-f]{6}$/);
    }
  });
});

describe("formatNumber", () => {
  it("renders an em dash rather than NaN for missing readings", () => {
    for (const value of [null, undefined, Number.NaN]) {
      assert.equal(formatNumber(value), "—");
    }
  });

  it("keeps the requested precision", () => {
    assert.equal(formatNumber(2, 2), "2.00");
    assert.equal(formatNumber(1.239, 2), "1.24");
  });
});

describe("formatFlow", () => {
  it("keeps a decimal on small creek flows, where 7 vs 8 cfs matters", () => {
    assert.equal(formatFlow(7.8), "7.8 cfs");
  });

  it("drops decimals on large flows, where they are noise", () => {
    assert.equal(formatFlow(12345.6), "12,346 cfs");
  });

  it("distinguishes no reading from a reading of zero", () => {
    assert.equal(formatFlow(null), "—");
    assert.equal(formatFlow(0), "0 cfs");
  });
});

describe("formatAge", () => {
  it("scales the unit with the age", () => {
    assert.equal(formatAge(0.4), "just now");
    assert.equal(formatAge(45), "45 min ago");
    assert.equal(formatAge(150), "2.5 h ago");
    assert.equal(formatAge(60 * 20), "20 h ago");
    assert.equal(formatAge(60 * 24 * 3), "3 d ago");
  });

  it("never claims freshness it does not have", () => {
    assert.equal(formatAge(null), "unknown age");
    assert.equal(formatAge(undefined), "unknown age");
  });
});

describe("formatOrdinal", () => {
  it("uses the English suffix, including the teens exception", () => {
    assert.deepEqual([1, 2, 3, 4, 11, 12, 13, 21, 42, 93].map(formatOrdinal), [
      "1st",
      "2nd",
      "3rd",
      "4th",
      "11th",
      "12th",
      "13th",
      "21st",
      "42nd",
      "93rd",
    ]);
  });
});

describe("thresholdPosition", () => {
  it("places a reading proportionally inside its window", () => {
    assert.equal(thresholdPosition(50, 0, 100), 50);
    assert.equal(thresholdPosition(25, 0, 100), 25);
  });

  it("clamps readings outside the window instead of overflowing the bar", () => {
    assert.equal(thresholdPosition(-40, 0, 100), 0);
    assert.equal(thresholdPosition(400, 0, 100), 100);
  });

  it("stays centred when a station has a degenerate window", () => {
    assert.equal(thresholdPosition(10, 100, 100), 50);
  });
});
