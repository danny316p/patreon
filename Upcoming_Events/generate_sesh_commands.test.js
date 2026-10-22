"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const { generateSeshCommands } = require("./generate_sesh_commands.js");

test("generates Sesh commands for all timed entries and simultaneous events", () => {
  const schedule = [
    "Saturday, November 7, 2026",
    "8:30 AM: Hall opens",
    "10:00 AM: Public hours start",
    "5:00 PM: Public hours end",
    "9:00 PM: Adult Swim 21+ years old only starts",
    "\tAND Build & Share - Food Court (presenter: Alex Builder)",
    "11:00 PM: Hall closes",
    "2:00 AM: Adult Swim 21+ years old only ends",
  ].join("\n");

  assert.equal(
    generateSeshCommands(schedule),
    [
      '/create title:"Hall opens" datetime:"November 7, 2026 8:30 AM EST"',
      '/create title:"Public hours start" datetime:"November 7, 2026 10:00 AM EST"',
      '/create title:"Public hours end" datetime:"November 7, 2026 5:00 PM EST"',
      '/create title:"Adult Swim 21+ years old only starts" datetime:"November 7, 2026 9:00 PM EST"',
      '/create title:"Build & Share" datetime:"November 7, 2026 9:00 PM EST" location:"Food Court" description:"Presenter: Alex Builder"',
      '/create title:"Hall closes" datetime:"November 7, 2026 11:00 PM EST"',
      '/create title:"Adult Swim 21+ years old only ends" datetime:"November 8, 2026 2:00 AM EST"',
    ].join("\n"),
  );
});

test("escapes quotes and backslashes in event titles", () => {
  assert.equal(
    generateSeshCommands(
      'Monday, November 9, 2026\n1:00 PM: Build "A" \\\\ Share',
    ),
    '/create title:"Build \\"A\\" \\\\\\\\ Share" datetime:"November 9, 2026 1:00 PM EST"',
  );
});

test("keeps Sesh titles within 64 characters and preserves the full title", () => {
  const title = "Check-In IS NOT POSSIBLE. Please check-in by Friday at the latest.";
  assert.equal(
    generateSeshCommands(`Saturday, November 7, 2026\n8:00 PM: ${title}`),
    '/create title:"Check-In IS NOT POSSIBLE. Please check-in by Friday at the la..." datetime:"November 7, 2026 8:00 PM EST" description:"Full schedule entry: Check-In IS NOT POSSIBLE. Please check-in by Friday at the latest."',
  );
});

test("rejects malformed schedule lines and invalid dates", () => {
  assert.throws(
    () => generateSeshCommands("Saturday, November 8, 2026\n1:00 PM: Event"),
    /Invalid schedule date/,
  );
  assert.throws(
    () => generateSeshCommands("Saturday, November 7, 2026\nnot a schedule entry"),
    /Unrecognized schedule line/,
  );
});

test("writes a command file beside the input schedule", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "sesh-commands-test-"));
  const inputPath = path.join(directory, "schedule.txt");
  const outputPath = path.join(directory, "schedule_sesh_commands.txt");
  const scriptPath = path.join(__dirname, "generate_sesh_commands.js");
  await fs.writeFile(
    inputPath,
    "Saturday, November 7, 2026\n8:30 AM: Hall opens\n",
    "utf8",
  );

  try {
    const result = spawnSync(
      process.execPath,
      [scriptPath, "--input", inputPath],
      { encoding: "utf8" },
    );
    assert.equal(result.status, 0, result.stderr);
    assert.equal(
      await fs.readFile(outputPath, "utf8"),
      '/create title:"Hall opens" datetime:"November 7, 2026 8:30 AM EST"\n',
    );
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});
