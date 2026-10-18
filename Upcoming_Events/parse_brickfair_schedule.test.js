"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { getScheduleHtml, parseSchedule } = require("./parse_brickfair_schedule.js");

const fixture = `
  <p class="pWeekday">Thursday</p>
  <div class="divWeekday" id="Day_5" data-date="11/5/2026">
    <div class="Gamvent clikable" id="Game_1">
      <p><span class="gmName">Build &amp; Share</span></p>
      <p class="Rtyu">Food Court</p>
      <input type="hidden" class="Hour" value="17" />
      <input type="hidden" class="Minute" value="30" />
    </div>
    <div class="Gamvent clikable" id="Seminar_1">
      <p><span class="gmName">Brick History</span></p>
      <p><small>with</small> <span class="Comic">Alex Builder</span></p>
      <p class="Rtyu">Bingo</p>
      <input type="hidden" class="Hour" value="17" />
      <input type="hidden" class="Minute" value="30" />
    </div>
    <div class="Gamvent" id="Game_2">
      <p><span class="gmName">Sunday Brunch</span></p>
      <input type="hidden" class="Hour" value="12" />
      <input type="hidden" class="Minute" value="0" />
    </div>
    <div class="Gamvent" id="Game_3">
      <p><span class="gmName"></span><small>Mosaic Reset</small></p>
      <input type="hidden" class="Hour" value="17" />
      <input type="hidden" class="Minute" value="30" />
    </div>
  </div>
`;

test("groups simultaneous events and includes schedule details", () => {
  assert.equal(
    parseSchedule(fixture),
    [
      "Thursday, November 5, 2026",
      "12:00 PM: Sunday Brunch",
      "5:30 PM: Build & Share — Food Court",
      "AND Brick History — Bingo (presenter: Alex Builder)",
      "AND Mosaic Reset",
    ].join("\n"),
  );
});

test("fails clearly when the page contains no schedule", () => {
  assert.throws(() => parseSchedule("<html><body>No schedule</body></html>"), /No schedule days/);
});

test("reuses cached HTML until refreshed or expired", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "brickfair-parser-test-"));
  const cachePath = path.join(directory, "schedule.json");
  const fetchedPages = [
    "first page",
    "refreshed page",
    "uncached page",
    "expired page",
  ];
  let fetchCount = 0;
  const fetcher = async () => ({
    ok: true,
    text: async () => fetchedPages[fetchCount++],
  });
  const now = 1_800_000_000_000;

  try {
    assert.equal(await getScheduleHtml("https://example.com", { cachePath, fetcher, now }), "first page");
    assert.equal(await getScheduleHtml("https://example.com", { cachePath, fetcher, now }), "first page");
    assert.equal(fetchCount, 1);

    assert.equal(
      await getScheduleHtml("https://example.com", {
        cachePath,
        fetcher,
        now,
        refresh: true,
      }),
      "refreshed page",
    );
    assert.equal(fetchCount, 2);

    assert.equal(
      await getScheduleHtml("https://example.com", {
        cachePath,
        fetcher,
        now,
        noCache: true,
      }),
      "uncached page",
    );
    assert.equal(fetchCount, 3);
    assert.equal(
      await getScheduleHtml("https://example.com", { cachePath, fetcher, now }),
      "refreshed page",
    );
    assert.equal(fetchCount, 3);

    assert.equal(
      await getScheduleHtml("https://example.com", {
        cachePath,
        fetcher,
        now: now + 24 * 60 * 60 * 1000,
      }),
      "expired page",
    );
    assert.equal(fetchCount, 4);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});
