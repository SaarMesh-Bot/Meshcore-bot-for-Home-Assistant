# Changelog

## 1.5.1-sm.2

- `warnung`: DWD and NINA districts that do not answer are asked once more; when a source still fails the reply says
  which one (DWD, or NINA with the number of districts).
- InstallCount is off by default in this fork.

## 1.5.1-sm.1 (SaarMesh fork, based on vipje 1.5.1)

- DE pack: `warnung` (DWD + NINA), card **DEWarn** (new warnings and all-clears in a channel), `pegel`
  (PEGELONLINE + Saarland HMD), card **PegelAlarm** (flood stages), `odl` (BfS gamma dose rate), `feestdag`/`feiertag`
  with countries and regions from the card.
- Commands whose data covers one country start off on an installation set to another country
  (weather → default_country).

## 1.5.1

- InstallCount (on by default, one switch to turn it off) now also sends the bot's language, the processor type, the
  connection type (serial/BLE/TCP), which cards are switched on or off (their names as in the add-on), the number of
  days the installation runs and how many errors and warnings it logged yesterday (just the numbers). Still no
  names, keys, channels, addresses or anything from the mesh; the README says exactly what is sent.

- New card **P2000** and command `p2000`: emergency-service call-outs with far less airtime. Only priority-1 messages
  (P1, A1, "met spoed") are posted in the channel (at most a few an hour), plus a daily count at 12:00 of fire brigade,
  ambulance and police call-outs. The rest on request: `p2000`, `p2000 3`, `p2000 spoed`, `p2000 <place>`,
  `p2000 vandaag` — only in that channel and by DM. Reads the public AlarmeringDroid API itself; no Home Assistant
  automation needed.

- Greeter: new option **Send the greeting as** — a DM to the new person (now the default) or a message in the channel, as
  before. When the DM cannot be sent (the name is not in the radio's contacts) the bot greets in the channel after all, or
  sends nothing (option **When the DM cannot be sent**). Want the old behaviour? Set the option to *A message in the channel*.

- Greeting and channel hint in the sender's language (with AutoLanguage on): a French "Bonne soirée" no longer gets a
  Dutch welcome. New fields per language on the Greeter and ChannelHint cards ("Greeting in French", "Hint text in
  French"); empty = a standard text in that language. Command words alone (test, ping) and words several languages
  share ("hallo") keep the bot's language. The channel list in a hint says "or"/"oder"/"ou"/"eller" instead of always
  the Dutch "of". The add-on now installs `langdetect`, so longer messages are recognised too (also for commands).

- Dashboard froze on some pages, mostly Bot network (also in the Home Assistant app): the translation script wrote a
  tooltip back when its translation was the same text (for example "node … · build …"), which counts as a change, so
  it ran again for ever. Now it only writes a real change and never translates its own output again. Parts inside a
  translated sentence are translated too ("last heard 2 days ago" -> "laatst gehoord 2 dagen geleden").

- A command switched off on the Plugins page now stays silent, as if it did not exist. Before, the bot answered
  "Sorry, '<command>' staat momenteel uit" (always in Dutch), and stats and the DM-only commands spoke up on their own
  too. A switched-off command also gets no channel hint any more.

- `ping` tells more: "Pong @[Jan]! 3 hops via Repeater Zuid · SNR 6.5 dB · RSSI -92 dBm · 1.2s in transit · 07:01" —
  the hops, the repeater the bot heard it from (by name, when only one repeater in the contacts has that prefix),
  signal, travel time and the bot's time, in the sender's language. Unknown parts are left out. A `ping` keyword in the
  config still wins.

- Dashboard language: the last texts with numbers (Region warnings per channel, multibyte shares, channel bytes on the
  radar), the labels of charts (read out by screen readers), the status bar (clients, radio ok, "snapshot 1m ago") and
  the long info tooltips (Hops, multibyte share; texts over 400 characters were skipped) are translated too.

- Dashboard (dark theme): the selected observer row was unreadable until you hovered over it, and some badges (online, ERROR, WARNING, found) had no colour; they use the dashboard's Bootstrap 5.1 classes now.

- Channel check: a channel you renamed or removed on the radio (its slot now holds another channel) is no longer looked for
  (it warned "still missing" after every restart until it was forgotten). A reading stored under a key prefix joins the
  full key right away, not only at the next start.

- AnalyzerFeed card: option **Look up unknown names** (on with the card). Neighbours in your repeaters' neighbour lists
  that have no name, only a key prefix such as `a1b2c3`, are looked up at the analyzer and shown on the Repeater page
  with their name and the label *analyzer*. At most 20 lookups an hour, each prefix once a
  week; works without regions too. The analyzer address can be any site of the EU Meshcore Analyzer, e.g.
  https://cornmeister.nl.

- Dashboard language, checked page by page with live data: the remaining texts translated (sentences split around
  links, texts with numbers such as "169 readings in this period"), and dates, times and numbers follow the bot's
  language too ("2 okt." instead of "Oct 2"). Repeater page: with only a few readings the points are drawn, so a chart
  with one reading no longer looks empty.

- Dashboard in the bot's language: now also the Plugins page (every card's description, field names, help texts and choices; about 850 texts in nl, de, fr and da).

- Channel radar: option **Community channel list** on the ChannelRadar card (off by default): once a day the bot fetches
  the list of hashtag channels seen across Europe (about 2000 names; the same list the EU Meshcore Analyzer and the Dutch
  MeshCore toolbox show) and the radar recognises those channels (from 2 messages, like its generated names), also back through the packet log. Only the
  names are kept, not the messages or senders in that list.

- **Observers without a broker of your own** (card *AnalyzerFeed*, off by default): fill in the region codes you want
  (e.g. `MST` for South Limburg, or `AMS`, `CGN`, `LGG`, ...) and the bot reads those observers from the public EU
  Meshcore Analyzer (meshcore-analyzer.eu, no account needed). Radar -> Observers then lists them (online/offline, model,
  firmware) plus one row per region with all its traffic: packets, adverts, group messages and the nodes heard there.
  Their group messages also count on the Channel radar. Only reads, at a slow pace (observers every 5 minutes, new
  packets every minute).

- Channel radar: channels the name hunt found get the label **new** on that day and the day after (they had no label).

- **NL-Alert on the mesh** (card *NLAlert*, off by default): the government's NL-Alert warnings for the provinces you
  choose (e.g. `Limburg`) and/or within a radius of the bot, posted in one or more channels (default `#nlalert`, e.g.
  `#nlalert, #limburg`; made on the radio by AutoChannels). Only the Dutch text, at most 3 messages; a re-sent alert with the same text is not posted again, and
  nothing old is posted after a restart. Source: the public NL-Alert feed; the province is looked up once per alert
  (OpenStreetMap). Plus a **siren test notice** every first Monday of the month at 12:00 (not on public holidays; in June
  and December with NL-Alert's own test message), until the sirens stop on 1 January 2028. An extra way to hear about
  a warning, never the official one.

## 1.5.0

- Repeater page: a repeater could appear twice (once with a single reading) when Home Assistant had not yet passed on
  its full key just after a restart. Such readings now go under the full key, and existing ones are merged at the start.

- **Users with roles for the dashboard** (Settings -> Users): admin accounts, and **read-only viewers** that only see the pages you tick
  and, on the Repeater page, only their repeaters or repeater **groups**. Enforced on the server: a viewer cannot change anything, gets no
  channel keys and no live connection. Salted password hashes, a pause after 8 wrong attempts, changes work at once. The add-on password
  still logs in as admin (name empty). The Home Assistant sidebar needs no second login any more.

- **The dashboard in the bot's language**: with *Language of the replies* on `nl`, `de`, `fr` or `da`, the whole dashboard (menus,
  headings, buttons, messages, help texts; also what appears later) is shown in that language.

- **Danish** as a fifth language (*Bot > Language of the replies*: `da`): every text of this add-on and of the bot
  itself. Only the long joke lists (hacker, cat facts, hello variations) stay English. AutoLanguage now also answers in
  a language only this add-on has (Danish) and recognises a few Danish greetings (godmorgen, tak, ...). The info bot,
  F1 and Reminders cards have *Dansk* as a choice too.

- **Repeater page: charging current and other sensors.** Repeaters that report extra telemetry through meshcore-ha
  (such as `ch2_current` and `ch2_voltage` of a charge controller, or temperature/humidity sensors) get a tile and a
  chart per value, with its unit. Only values the repeater actually reports appear.

- **MQTT observers** (card *ObserverFeed*, off by default): listens to MeshCore observers on an MQTT broker (the common
  format `meshcore/{IATA}/{PUBLIC_KEY}/packets` and `/status`, as meshcoretomqtt, LetsMesh and meshcore-ha publish).
  The Radar page gets a tab **Observers**: per observer online/offline, model and firmware, packets per hour (adverts,
  group messages, other), signal, and which nodes it hears. Group messages an observer hears also count on the Channel
  radar (once, also when the bot's radio heard them too). Only listens: nothing is published, nothing goes over the
  radio, messages are not decrypted. Kept 30 days.

- **Fix: the greeter never greeted.** With a wait before the greeting (*dead air delay*), the greeter put the newcomer on
  its list at once and, after the wait, took that mark for "already greeted" and stayed silent (12 greetings in a day,
  none sent). The welcome goes out again; someone greeted before is still not greeted twice.

- **Time zone from Home Assistant:** with the option *Time zone* empty, the bot now uses Home Assistant's own time zone
  (Settings -> System -> General) instead of Europe/Amsterdam, like it already did with the home location.

- Dashboard: the banner check (radio offline, ...) every 30 s and only while the page is visible (was every 10 s, also in
  a background tab); the Games standings are reused for 30 s.

- **Dashboard in the Home Assistant sidebar no longer hangs:** every page opened a live connection (socket.io), also
  pages that never use it. Through Home Assistant (ingress) the browser talks to one address with about six connections
  at a time, and Home Assistant's own connections plus a live connection per page filled that up, so the next request
  had to wait. Now only Realtime, Logs and Mesh open it; other pages show *Live: off* in the bar.

- **Name hunt** (card *NameHunt*, on): at the quietest hours of the day (default 02:00-06:00 until there is enough to go
  on), the bot tries millions of names against the unknown channels of the Channel radar.
  The names come from what it hears itself: node and place names, words and #hashtags typed in channels, the radar's
  lists and combinations. A name only counts when two stored messages match. Found channels appear on the radar at
  once. Quiet hours are the hours in which people send the fewest messages and commands (the last week); radio packets
  are not used, because most of them are repeater adverts, also at night. At most 30 minutes in every quiet hour (adjustable), in small portions, so the bot keeps answering; when every
  name has been tried it waits for something new (new words heard, a new unknown channel). Nothing is sent.

## 1.4.0

- Channel radar: **Add a channel** at the top (a #name, or a name with its key; works at once, no restart) and a tab
  **Not heard yet** with the channels you added on which nothing was heard yet (they used to be invisible).
- `ha` **groups**: every row on the Ha card can be in groups (`tuin, alles`); `ha tuin uit` switches the whole group,
  `ha tuin` toggles it (one on: all off), `ha tuin status` shows it.
- Dashboard: live events (packets, commands, messages) only go to pages that asked for them, not to every open page
  (Radar and Games got every radio packet for nothing). An update no longer logs "Web viewer process exited
  unexpectedly (code -15)": a stop signal is a normal stop.

- Channel radar, straight from the page: **Add to radio** next to a recognised hashtag channel that is not on your radio
  (AutoChannels puts it in a free slot within a minute, asking the radio for each slot first; nothing is overwritten),
  and **Name it** next to an unknown channel byte: the name is checked against the logged messages of that byte (channel
  byte and check code must match) and, when right, recognised at once, without a restart, and counted back through the
  log. Names added there can be removed again.

- Channel radar: the *found* label only on the day a channel is first heard and the day after. Open channels **without
  #** whose key is shared openly can be added on the ChannelRadar card (*Known channel keys*, `Name=key`); they are
  counted (never decrypted) like the channels on the radio.
- `ha <word>` without aan/uit **toggles** something that may be switched (a scene or script: turns it on);
  `ha <word> status` shows its state.

- **Dashboard much faster:** the Games page took 9 seconds for every load (and again every minute), because Mesh RPG was
  worked out person by person (seven queries each, for everyone who ever wrote, twice) and DX Jacht searched the whole
  table for every row. Now a few queries for everyone: 0.35 s for 1500 names, same results. Pages only refresh while you
  look at them (not in another browser tab or a minimised window).

- **DM answers arrive more often:** one try over the stored route, then up to three floods (was: twice the stored route,
  one flood). A stale route (the person wrote via another path) lost the answer before.
- Problems page: a DM answer that went out but whose confirmation (ACK) never came back is shown apart (*DM sent, not
  confirmed*) from a command that got no answer at all. **Done** per row and **Clear all**: what you looked into
  disappears until it happens again.
- Farming Idle seasons: besides a month or a week, **your own dates** (from ... to ..., with a calendar on the tab). After
  the end date the result is posted and no season runs until you choose new dates; `farm seizoen` tells when the next
  one starts.

- **Problems page** (Settings -> Problems, card *ProblemLog*): the bot's warnings and errors grouped per kind (repeats
  count as one), and commands it recognised but did not answer, with what was typed. 24 hours, 7 or 14 days.
- **Home Assistant over the mesh**: `ha` by DM, only for the bot's admin. Read the entities on the *Ha_Command* card
  (`ha woonkamer temperatuur`, `ha alles`) and switch the ones marked so (`ha tuinlicht aan`, scenes, scripts). On the
  card every entity is a row of its own with the word you type after `ha` (switch.feest_verlichting -> `ha feest aan`).
  Not in `help`.
- **Mailbox**: `post <name> <text>` leaves a message for someone; the bot DMs it as soon as it hears that person again
  (a message or an advert; 7 days). New page *Mailbox* on the dashboard: waiting, delivered, expired, take one out; the
  text of a message left by DM is not shown.
- Farming Idle **seasons**: a month (or a week), points = farm XP gained; `farm seizoen`; the top 3 get coins (1000 /
  500 / 250) and the result is posted in the games channel. On, off, length and rewards on the Farming Idle tab.
- Bot network: **only the closest bot answers**. When bots of this add-on hear the same information command (test,
  ping, path, trace, wx, help, ...) in a channel, the one with the fewest hops (then the best signal) answers, the others
  stay silent. BotNetwork card: *Only the closest bot answers* (on) and the list of commands. Without the broker, or
  with no other network bot online, nothing changes.

- **Advert like a repeater:** new options *Advert every (hours)* (default 12, 0 = off, at least 3) and *Advert at start*
  (default zero-hop). The count continues after a restart (the time of the last advert is kept in the database).
- **Contact list full of repeaters:** the ContactCleanup card may now also remove repeaters that are still heard, the
  farthest first (*Also remove repeaters that are still heard*, on). The radio held 349 of 350 contacts, almost all active
  repeaters, so nothing could go and the firmware overwrote people instead. Never removed: direct neighbours, repeaters
  meshcore-ha follows, RepeaterWatch's list, starred and favourites.
- Farming Idle: `farm` in a channel now opens a **DM from the bot** to that person (when their name matches exactly one
  contact; once a day per person), so they can play on there at once. Otherwise the answer says clearly to open a DM
  with the bot (by name) and send `farm start` there; the daily invitation says the same.

- The farm game is now called **Farming Idle** (it was *Kwekerij*). The command stays `farm`; farms, coins and fields
  are kept.
- Farming Idle: after a harvest the answer says the plant **grows again** and how often (`farm` shows "(9x left)" per
  crop), because a field only gets empty once the plant is spent. `farm ruim <crop|field nr|alles>` (en `clear`) clears
  fields to sow something else. A real **seed shop**: `farm winkel` lists price, growing time and number of harvests,
  `farm winkel tomaat` tells everything about a crop, and `farm zaad tomaat 5` (en `seeds`) buys seeds for the barn to
  sow later or sell on the market.
- Games page: a **Farming Idle** tab with everything of the farm game: all players (level, coins, bank, fields, workshop,
  today's task, last played); click a player to see what grows on each field and when it is ripe, what the workshop
  makes, the barn and their market offers. The market between players is on the tab too. (The small farm card on
  the standings tab is gone.)
- **The market buys:** on the Farming Idle tab you set what the market wants, how many and the price per piece (and for how
  many days). Players see it in `farm markt` (*Market buys*) and sell with `farm lever jam 5` (en: `deliver`, de:
  `liefere`, fr: `livre`), paid at once; it counts for a sell task. At 12:00 the FarmDaily card posts what the market
  buys in the games channel (only on days with an open order; *Market buys at* on the card, empty = off).
- **trace** on long paths: it waited only 5.5 s for a round trip of 9 hops and nearly always failed. The default is now
  2 s + 1.5 s per hop (as the card already said); a timeout answers in your language with the hops, the time and a tip
  (`tracer da,69` for a shorter stretch). `tracert` works as well.
- New command **discover** (also `buren`): the repeaters the bot hears directly, best signal first, from neighbour
  discovery; sends nothing over the radio.

## 1.3.0

- **Fix:** `ping` did not answer at all since 1.1.0 (new installations have no ping keyword, and the translated
  "Pong! More info: type test" was never used). It answers again; a ping keyword of your own still wins.
- Kwekerij: a **daily task**, the same for everyone (harvest, make or sell; the amount grows with your level), with
  coins, farm XP and 5 Mesh RPG XP as reward (`farm opdracht`); every morning at 06:00 the task goes to the games channel
  (card *FarmDaily*, waits for the end of night mode); while nobody plays it is an invitation to start, and every day at
  14:00 an invitation to join goes out to get more players. A **market** between players: `farm markt`, `farm bied jam 3 60`,
  `farm koop 2`, `farm intrekken 2`; offers last 3 days, the seller sees the sale in `farm`. Farm tasks show in the
  Mesh RPG breakdown on the Games page.
- GitHub: the tests run automatically on every push (badge in the README). Nothing of it is installed in Home
  Assistant.
- The bot's position: with Latitude/Longitude empty, Home Assistant's own home location is used (before the radio's).
- **First-start wizard** (dashboard: Settings -> Setup): the channels the bot answers in, a busy public channel that
  only gets a pointer and a welcome, command groups on or off (games, Netherlands/Belgium, weather and space, fun, F1),
  a games channel and extras (night mode, bot network, repeater watch, Home Assistant sensors), on one page, with a
  restart button. On a new installation the dashboard opens on the wizard (and other pages show a banner) until it is
  saved; it can be run again at any time.
- New card **HASensors** (on): the bot's numbers as Home Assistant sensors (`sensor.meshcore_bot_...`), updated every 5
  minutes: people and repeaters heard, people who wrote, channel messages, commands answered, new nodes, most hops
  today, direct neighbours, the radio's noise floor and airtime, map uploads and the Kwekerij's players. Put them on a
  dashboard or use them in automations.
- New card **RepeaterWatch** (on): when a repeater your radio hears directly has not been heard for 24 hours (adjustable),
  you get a message through the Notifications card (room, channel or DM) and a notification in Home Assistant; and a
  message when it is back. Extra repeaters to watch can be named on the card.
- MapUploader: instead of two log lines for every repeater it sends to map.meshcore.dev, it counts per day (sent, new
  on the map, already known, failed) and logs one summary line an hour; failures keep their own warning. The Repeater
  radar shows a tile *Map uploads today* (hover for the last 7 days).

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
