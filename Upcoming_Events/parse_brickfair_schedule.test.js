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
  <div id="hed2">Oaks</div>
  <table><tr>
    <td>
      <p class="dbInfo">
        <strong>Public Hours</strong>
        <br /><small>Saturday</small> 10:00am - 4:00pm</samp>
        <br /><small>Sunday</small> 10:00am - 4:00pm</samp>
      </p>
    </td>
    <td>
      <p class="dbInfo">
        <strong>Exhibitor Hours</strong>
        <br /><small>Thursday</small> Noon - 11:00pm</samp>
        <br /><small>Friday</small> 8:30am - 11:00pm</samp>
        <br /><small>Saturday</small> 8:30am - 11:00pm</samp>
        <br /><small class="tAlert">Adult Swim 21+years-old only, SAT 9pm - 2am</small>
        <br /><small>Sunday</small> 8:30am - Midnight</samp>
      </p>
    </td>
  </tr></table>
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
  <p class="pWeekday">Friday</p>
  <div class="divWeekday" id="Day_6" data-date="11/6/2026"></div>
  <p class="pWeekday">Saturday</p>
  <div class="divWeekday" id="Day_7" data-date="11/7/2026"></div>
  <p class="pWeekday">Sunday</p>
  <div class="divWeekday" id="Day_1" data-date="11/8/2026">
    <div class="Gamvent" id="Game_4">
      <p><span class="gmName">Brickee</span><small>Votes Due</small></p>
      <input type="hidden" class="Hour" value="10" />
      <input type="hidden" class="Minute" value="0" />
    </div>
  </div>
`;

test("groups events and puts public and exhibitor hour markers in each day's timeline", () => {
  const output = parseSchedule(fixture);
  assert.equal(
    output,
    [
      "Thursday, November 5, 2026",
      "12:00 PM: Sunday Brunch",
      "\tAND Hall opens",
      "5:30 PM: Build & Share - Food Court",
      "\tAND Brick History - Bingo (presenter: Alex Builder)",
      "\tAND Mosaic Reset",
      "11:00 PM: Hall closes",
      "",
      "Friday, November 6, 2026",
      "8:30 AM: Hall opens",
      "11:00 PM: Hall closes",
      "",
      "Saturday, November 7, 2026",
      "8:30 AM: Hall opens",
      "10:00 AM: Public hours start",
      "4:00 PM: Public hours end and teardown starts",
      "9:00 PM: Adult Swim 21+ years old only starts",
      "11:00 PM: Hall closes",
      "2:00 AM: Adult Swim 21+ years old only ends",
      "",
      "Sunday, November 8, 2026",
      "8:30 AM: Hall opens",
      "10:00 AM: Brickee Votes Due",
      "\tAND Public hours start",
      "4:00 PM: Public hours end and teardown starts",
      "12:00 AM: Hall closes",
    ].join("\n"),
  );
  assert.doesNotMatch(output, /^Public Hours$|^Exhibitor Hours$/m);
});

test("fails clearly when the page contains no schedule", () => {
  assert.throws(() => parseSchedule("<html><body>No schedule</body></html>"), /No schedule days/);
});

test("combines an inline event subtitle with its title without a title-specific rule", () => {
  const html = fixture.replace("Brickee", "Ballot").replace("Votes Due", "Closes");
  assert.match(parseSchedule(html), /10:00 AM: Ballot Closes/);
});

test("builds the default output filename from event, year, and retrieval date", () => {
  assert.equal(
    path.basename(
      getDefaultOutputPath(fixture, new Date(2026, 9, 17, 12)),
    ),
    "BrickFair_Oaks_2026_2026-10-17.txt",
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
