# BrickFair schedule parser

Run with Node.js 18 or newer:

```sh
node Upcoming_Events/parse_brickfair_schedule.js
```

The script fetches the current [BrickFair AFOL schedule](https://www.brickfair.com/afol/schedule/) and saves a plain-text schedule grouped by day. Public-hours starts and ends, exhibitor hall openings and closings, and scheduled events are placed together in chronological order. By default, it creates a file named `EVENT_YEAR_RETRIEVALDATE.txt` in `Upcoming_Events/` (for example, `BrickFair_LEGO_Expo_2026_2026-10-17.txt`). Events that start at the same time are listed on separate lines, with each additional event prefixed by `AND`; locations and presenters are included when listed. Fetched HTML is cached locally for 24 hours so repeated runs do not keep contacting the site.

Use `--stdout` to print the formatted schedule to the console instead, `--output FILE` to choose an explicit output file, or `--input FILE` to parse a previously saved HTML page without making a network request. Use `--refresh` to fetch and cache a fresh copy, `--no-cache` to bypass the cache for a run, or `--cache-file FILE` to choose a different cache location. The default cache lives outside the repository in the operating system's user cache directory. Run with `--help` for all available options.

Run the parser tests with:

```sh
node --test Upcoming_Events/parse_brickfair_schedule.test.js
```
