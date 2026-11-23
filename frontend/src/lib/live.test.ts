import { describe, expect, it } from "vitest";
import { parseLiveReading } from "./live";

const READING = { outlet_id: 1, power_w: 83.5, online: true, ts: "2026-11-23T15:00:00Z" };

describe("parseLiveReading", () => {
  it("reads a reading", () => {
    expect(parseLiveReading(JSON.stringify(READING))).toEqual(READING);
  });

  it("accepts a plug that could not be read, which has no power", () => {
    const offline = { ...READING, power_w: null, online: false };
    expect(parseLiveReading(JSON.stringify(offline))).toEqual(offline);
  });

  it("drops fields it does not know", () => {
    expect(parseLiveReading(JSON.stringify({ ...READING, extra: 1 }))).toEqual(READING);
  });

  it.each([
    ["not text", 42],
    ["not JSON", "{oops"],
    ["null", "null"],
    ["a list", "[]"],
    ["a number", "7"],
    ["no plug id", JSON.stringify({ ...READING, outlet_id: undefined })],
    ["a plug id that is text", JSON.stringify({ ...READING, outlet_id: "1" })],
    ["power that is text", JSON.stringify({ ...READING, power_w: "83" })],
    ["no power field", JSON.stringify({ outlet_id: 1, online: true, ts: READING.ts })],
    ["online that is not a boolean", JSON.stringify({ ...READING, online: 1 })],
    ["no timestamp", JSON.stringify({ ...READING, ts: undefined })],
  ])("rejects %s", (_name, data) => {
    expect(parseLiveReading(data)).toBeNull();
  });
});
