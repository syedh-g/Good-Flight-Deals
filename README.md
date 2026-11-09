# Good Flight Deals ✈️

> 🚧 **Work in progress.** The core works: it searches, spots deals and remembers prices. Alerts only
> print to the terminal for now, and there's no built-in scheduler yet.

A small personal tool that checks for cheap flights once a day and tells you when it finds a deal.

You list the airports you're happy to fly from. It asks Google Flights for the cheapest return
trips to anywhere, then flags anything that's either really cheap or much cheaper than usual for
that destination.

## What it looks like

```
5 flight deals found:

£32  Cork, Ireland (ORK)  Mon 16 Nov - Tue 24 Nov  Ryanair, direct
    £40 or less
£37  Dublin, Ireland (DUB)  Fri 08 Jan - Thu 14 Jan  Ryanair, direct
    £40 or less
£39  Naples, Italy (NAP)  Sun 06 Dec - Sun 13 Dec  Ryanair, direct
    £40 or less
```

Each deal also comes with a Google Flights link.

## Getting started

**You'll need:**
- [uv](https://docs.astral.sh/uv/), which installs Python and the project for you
- A free [SerpApi](https://serpapi.com/) account (250 searches a month free)

**1. Install**

```sh
git clone https://github.com/syedh-g/Good-Flight-Deals.git
cd Good-Flight-Deals
uv sync
```

**2. Add your API key**

Copy the example secrets file and paste your key into it:

```sh
cp .env.example .env
```

```
SERPAPI_API_KEY=your-key-here
```

`.env` is git-ignored, so your key never gets committed.

**3. Run it**

```sh
uv run flight-deals
```

Add `-v` to see what it's doing.

## Making it yours

Everything is in [`config.toml`](config.toml):

| Setting | What it does | Default |
|---|---|---|
| `origins` | Airports you'll fly from | London (LHR, LGW, STN, LTN), Birmingham, Manchester |
| `max_price` | Always alert at or below this price | £40 |
| `min_drop_pct` | Alert when a fare is this % below its usual price | 25% |
| `alert_cooldown_days` | Don't repeat an alert unless the price drops further | 14 days |
| `monthly_search_limit` | Hard stop on API calls so you stay in the free tier | 240 |

## How it decides what's a deal

Each run saves every price it sees. Over time it learns what's normal for each destination, so a
fare counts as a deal if either:

1. it's at or below your `max_price`, **or**
2. it's at least `min_drop_pct`% cheaper than that destination's usual price.

The second rule starts working after about 5 days of history.

## How it's built

Plain Python with **no runtime dependencies**. Each part has one job and can be swapped out:

```
src/flight_deals/
├── sources/      where flight prices come from (SerpApi today, swappable)
├── deals.py      the "is this a deal?" rules
├── store.py      price history in a local SQLite database
├── notify.py     how you get told (terminal for now)
└── app.py        ties one daily run together
```

## Roadmap

- [ ] Alerts by email, Telegram or push notification
- [ ] Run automatically every day
- [ ] Long-haul destinations
- [ ] Show which airport each deal departs from

## Development

```sh
uv run pytest                                      # tests
uv run ruff check . && uv run ruff format --check .  # lint and formatting
```
