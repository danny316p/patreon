# BrickFair schedule parser

Run with Node.js 18 or newer:

```sh
node Upcoming_Events/parse_brickfair_schedule.js
```

The script fetches the current [BrickFair AFOL schedule](https://www.brickfair.com/afol/schedule/) and prints a plain-text schedule grouped by day. Events that start at the same time are joined with `AND`; locations and presenters are included when listed.

Use `--output FILE` to save the formatted schedule instead of printing it, or `--input FILE` to parse a previously saved HTML page without making a network request. Run with `--help` for the available options.

Run the parser tests with:

```sh
node --test Upcoming_Events/parse_brickfair_schedule.test.js
```
