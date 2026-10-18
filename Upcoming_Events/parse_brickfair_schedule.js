#!/usr/bin/env node
"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");

const SCHEDULE_URL = "https://www.brickfair.com/afol/schedule/";

function decodeEntities(text) {
  const named = {
    amp: "&",
    apos: "'",
    gt: ">",
    lt: "<",
    nbsp: " ",
    quot: '"',
  };
  return text.replace(/&(#(?:x[0-9a-f]+|[0-9]+)|[a-z]+);/gi, (entity, code) => {
    if (code[0] !== "#") return named[code.toLowerCase()] ?? entity;

    const hexadecimal = code[1].toLowerCase() === "x";
    const number = Number.parseInt(
      code.slice(hexadecimal ? 2 : 1),
      hexadecimal ? 16 : 10,
    );
    if (!Number.isInteger(number) || number < 0 || number > 0x10ffff) return entity;
    try {
      return String.fromCodePoint(number);
    } catch {
      return entity;
    }
  });
}

function textContent(html) {
  return decodeEntities(html.replace(/<!--[\s\S]*?-->/g, "").replace(/<[^>]*>/g, " "))
    .replace(/\s+/g, " ")
    .trim();
}

function hasClass(attributes, className) {
  const match = attributes.match(/\bclass\s*=\s*(["'])(.*?)\1/i);
  return match !== null && match[2].split(/\s+/).includes(className);
}

function getAttribute(tag, attributeName) {
  const escapedName = attributeName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = tag.match(
    new RegExp(`\\b${escapedName}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, "i"),
  );
  return match ? match[1] ?? match[2] : null;
}

function extractDiv(html, start) {
  const openingEnd = html.indexOf(">", start);
  if (openingEnd < 0) throw new Error("Found an incomplete div opening tag.");

  let depth = 1;
  const divTags = /<\/?div\b[^>]*>/gi;
  divTags.lastIndex = openingEnd + 1;
  let match;
  while ((match = divTags.exec(html)) !== null) {
    if (match[0][1] === "/") {
      depth -= 1;
      if (depth === 0) {
        return { html: html.slice(start, divTags.lastIndex), end: divTags.lastIndex };
      }
    } else if (!/\/\s*>$/.test(match[0])) {
      depth += 1;
    }
  }
  throw new Error("Found a div with no matching closing tag.");
}

function getClassText(html, className) {
  const tags = /<([a-z][\w:-]*)\b([^>]*)>/gi;
  let match;
  while ((match = tags.exec(html)) !== null) {
    if (!hasClass(match[2], className)) continue;
    const closingTag = new RegExp(`</${match[1]}\\s*>`, "ig");
    closingTag.lastIndex = tags.lastIndex;
    const closing = closingTag.exec(html);
    if (!closing) return "";
    return textContent(html.slice(tags.lastIndex, closing.index));
  }
  return "";
}

function getFirstTagText(html, tagName) {
  const tag = new RegExp(`<${tagName}\\b[^>]*>([\\s\\S]*?)</${tagName}\\s*>`, "i");
  const match = html.match(tag);
  return match ? textContent(match[1]) : "";
}

function getInputValue(html, className) {
  const inputs = /<input\b[^>]*>/gi;
  let match;
  while ((match = inputs.exec(html)) !== null) {
    if (!hasClass(match[0], className)) continue;
    return getAttribute(match[0], "value");
  }
  return null;
}

function findDays(html) {
  const days = [];
  const paragraphs = /<p\b([^>]*)>([\s\S]*?)<\/p>/gi;
  let paragraph;
  while ((paragraph = paragraphs.exec(html)) !== null) {
    if (!hasClass(paragraph[1], "pWeekday")) continue;

    const weekday = textContent(paragraph[2]);
    const divTags = /<div\b([^>]*)>/gi;
    divTags.lastIndex = paragraphs.lastIndex;
    let opening;
    let found = false;
    while ((opening = divTags.exec(html)) !== null) {
      if (!hasClass(opening[1], "divWeekday")) continue;
      const block = extractDiv(html, opening.index);
      const date = getAttribute(opening[0], "data-date");
      if (!date) throw new Error(`The ${weekday} schedule has no date.`);
      days.push({ weekday, date, html: block.html });
      paragraphs.lastIndex = block.end;
      found = true;
      break;
    }
    if (!found) throw new Error(`Could not find the schedule section for ${weekday}.`);
  }
  return days;
}

function findEvents(dayHtml, weekday) {
  const events = [];
  const divTags = /<div\b([^>]*)>/gi;
  let opening;
  while ((opening = divTags.exec(dayHtml)) !== null) {
    if (!hasClass(opening[1], "Gamvent")) continue;
    const block = extractDiv(dayHtml, opening.index);
    divTags.lastIndex = block.end;

    const title =
      getClassText(block.html, "gmName") || getFirstTagText(block.html, "small");
    const hourText = getInputValue(block.html, "Hour");
    const minuteText = getInputValue(block.html, "Minute");
    if (!title || hourText === null || minuteText === null) {
      throw new Error(
        `Found an incomplete event in the ${weekday} schedule: ` +
          `title="${title}", hour="${hourText}", minute="${minuteText}".`,
      );
    }
    const hour = Number(hourText);
    const minute = Number(minuteText);
    if (
      !Number.isInteger(hour) ||
      hour < 0 ||
      hour > 23 ||
      !Number.isInteger(minute) ||
      minute < 0 ||
      minute > 59
    ) {
      throw new Error(`Found an invalid start time for "${title}" on ${weekday}.`);
    }

    events.push({
      hour,
      minute,
      title,
      location: getClassText(block.html, "Rtyu"),
      presenter: getClassText(block.html, "Comic"),
    });
  }
  return events;
}

function formatDate(date) {
  const match = date.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return date;
  const [, month, day, year] = match;
  const parsed = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  if (
    parsed.getUTCFullYear() !== Number(year) ||
    parsed.getUTCMonth() !== Number(month) - 1 ||
    parsed.getUTCDate() !== Number(day)
  ) {
    return date;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function formatTime(hour, minute) {
  const period = hour < 12 ? "AM" : "PM";
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${String(minute).padStart(2, "0")} ${period}`;
}

function formatEvent(event) {
  let details = event.location ? ` — ${event.location}` : "";
  if (event.presenter) details += ` (presenter: ${event.presenter})`;
  return `${event.title}${details}`;
}

function parseSchedule(html) {
  const days = findDays(html);
  if (days.length === 0) throw new Error("No schedule days were found in the page.");

  return days
    .map(({ weekday, date, html: dayHtml }) => {
      const events = findEvents(dayHtml, weekday);
      const byTime = new Map();
      for (const event of events) {
        const key = event.hour * 60 + event.minute;
        if (!byTime.has(key)) byTime.set(key, []);
        byTime.get(key).push(event);
      }

      const lines = [...byTime.entries()]
        .sort(([left], [right]) => left - right)
        .map(([minutes, simultaneous]) => {
          const time = formatTime(Math.floor(minutes / 60), minutes % 60);
          return `${time}: ${simultaneous.map(formatEvent).join("\nAND ")}`;
        });
      return [`${weekday}, ${formatDate(date)}`, ...lines].join("\n");
    })
    .join("\n\n");
}

async function fetchSchedule(url) {
  let response;
  try {
    response = await fetch(url, {
      headers: {
        Accept: "text/html",
        "User-Agent": "Mozilla/5.0 (compatible; BrickFairScheduleParser/1.0)",
      },
    });
  } catch (error) {
    throw new Error(`Could not fetch ${url}: ${error.message}`);
  }
  if (!response.ok) {
    throw new Error(`Fetching ${url} failed with HTTP ${response.status}.`);
  }
  return response.text();
}

function parseArguments(args) {
  const options = { input: null, output: null };
  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (argument === "--help" || argument === "-h") {
      options.help = true;
    } else if (argument === "--input" || argument === "--output") {
      const value = args[index + 1];
      if (!value || value.startsWith("-")) throw new Error(`${argument} requires a path.`);
      options[argument === "--input" ? "input" : "output"] = value;
      index += 1;
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }
  return options;
}

function usage() {
  return [
    "Usage: node Upcoming_Events/parse_brickfair_schedule.js [--input FILE] [--output FILE]",
    "",
    `Fetches ${SCHEDULE_URL} by default and prints a day-grouped plain-text schedule.`,
    "--input FILE   Parse a saved HTML page instead of fetching the live schedule.",
    "--output FILE  Write the text to a file instead of standard output.",
    "--help         Show this help.",
  ].join("\n");
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }

  const html = options.input
    ? await fs.readFile(options.input, "utf8")
    : await fetchSchedule(SCHEDULE_URL);
  const output = `${parseSchedule(html)}\n`;
  if (options.output) {
    const outputPath = path.resolve(options.output);
    await fs.mkdir(path.dirname(outputPath), { recursive: true });
    await fs.writeFile(outputPath, output, "utf8");
    console.log(`Saved schedule to ${outputPath}`);
  } else {
    process.stdout.write(output);
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = { parseSchedule };
