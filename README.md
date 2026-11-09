# Good Flight Deals ✈️

> 🚧 **Work in progress.** The core works: it searches, spots deals and remembers prices. Alerts only
> print to the terminal for now, and there's no built-in scheduler yet.

A small personal tool that checks for cheap flights once a day and tells you when it finds a deal.

You list the airports you're happy to fly from. It asks Google Flights for the cheapest return
trips to anywhere, then flags anything that's either really cheap or much cheaper than usual for
that destination.

## What it looks like

An illustrative alert. The fares are based on real search results, but the "usually £…" price
history is made up to show the format:

```
3 flight deals found:

£29  Belfast, United Kingdom (BFS)  Sun 13 Dec - Sat 19 Dec  easyJet, direct, 1h05
    £30 or less
£56  Antalya, Türkiye (AYT)  Mon 22 Feb - Mon 08 Mar  easyJet, direct, 4h15
    usually £84 (normally £73-£97), 33% off, lowest in 21 days tracked
£380  Bangkok, Thailand (BKK)  Sat 21 Nov - Mon 07 Dec  Turkmenistan and Norse, 1 stop(s), 14h55
    usually £440 (normally £419-£463), 14% off, lowest in 23 days tracked
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
| `max_price` (per search) | Always alert at or below this price | £30 for Europe |
| `min_zscore` | How unusual a price must be for its route | 2 |
| `min_saving_pct` | And how big the saving must be | 12% |
| `alert_cooldown_days` | Don't repeat an alert unless the price drops further | 14 days |
| `monthly_search_limit` | Hard stop on API calls so you stay in the free tier | 240 |

### Searches

Each `[[searches]]` block is one search per run. The defaults are:

| Search | Trip | Stops | Flight time |
|---|---|---|---|
| `europe` | 1 week | up to 1 | any |
| `asia` (incl. Middle East and Turkey) | 2 weeks | up to 1 | 4–24 hours |
| `africa` | 2 weeks | up to 1 | 4–24 hours |

North America, South America and the Caribbean are in the config too, commented out. Each search
uses about 31 API calls a month, so 3 searches fit comfortably in the free tier.

Flight time is one way and includes layovers, so the 24-hour cap filters out "1 stop" trips
with a 20-hour wait at the airport.

## How it decides what's a deal

Each run saves every price it sees, and over time it learns two things about each route: its
**typical price** and **how much it normally moves** day to day. A fare is a deal if either:

1. it's **unusually cheap for that route**: at least 2 "normal swings" below typical, *and*
   at least 12% cheaper, **or**
2. it's at or below the search's `max_price`.

Why not just "X% below typical"? Because routes behave differently (illustrative numbers):

| Route | Usual prices | Today | Verdict |
|---|---|---|---|
| Barcelona | £30–£70, all over the place | £33 | Not a deal: it's been this cheap before |
| Bangkok | £430–£450, very steady | £380 | **Deal**: far outside its normal range |

Alerts say why:

```
£380  Bangkok, Thailand (BKK)  ...
    usually £440 (normally £419-£463), 14% off, lowest in 23 days tracked
```

<details>
<summary>The maths</summary>

For each route, take the cheapest price per day over the last 60 days (needs at least 7 days),
then score today's price:

```
z = (log(price) − median(log prices)) / (1.4826 × MAD(log prices))
```

- **Log prices** make it proportional: £20 off a £40 flight matters more than £20 off £600.
- **Median and MAD** (median absolute deviation) instead of mean and standard deviation, so one
  glitchy price can't wreck the baseline.
- The spread has a 5% floor, so a route stuck at one price for weeks doesn't flag a £1 dip.
- Every fare's score is saved, so the thresholds can be tuned against real data later.

It's deliberately not ML: there's one number per route per day and no labelled "good deals" to
learn from, so a model would mostly learn noise.

</details>

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
- [x] Long-haul destinations (filtered by stops and flight time)
- [x] Price ceiling per search
- [x] Statistical deal detection per route
- [ ] Tune thresholds from a few weeks of saved scores
- [ ] Seasonal baselines (once there's a year of data)
- [ ] Show which airport each deal departs from

## Development

```sh
uv run pytest                                      # tests
uv run ruff check . && uv run ruff format --check .  # lint and formatting
```
