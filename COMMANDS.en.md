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
| `path`<br><sub>also: decode, route</sub> | `path  /  path 4a,c2,8c` | Long version of the route: every repeater on its own line. |
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

## Formula 1

| Command | Example | What it does |
|---|---|---|
| `f1` | `f1  /  f1 stand  /  f1 uitslag  /  f1 nu  /  f1 kalender  /  f1 voorspel VER  /  f1 spel` | Next race, championship standings, result, live session, the coming races and the F1 prediction game: the winner (`f1 voorspel VER`) or your top 3 (`f1 voorspel VER NOR LEC`), by DM. **#f1** |

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
