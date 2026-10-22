# BrickFair schedule parser

Run with Node.js 18 or newer:

```sh
node Upcoming_Events/parse_brickfair_schedule.js
```

The script fetches the current [BrickFair AFOL schedule](https://www.brickfair.com/afol/schedule/) and saves a plain-text schedule grouped by day. Public-hours starts and ends, exhibitor hall openings and closings, special access alerts such as Adult Swim (including overnight end times), and scheduled events are placed together in chronological order. The teardown-start marker appears only after the final day's public hours end. Inline event subtitles are included with their titles. By default, it creates a file named `EVENT_YEAR_RETRIEVALDATE.txt` in `Upcoming_Events/`, using the event venue shown on the page (for example, `BrickFair_Oaks_2026_2026-10-17.txt`). Events that start at the same time are listed on separate lines, with each simultaneous follow-on prefixed by a tab and `AND`; locations are included with a plain hyphen, and presenters are included when listed. Fetched HTML is cached locally for 24 hours so repeated runs do not keep contacting the site.

Use `--stdout` to print the formatted schedule to the console instead, `--output FILE` to choose an explicit output file, or `--input FILE` to parse a previously saved HTML page without making a network request. Use `--refresh` to fetch and cache a fresh copy, `--no-cache` to bypass the cache for a run, or `--cache-file FILE` to choose a different cache location. The default cache lives outside the repository in the operating system's user cache directory. Run with `--help` for all available options.

Run the parser tests with:

```sh
node --test Upcoming_Events/parse_brickfair_schedule.test.js
```

To turn a generated schedule file into Sesh `/create` commands:

```sh
node Upcoming_Events/generate_sesh_commands.js --input Upcoming_Events/BrickFair_Oaks_2026_2026-10-17.txt
```

The command list is saved beside the input with `_sesh_commands.txt` appended to its filename. Use `--output FILE` to choose another path or `--stdout` to print the commands. Every timed entry is included, including hours markers, alerts, and simultaneous events. Overnight entries are assigned to the following calendar day. Every event datetime explicitly specifies EST. Locations and presenters are placed in Sesh's corresponding optional fields, and overlong event titles are shortened to Sesh's 64-character limit with the full text retained in the description.

Run the command generator tests with:

```sh
node --test Upcoming_Events/generate_sesh_commands.test.js
```
