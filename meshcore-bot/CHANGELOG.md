# Changelog

## 1.2.0

- Dashboard: the **Radar** page has two tabs. *Channel radar* is the old page; the new **Repeater radar** lists every
  repeater the bot heard in 24 hours, 7 or 30 days: place and distance, last heard, SNR, hops, adverts, whether the
  bot's radio hears it directly, how many bots of the bot network hear it, and repeaters that share a key byte. Click a tile to show only
  those repeaters (direct, new, shared prefix); click a repeater for everything the bot knows about it (position with a
  map link, first and last heard, best SNR, which bots hear it, and the repeaters that share its prefix).
  "Same prefix" only counts repeaters that are both within 50 km of the bot (a shared byte with a repeater far away
  does not confuse paths). The table shows 50 rows at a time ("Show more"), light enough for RDP or a slow link.
- New card **AutoChannels** (on): hashtag channels the bot is set to use (#test, #games, #f1, ...) that are missing on
  the radio are made there automatically. Never private channels, never removed or overwritten.
- New game: **Kwekerij** (`farm`), played by DM. Sow ten crops (tomato to cocoa, each with its own price, growing
  time and yield), harvest, process them in the workshop (tomato soup, pasta, jam, jack-o'-lantern, joint, wine, oil,
  apple pie, beer, espresso, chocolate), sell, save in the bank (1% interest a day), buy upgrades, give coins, find
  seeds, and level up from 1 to 10; now and then a bumper crop, a storm or a pickpocket. `farm top` also in `#games`,
  standings on the dashboard's Games page. The card *farm* can switch crops off (for example weed).

**Fixes from GitHub issue #1 (second report)**
- config.ini is now visible: at every start the add-on writes `config-current.ini` (a copy to read and compare) and
  `README.txt` in its own folder (`/addon_configs/..._meshcore_bot/` in the File Editor), and reads your own lines from
  `override.ini` there (they win over everything else).
- Plugins page: the on/off switch of a card saves at once (before, the change was lost without pressing Save). When a
  change only works after a restart (a service switched on or off), a banner at the top says so, with a **Restart now**
  button that restarts the add-on; the page reloads itself when the bot is back. The banner stays in sight while
  scrolling.
- airplanes: switched on on its card, it stays on after a restart (the add-on switched it off again at every start).
  Without the Latitude/Longitude options, airplanes (and `airplanes here`) use the position the radio advertises.
- path: long replies are numbered (1/2, 2/2) so the order is clear when the mesh mixes them up, and the path card has
  *Max hops shown* (for example 7; the rest is shown as "+N more hops").
- Documentation: the service DARC MoWaS makes its own channels on the radio (`#mowas`, `#mowas-en`) when it starts.
- Command list: `airplanes` added, `path` explains the numbered parts.
- Channel radar: a channel that is newly recognised (a name added on its card, a channel added on the radio) now also
  counts its messages from the first day in the packet log, without counting anything twice.

## 1.1.1

- More `f1`: `f1 weekend` (all session times), `f1 sprint`, `f1 coureur VER` (a driver's place, points, wins, number),
  `f1 grid` (starting grid after qualifying), `f1 ik` (your own place in the prediction game, by DM), and during a
  session `f1 weer` (track weather) and `f1 pit` (pit stops). Outside a session the live parts say when the next one
  starts. The command list explains the prediction game's points.

## 1.1.0

**English by default** (thanks to the first user report, GitHub issue #1)
- *Bot > Language of the replies* now offers English, Dutch, German and French; new installations start in English.
  Everything this add-on adds follows it: `help <command>` for every extra command, `helpall`, the short `help` list and the
  standard hint texts. The descriptions on the dashboard's Plugins cards are in English.
- `ping` answers "Pong!" with a pointer to `test`, in the bot's language (new installations no longer get a fixed `ping`
  keyword).
- `test` shows the bytes per hop (1, 2 or 3) when known; new keyword placeholder `{bytes_per_hop}`.
- New options: *Command prefix* (for example `/`, so `/test` works; `test` keeps working unless you require it) and the
  bot's *Latitude* / *Longitude* (used by `airplanes`, `wx`, `rain`, `sun`, distances in `test` and the map).
- The help card has a field *Own help text*: a bare `help` then answers exactly that (a `help` keyword is never used).
- `help` links to the English command list (`COMMANDS.en.md`) for someone who writes in English, German or French, when
  the link on the help card points to this repository's `COMMANDS.md`.
- Documentation: where config.ini is and how to change settings without it.

**Fixed**
- `test`: the bytes per hop (for example `| 1B/hop |`) now really shows. The command builds its reply in another place than
  keywords do, and only the keyword route had it. `{bytes_per_hop}` now works in every command template too.
- Greeter: the rollout (a period in which people already active are only remembered, not greeted) now runs once. Upstream
  started a new one by itself every week, so the greeter kept going quiet for a week at a time.

**New**
- `dm`: typed in a channel, the bot sends you a direct message, so you can use it privately from then on (card *dm*: own
  text, wait per person). When your node is not in the radio's contacts yet, it says so and asks for an advert.
- F1 prediction game: predict your top 3 (`f1 voorspel VER NOR LEC`): right place 5, right driver on another place 2, all
  three exactly right +3 (adjustable on the F1 card). One code still predicts the winner, as before.
- Bot network (card *BotNetwork*): bots running this add-on share what their radio hears over the internet (MQTT, no
  airtime, any distance): hello, radio info, an hourly status, channel and bot names, and optionally the repeaters the
  radio hears directly. Signed messages, never message content or private keys. Off by default: switch the card on to
  join. Its own dashboard page *Bot network* (only while the card is on): every bot with its numbers, network
  totals, charts over 24 h / 7 / 30 days, and which repeaters each bot hears directly.
- Install count (card *InstallCount*, **on by default**): once a day one anonymous message (a random number, the
  add-on version and the date) to the maintainer's server, so the maintainer knows how many installations run. Nothing
  about you, your radio or the mesh. Switch the card off to send nothing; see the README.
- GitHub: issue forms for joining the bot network, bug reports and ideas.
- Games channel (card *GamesChannel*, off by default): the game commands only in one channel, for example `#games`, with
  an optional pointer elsewhere; XP keeps counting everywhere.

- `help` in a channel with its own commands (a command card whose *Channels* lists it, such as `#f1` for `f1`) answers with
  the help of just those commands, instead of a pointer to other channels.
- Greeter: end the greeting with `|` to give the mesh info (contacts, repeaters, companions, active in 24 h) its own part.
  A `|` only starts a new message when needed: parts that fit together (up to 130 bytes) go out as one message, one line each.
- Shorter reply to a bare `help`, so the full link to the command list (COMMANDS.md) fits one mesh message in every language.
- Channel radar: the channels on your own radio are recognised by themselves, with their own keys, so private channels and
  hashtag names that are on no list (such as `#public`) show up too. A channel added on the radio is picked up within a minute.
- Channel radar: when it counts the packet log again (new names or channels), the first, partial day of the log keeps its
  count instead of losing the messages from before the log started.
- Bots do not take part anywhere: `xp`, `dx` and `badge` with a bot's name say so, a bot cannot predict in the F1 game, and bots
  never show in the F1 standings.
- Night mode (card *NightMode*, off by default): scheduled messages and feeds stay quiet at night (default 23:00-07:00),
  the webhook too if you want; answers to people always go out.
- `whois` also shows someone's Mesh RPG level, title and XP (not for bots).
- `f1 kalender`: the coming races with date and local time (from the f1_sensor season calendar).
- Dashboard: a new *Repeater* page with the history of your repeater (battery, temperature, noise floor, airtime, SNR,
  neighbours) over 24 hours, 7 or 30 days. The *Channel radar* menu item is now called *Radar*, so the menu fits one line.
- Repeater uptime (`rptr`, Repeater page) is read in the unit Home Assistant gives it: meshcore-ha reports it in days,
  which was read as minutes (a repeater up for 60 days showed "1 h").
- Repeater: uptimes stored in the wrong unit are corrected once, automatically. Neighbours that meshcore-ha gives no
  name get it from the bot's Contacts (also in `rptr buren`); the Repeater page also shows where each neighbour is and how
  far it is from the repeater.
- The command list in English as well (`COMMANDS.en.md`).
- README and installation guide: new repository name and an *Add repository* button.

## 1.0.0

First public release: [agessaman/meshcore-bot](https://github.com/agessaman/meshcore-bot) v1.1.0 as a Home Assistant add-on,
with a Home Assistant layer and extra commands on top.

**Home Assistant**
- Every setting in the add-on options or on the bot's own dashboard (*Plugins* page, one card per command and service); settings
  on the dashboard survive restarts and updates.
- The dashboard in the Home Assistant sidebar (ingress), with extra *Bots* and *Games* pages (click a player to see where the XP comes from; who has predicted the next F1 race). By default it is only reachable
  through the sidebar.
- Works through the MeshCore Proxy add-on, so meshcore-ha and the bot share one radio.
- Optional, each off until switched on: notifications to a room server, channel or DM (and Home Assistant for radio problems), a
  bridge that mirrors replies into the MeshCore Chat panel, an incoming webhook, a heartbeat sensor, the status of your repeater
  from meshcore-ha (`rptr`, with warnings), an F1 channel from the f1_sensor integration.
- **Channel radar** (dashboard page): which hashtag channels are in use around the bot, recognised by channel byte and
  check code against about 200 known names (plus your own on its card), without decrypting anything.
- Export and import of settings and database through `/share/meshcore-bot`, to move the bot to a new installation.
- Room server login with an adjustable re-login interval; as room admin the bot keeps the room's clock right (`clock sync`).

**Commands** (see the command list in the repository README)
- Netherlands and Belgium: traffic jams, road works, public transport, fuel and energy prices, EV chargers, AEDs, KNMI warnings,
  earthquakes, water level, radiation, telecom outages, number plates (RDW), holidays, Buienradar.
- Mesh: route in one line with distance (`pad`), signal with a verdict (`sig`), size of the mesh (`meshkaart`), top users
  (other bots left out), repeaters and commands.
- Community and games: DX Jacht (`dx`), Mesh RPG (`xp`, `badge`), `karma`, daily `checkin`, `prikbord`, `peiling`, `voorspel`,
  reminders by DM (`herinner`), quiz, hangman, polls, facts (`weetje`), quotes, morse.
- `help` pages through all commands, or links to your own command list (help card); `helpall`; admin commands `status`,
  `botlist`, `cleanup`.

**Everywhere**
- Replies in the language the sender writes in (Dutch, English, German, French; optional *AutoLanguage*); Dutch, German and French
  cover all of upstream's texts too.
- Other bots are recognised (robot emoji or the word bot, plus a list on the *Bots* page): no greeting for them, no endless
  replies between bots, not in the rankings.
- In a busy public channel the bot runs no commands but points people to the right channel, with varying texts.
- Contact cleanup that keeps room on the radio, a lasting archive for the games, a small image (13 layers) and a test suite
  that replays the whole build on the upstream source.
