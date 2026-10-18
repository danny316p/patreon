"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const {
  getDefaultOutputPath,
  getScheduleHtml,
  parseSchedule,
} = require("./parse_brickfair_schedule.js");

const fixture = `
  <title>BrickFair LEGO Expo</title>
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

test("builds the default output filename from event, year, and retrieval date", () => {
  assert.equal(
    path.basename(
      getDefaultOutputPath(fixture, new Date(2026, 9, 17, 12)),
    ),
    "BrickFair_LEGO_Expo_2026_2026-10-17.txt",
  );
});

test("defaults to a dated file and prints only with --stdout", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "brickfair-parser-cli-"));
  const inputPath = path.join(directory, "schedule.html");
  const html = fixture.replace("BrickFair LEGO Expo", "BrickFair Test CLI");
  const defaultOutputPath = getDefaultOutputPath(html);
  const scriptPath = path.join(__dirname, "parse_brickfair_schedule.js");
  await fs.writeFile(inputPath, html, "utf8");

  try {
    const fileRun = spawnSync(process.execPath, [scriptPath, "--input", inputPath], {
      encoding: "utf8",
    });
    assert.equal(fileRun.status, 0, fileRun.stderr);
    assert.match(fileRun.stdout, /Saved schedule to /);
    assert.equal(await fs.readFile(defaultOutputPath, "utf8"), `${parseSchedule(html)}\n`);

    const stdoutRun = spawnSync(
      process.execPath,
      [scriptPath, "--input", inputPath, "--stdout"],
      { encoding: "utf8" },
    );
    assert.equal(stdoutRun.status, 0, stdoutRun.stderr);
    assert.equal(stdoutRun.stdout, `${parseSchedule(html)}\n`);
  } finally {
    await fs.rm(defaultOutputPath, { force: true });
    await fs.rm(directory, { recursive: true, force: true });
  }
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
