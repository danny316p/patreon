#!/usr/bin/env node
"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");

const WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function parseScheduleDate(line) {
  const match = line.match(
    /^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), (January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (\d{4})$/,
  );
  if (!match) return null;

  const [, weekday, month, dayText, yearText] = match;
  const day = Number(dayText);
  const year = Number(yearText);
  const monthIndex = MONTHS.indexOf(month);
  const date = new Date(Date.UTC(year, monthIndex, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== monthIndex ||
    date.getUTCDate() !== day ||
    WEEKDAYS[date.getUTCDay()] !== weekday
  ) {
    throw new Error(`Invalid schedule date: ${line}`);
  }
  return { year, month: monthIndex + 1, day };
}

function formatDate({ year, month, day }) {
  return `${MONTHS[month - 1]} ${day}, ${year}`;
}

function quote(value) {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function formatCommand(eventText, time, date) {
  let title = eventText;
  let description = "";
  let location = "";
  const presenter = title.match(/\s+\(presenter:\s*(.+)\)$/i);
  if (presenter) {
    description = `Presenter: ${presenter[1]}`;
    title = title.slice(0, presenter.index);
  }

  const locationSeparator = title.lastIndexOf(" - ");
  if (locationSeparator >= 0) {
    location = title.slice(locationSeparator + 3);
    title = title.slice(0, locationSeparator);
  }

  if (Array.from(title).length > 64) {
    description = [
      description,
      `Full schedule entry: ${eventText}`,
    ].filter(Boolean).join("; ");
    title = `${Array.from(title).slice(0, 61).join("")}...`;
  }

  if (!title) throw new Error(`An event has no title: ${eventText}`);
  const dateTime = `${formatDate(date)} ${time}`;
  const parameters = [
    `title:${quote(title)}`,
    `datetime:${quote(dateTime)}`,
  ];
  if (location) parameters.push(`location:${quote(location)}`);
  if (description) parameters.push(`description:${quote(description)}`);
  return `/create ${parameters.join(" ")}`;
}

function generateSeshCommands(schedule) {
  const commands = [];
  let date = null;
  let previousMinute = null;
  let rolloverDays = 0;
  let currentMinute = null;

  for (const line of schedule.replace(/^\uFEFF/, "").split(/\r?\n/)) {
    if (!line.trim()) continue;

    const parsedDate = parseScheduleDate(line);
    if (parsedDate) {
      date = parsedDate;
      previousMinute = null;
      rolloverDays = 0;
      currentMinute = null;
      continue;
    }

    const timedEntry = line.match(/^(\d{1,2}):(\d{2}) (AM|PM): (.+)$/i);
    const continuation = line.match(/^\s+AND (.+)$/i);
    if (!timedEntry && !continuation) {
      throw new Error(`Unrecognized schedule line: ${line}`);
    }
    if (!date) throw new Error("A schedule entry appears before its day heading.");

    let title;
    if (timedEntry) {
      const [, hourText, minuteText, period, eventTitle] = timedEntry;
      const hour = Number(hourText);
      const minute = Number(minuteText);
      if (hour < 1 || hour > 12 || minute > 59) {
        throw new Error(`Invalid event time: ${timedEntry[0]}`);
      }
      currentMinute = (hour % 12 + (period.toLowerCase() === "pm" ? 12 : 0)) * 60 + minute;
      if (previousMinute !== null && currentMinute < previousMinute) {
        rolloverDays += 1;
      }
      previousMinute = currentMinute;
      title = eventTitle;
    } else {
      if (currentMinute === null) {
        throw new Error(`A simultaneous event has no preceding time: ${line.trim()}`);
      }
      title = continuation[1];
    }

    const eventDate = new Date(Date.UTC(date.year, date.month - 1, date.day + rolloverDays));
    const commandDate = {
      year: eventDate.getUTCFullYear(),
      month: eventDate.getUTCMonth() + 1,
      day: eventDate.getUTCDate(),
    };
    commands.push(formatCommand(title, lineTime(currentMinute), commandDate));
  }

  if (commands.length === 0) throw new Error("No timed schedule entries were found.");
  return commands.join("\n");
}

function lineTime(minutes) {
  const hour = Math.floor(minutes / 60);
  const minute = minutes % 60;
  const period = hour < 12 ? "AM" : "PM";
  return `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${period}`;
}

function parseArguments(args) {
  const options = { input: null, output: null, stdout: false };
  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (argument === "--input" || argument === "--output") {
      const value = args[index + 1];
      if (!value || value.startsWith("-")) {
        throw new Error(`${argument} requires a path.`);
      }
      options[argument === "--input" ? "input" : "output"] = path.resolve(value);
      index += 1;
    } else if (argument === "--stdout") {
      options.stdout = true;
    } else if (argument === "--help" || argument === "-h") {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }
  if (!options.input && !options.help) {
    throw new Error("--input FILE is required.");
  }
  if (options.stdout && options.output) {
    throw new Error("--stdout cannot be used with --output.");
  }
  return options;
}

function usage() {
  return [
    "Usage: node Upcoming_Events/generate_sesh_commands.js --input FILE [--output FILE | --stdout]",
    "",
    "Converts a BrickFair plain-text schedule into Sesh /create commands.",
    "--input FILE   Read a schedule generated by parse_brickfair_schedule.js.",
    "--output FILE  Save commands to a specific file.",
    "--stdout       Print commands instead of saving them.",
    "--help         Show this help.",
  ].join("\n");
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }

  const schedule = await fs.readFile(options.input, "utf8");
  const output = `${generateSeshCommands(schedule)}\n`;
  if (options.stdout) {
    process.stdout.write(output);
    return;
  }

  const outputPath =
    options.output ??
    path.join(
      path.dirname(options.input),
      `${path.basename(options.input, path.extname(options.input))}_sesh_commands.txt`,
    );
  await fs.writeFile(outputPath, output, "utf8");
  console.log(`Saved Sesh commands to ${outputPath}`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = { generateSeshCommands };
