# Commands of the MeshCore bot

*[Nederlands](COMMANDS.md)*

This is how the **Vip|HA|🤖** bot uses them; your own bot works the same, with the channels you set yourself.

The bot answers in the language you write in: Dutch, English, German or French. The command words themselves stay the
same in every language (many are Dutch, such as `pad`, `buien` or `herinner`).

**How to use them:** type the command in `#bot` or `#test`, or send it to the bot as a DM. In the public channel
(channel 0) the bot does not answer commands. More about one command: `help <command>`, for example `help dx`.

Signs: **DM** = direct message only · **#f1** = in the #f1 channel or by DM · 🌐 = needs the internet

## Contents

- [Basics and help](#basics-and-help)
- [Mesh and radio](#mesh-and-radio)
- [Games and community](#games-and-community)
- [Farm](#farm)
- [Formula 1](#formula-1)
- [Useful (Netherlands and Belgium)](#useful-netherlands-and-belgium)
- [Weather, sun and space](#weather-sun-and-space)
- [Fun](#fun)

## Basics and help

| Command | Example | What it does |
|---|---|---|
| `ping` | `ping` | Quick check: the bot answers 'Pong!', with a pointer to `test` for more. |
| `test`<br><sub>also: t</sub> | `test [phrase]` | Connection info of your message: route, bytes per hop (1, 2 or 3), SNR, RSSI and time. |
| `hello`<br><sub>also: hi, hey, hola, bonjour, ...</sub> | `hello` | Greets you back (robot style). Note: 'hallo' is not one of them. |
| `help` | `help  /  help 2  /  help dx` | List of commands per page, or help about one command. |
| `helpall` | `helpall` | The full command list, the next page each time. |
| `cmd`<br><sub>also: cmds, commands</sub> | `cmd` | Short list of the available commands. |
| `version`<br><sub>also: ver</sub> | `version` | Which version of the bot is running. |
| `contact` | `contact` | Contact details of the bot. |
| `channels`<br><sub>also: channel</sub> | `channels [list\|#channel]` | Overview of known hashtag channels. |
| `dm` | `dm` | Type it in a channel: the bot sends you a DM, so you can use it privately from then on. |
| `info bot`<br><sub>also: infobot</sub> | `info bot` | What this bot is and what you need for a bot of your own. **DM** |

## Mesh and radio

| Command | Example | What it does |
|---|---|---|
| `pad` | `pad` | The route of your message in one line: hops, km and repeaters (? = guess). |
| `sig`<br><sub>also: signaal</sub> | `sig` | SNR, RSSI and hops of your message with a verdict (good/fair/weak). Handy when tuning an antenna. |
| `path`<br><sub>also: decode, route</sub> | `path  /  path 4a,c2,8c` | Long version of the route: every repeater on its own line. Long replies get (1/2), (2/2); *Max hops shown* on the *path* card makes it shorter. |
| `trace`<br><sub>also: tracer</sub> | `trace [path]` | Trace along a path (there and back), with the signal per step. |
| `multitest`<br><sub>also: mt</sub> | `multitest` | Listens for 6 seconds and shows every route your message came in by. |
| `prefix`<br><sub>also: lookup</sub> | `prefix 4a` | Which repeaters have a given prefix, with their location. 🌐 |
| `meshkaart`<br><sub>also: nodes</sub> | `meshkaart` | How many nodes, repeaters and rooms the bot hears (24 hours, 7 days, ever). |
| `whois` | `whois <name or key>` | Contact card of a known node, with level and title in Mesh RPG. |
| `rptr` | `rptr  /  rptr buren  /  rptr accu 7d` | Status of the admin's repeater: battery, uptime, airtime, neighbours. |
| `stats` | `stats [messages\|channels\|paths\|adverts]` | Statistics of the last 24 hours. |
| `topu` | `topu  /  topu 7` | Top 5 most active users (24 hours or N days), without bots. |
| `topr` | `topr  /  topr 7` | Top 3 busiest repeaters. |
| `topc` | `topc  /  topc 7` | Top 5 most used commands. |
| `uptime` | `uptime` | How long the bot has been running. |

## Games and community

| Command | Example | What it does |
|---|---|---|
| `dx` | `dx  /  dx top [week\|maand\|ooit]  /  dx ik` | DX hunt: records for the message with the most hops, per week, month and ever. |
| `xp`<br><sub>also: level</sub> | `xp  /  xp <name>  /  xp top [week]` | Mesh RPG: XP, level and title. You earn XP with messages, commands, check-ins, karma and DX. |
| `badge`<br><sub>also: badges</sub> | `badge  /  badge <name>` | Mesh RPG: the milestones you reached (messages, active days, hops, streaks, karma, levels). |
| `karma`<br><sub>also: topkarma</sub> | `karma <name>  /  karma  /  karma top` | Thank someone with a point (max 3 a day, not yourself or a bot). |
| `checkin`<br><sub>also: meld, inchecken</sub> | `checkin  /  checkin top` | Check in daily and build a streak. |
| `voorspel` | `voorspel  /  voorspel nieuw Question? \| yes \| no  /  voorspel 1` | Prediction game for any question. Asking and answering by DM; 1 point for a right answer. |
| `peiling`<br><sub>also: kies</sub> | `peiling Where do we eat? \| pizza \| fries  →  kies 2` | Multiple-choice poll in a channel (2 to 5 choices), vote with kies <nr>. |
| `stem`<br><sub>also: poll, ja, nee</sub> | `stem 15m pizza tonight?  →  ja / nee` | Yes/no vote in a channel. |
| `prikbord` | `prikbord  /  prikbord pump to lend  /  prikbord weg 3` | Notice board: short messages that stay for 7 days. |
| `quiz` | `quiz` | Quiz question in the channel. |
| `hangman` | `hangman` | Hangman in the channel. |
| `dice` | `dice 2d6` | Roll dice. |
| `roll` | `roll 100` | Random number from 1 up to the number. |
| `magic8` | `magic8 Will it stay dry?` | The Magic 8-Ball answers a yes/no question. |

## Farm

A farming game you play **by DM** with the bot (so the bot knows it is you). Sow crops, harvest them, process them in
your workshop into something worth more, sell, save in the bank and grow from level 1 to 10.

| Command | Example | What it does |
|---|---|---|
| `farm` | `farm` | Your status: level, coins, bank, what is ripe and when the rest is. **DM** |
| `farm start` | `farm start` | Start your farm: 4 fields and 200 coins. **DM** |
| `farm shop`<br><sub>also: winkel</sub> | `farm shop` | The seeds you can buy at your level, with price and growing time. **DM** |
| `farm sow`<br><sub>also: plant, zaai</sub> | `farm sow tomato 4` | Sow on your empty fields. Your own seeds go first, you buy the rest. **DM** |
| `farm harvest`<br><sub>also: oogst</sub> | `farm harvest` | Harvest everything that is ripe; it goes to your barn. **DM** |
| `farm barn` | `farm barn` | What is in your barn: crops, products and seeds. **DM** |
| `farm sell` | `farm sell`  /  `farm sell jam` | Sell everything, or one kind. **DM** |
| `farm make`<br><sub>also: verwerk</sub> | `farm make soup 2` | Make a product from your crops in the workshop (see the table). **DM** |
| `farm bank` | `farm bank`  /  `farm deposit 500`  /  `farm withdraw all` | Your savings: 1% interest a day (max 500 a day), safe from the pickpocket. **DM** |
| `farm upgrade` | `farm upgrade`  /  `farm upgrade greenhouse` | An extra field, a better greenhouse (faster), better soil (bigger crops) or a bigger workshop. **DM** |
| `farm give` | `farm give Alex 100` | Give coins to another farmer. **DM** |
| `farm top` | `farm top` | The richest farmers (coins + bank). Also works in `#games`. |

**Crops and products**

| Level | Crop | Seed | Grows | Yield per harvest | Harvests | Made into |
|---|---|---|---|---|---|---|
| 1 | tomato | 20 | 1 h | 2–4 × 3 | 10× | tomato soup (4 tomato, 1 h), pasta (8 tomato, 3 h) |
| 2 | strawberry | 60 | 2 h | 3–5 × 6 | 8× | jam (5 strawberry, 2 h) |
| 3 | pumpkin | 150 | 4 h | 1–2 × 40 | 6× | jack-o'-lantern (1 pumpkin, 1 h) |
| 4 | weed | 300 | 6 h | 2–3 × 50 | 5× | joint (2 weed, 1 h) |
| 5 | grape | 500 | 8 h | 4–6 × 45 | 8× | wine (6 grape, 12 h) |
| 6 | sunflower | 800 | 10 h | 3–5 × 95 | 6× | oil (3 sunflower, 4 h) |
| 7 | apple | 1200 | 12 h | 5–7 × 100 | 10× | apple pie (4 apple, 3 h) |
| 8 | hops | 2000 | 16 h | 4–6 × 210 | 8× | beer (3 hops, 8 h) |
| 9 | coffee | 3500 | 20 h | 3–5 × 430 | 8× | espresso (2 coffee, 2 h) |
| 10 | cocoa | 6000 | 24 h | 3–5 × 700 | 8× | chocolate (2 cocoa, 6 h) |

- Yield: number of pieces × selling price per piece. After the last harvest the plant is used up and the field is empty.
- Every harvested piece has a 1% chance of a **seed**: a free seed for next time.
- Your level rises with XP from harvesting and processing; every level brings a new crop.
- Sometimes something happens at harvest time: a **bumper crop** (double), a **storm** (one field lost), a **pickpocket**
  (10% of your coins, not of the bank) or an **inspection** when you harvest weed.
- A bot owner can switch crops off (card *farm*), for example weed.

## Formula 1

Works in the `#f1` channel and by DM. The data comes from Home Assistant's F1 integration (f1_sensor).

| Command | Example | What it does |
|---|---|---|
| `f1`<br><sub>also: next</sub> | `f1` | The next race: name, place and the start times of the weekend. **#f1** |
| `f1 standings`<br><sub>also: stand, wk</sub> | `f1 standings` | Drivers' championship (top 10). **#f1** |
| `f1 constructors`<br><sub>also: team, teams</sub> | `f1 constructors` | Constructors' championship (top 10). **#f1** |
| `f1 driver`<br><sub>also: coureur</sub> | `f1 driver VER`  /  `f1 driver verstappen`  /  `f1 driver 1` | One driver: championship place, points, wins, team and racing number. **#f1** |
| `f1 result`<br><sub>also: uitslag</sub> | `f1 result` | Result of the last race. **#f1** |
| `f1 sprint` | `f1 sprint` | Result of the last sprint race. **#f1** |
| `f1 weekend`<br><sub>also: schedule, times</sub> | `f1 weekend` | All sessions of the next race weekend in your time: practice, qualifying, sprint and race. **#f1** |
| `f1 grid`<br><sub>also: start</sub> | `f1 grid` | The starting grid (top 10) after qualifying; before that the bot says when qualifying is. **#f1** |
| `f1 calendar`<br><sub>also: kalender, races</sub> | `f1 calendar` | The coming races with date and time. **#f1** |
| `f1 live`<br><sub>also: now, nu</sub> | `f1 live` | During a session: which session, lap, flag and the front of the field. **#f1** |
| `f1 weather`<br><sub>also: weer</sub> | `f1 weather` | During a session: air and track temperature, humidity, wind and whether it rains. **#f1** |
| `f1 pit`<br><sub>also: pitstops</sub> | `f1 pit` | During a session: the latest pit stops with lap and stationary time. **#f1** |
| `f1 predict`<br><sub>also: voorspel</sub> | `f1 predict VER`  /  `f1 predict VER NOR LEC` | Predict the winner, or your top 3 in order, with the three-letter code. **DM** |
| `f1 game`<br><sub>also: spel, punten</sub> | `f1 game` | Standings of the prediction game this season. **#f1** |
| `f1 me`<br><sub>also: ik</sub> | `f1 me` | Your own points, your place and your prediction for the next race. **DM** |

`f1 live`, `f1 weather` and `f1 pit` only work during a session. Outside one, the bot says how long until the next
session starts, for example "The qualifying starts in 2:15 h".

**The prediction game**
- You predict by DM to the bot (it carries your key, so nobody can play in your name).
- You can change your prediction until the first qualifying session of the weekend starts; the last one counts.
- **Winner only** (`f1 predict VER`): right = **5 points**, your driver finished 2nd or 3rd = **2 points**.
- **Your top 3** (`f1 predict VER NOR LEC`): per driver on the right place **5 points**, in the top 3 but on another
  place **2 points**, and **3 extra points** when all three are exactly right. So at most 18 points a race.
- Points are added after the race; `f1 game` shows the standings. Each bot can change the points (card *F1*).

## Useful (Netherlands and Belgium)

| Command | Example | What it does |
|---|---|---|
| `herinner`<br><sub>also: remind</sub> | `herinner 30m pizza  /  herinner 18:30 antenna  /  herinner lijst` | Personal reminder, you get a DM at the time you chose. **DM** |
| `noodnummers`<br><sub>also: nood</sub> | `noodnummers` | 112 and the regional help numbers. Asked in a channel, the answer comes as a DM. |
| `aed` | `aed Heerlen` | The nearest AEDs. Asked in a channel, the answer comes as a DM. 🌐 |
| `buien`<br><sub>also: buienradar</sub> | `buien  /  buien Weert` | Rain in the next 2 hours, per 10 minutes (Buienradar). 🌐 |
| `weerwaarschuwing`<br><sub>also: gladheid</sub> | `weerwaarschuwing` | Current KNMI weather warning. 🌐 |
| `beving` | `beving` | Recent earthquakes in and around the Netherlands (KNMI). 🌐 |
| `storing` | `storing kpn` | Outages at a telecom provider. 🌐 |
| `file` | `file Maastricht` | Traffic jams and accidents near a place. 🌐 |
| `wegwerk` | `wegwerk Sittard` | Road works near a place. 🌐 |
| `ov` | `ov Heerlen station` | Next public transport departures. 🌐 |
| `tanken` | `tanken` | Today's national average fuel prices (CBS). 🌐 |
| `laadpaal` | `laadpaal Kerkrade` | EV charging points nearby. 🌐 |
| `energieprijs` | `energieprijs` | Current dynamic electricity price. 🌐 |
| `waterstand` | `waterstand` | Water level of the Meuse (Maas). 🌐 |
| `straling` | `straling Maastricht` | Indicative radiation level. 🌐 |
| `kenteken` | `kenteken HDJ-60-R` | Look up a Dutch number plate (RDW). Belgian and German plates are not supported (no free source). 🌐 |
| `feestdag`<br><sub>also: vandaag</sub> | `feestdag` | Public holidays in the Netherlands and Belgium. |

## Weather, sun and space

| Command | Example | What it does |
|---|---|---|
| `wx`<br><sub>also: weather</sub> | `wx Heerlen  /  wx Heerlen 7d` | Weather forecast for a place. 🌐 |
| `rain`<br><sub>also: nowcast, snow</sub> | `rain Heerlen` | When it will rain or snow (also outside NL/BE). 🌐 |
| `aqi`<br><sub>also: air, airquality</sub> | `aqi Maastricht` | Air quality for a place. 🌐 |
| `sun` | `sun` | Sunrise and sunset. |
| `moon` | `moon` | Moon phase and moonrise/moonset. |
| `aurora`<br><sub>also: kp</sub> | `aurora` | Northern lights forecast (KP index). 🌐 |
| `solar` | `solar` | Solar conditions and HF bands. 🌐 |
| `hfcond` | `hfcond` | HF band conditions for radio amateurs. 🌐 |
| `solarforecast`<br><sub>also: sf</sub> | `sf Heerlen 4000` | Expected yield of solar panels. 🌐 |
| `satpass` | `satpass iss` | When a satellite passes over. 🌐 |
| `airplanes`<br><sub>also: planes, aircraft</sub> | `airplanes`  /  `airplanes here`  /  `airplanes 50.9,5.9` | Aircraft above the bot (or a place), with altitude and type. Off by default (card *airplanes*). 🌐 |
| `alert`<br><sub>also: incident</sub> | `alert <place>` | Active emergency incidents (PulsePoint, mainly US). 🌐 |

## Fun

| Command | Example | What it does |
|---|---|---|
| `weetje`<br><sub>also: wistje</sub> | `weetje` | A random fun fact (in Dutch). |
| `quote`<br><sub>also: citaat</sub> | `quote` | A random quote. |
| `joke`<br><sub>also: jokes</sub> | `joke` | A random joke. 🌐 |
| `dadjoke` | `dadjoke` | A dad joke. 🌐 |
| `morse` | `morse SOS` | Text to Morse code and back. |
| `sudo`<br><sub>also: ls -la, rm -rf, ...</sub> | `sudo make coffee` | Pretends you are hacking a villain's computer. |
| `catfact`<br><sub>also: cat, meow</sub> | `catfact` | A cat fact (hidden command). 🌐 |
| `sports`<br><sub>also: score, scores</sub> | `sports ajax` | Sports results and fixtures. 🌐 |

## Games, good to know

- **XP (Mesh RPG):** 1 per message (max 20 a day), 2 per command (max 10 a day), 5 per check-in, 10 per karma point you receive, 5 per hop of your best DX (up to 10 hops, so max 50). What you write in the public channel counts too.
- **Games channel:** a bot can keep the games in one channel (card *GamesChannel*). The **Vip|HA|🤖** bot does: `quiz`, `hangman`, `stem`, `peiling`, `checkin`, `karma`, `voorspel`, `xp` and `dx` work in **`#games`** and by DM; in other channels the bot tells you where to go. XP keeps counting in every channel.
- **Bots do not take part**: they are not in the rankings, cannot predict in the F1 game, and `xp`, `dx` or `badge` with a bot's name answers that bots don't take part.
- `voorspel`, `herinner` and `f1 voorspel` go by DM: it carries your key, so nobody can play in your name.
