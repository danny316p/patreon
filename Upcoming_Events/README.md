# BrickFair schedule parser

Run with Node.js 18 or newer:

```sh
node Upcoming_Events/parse_brickfair_schedule.js
```

The script fetches the current [BrickFair AFOL schedule](https://www.brickfair.com/afol/schedule/) and prints a plain-text schedule grouped by day. Events that start at the same time are listed on separate lines, with each additional event prefixed by `AND`; locations and presenters are included when listed. Fetched HTML is cached locally for 24 hours so repeated runs do not keep contacting the site.

Use `--output FILE` to save the formatted schedule instead of printing it, or `--input FILE` to parse a previously saved HTML page without making a network request. Use `--refresh` to fetch and cache a fresh copy, `--no-cache` to bypass the cache for a run, or `--cache-file FILE` to choose a different cache location. The default cache lives outside the repository in the operating system's user cache directory. Run with `--help` for all available options.

Run the parser tests with:

```sh
node --test Upcoming_Events/parse_brickfair_schedule.test.js
```
