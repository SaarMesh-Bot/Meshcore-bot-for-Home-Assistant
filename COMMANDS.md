# Commando's van de MeshCore-bot

*[English](COMMANDS.en.md)*

Zo gebruikt de **Vip|HA|🤖**-bot ze; een eigen bot werkt hetzelfde, met de kanalen die je zelf instelt.

De bot antwoordt in de taal waarin je schrijft: Nederlands, Engels, Duits, Frans of Deens.

**Zo gebruik je ze:** typ het commando in `#bot` of `#test`, of stuur het als DM naar de bot. In Publiek (kanaal 0) reageert de bot niet op commando's. Meer uitleg over één commando: `help <commando>`, bijvoorbeeld `help dx`.

Tekens: **DM** = alleen via een DM · **#f1** = in het kanaal #f1 of via DM · 🌐 = heeft internet nodig

## Inhoud

- [Basis en hulp](#basis-en-hulp)
- [Mesh en radio](#mesh-en-radio)
- [Spellen en community](#spellen-en-community)
- [Farming Idle](#farming-idle)
- [Formule 1](#formule-1)
- [Handig (Nederland en België)](#handig-nederland-en-belgië)
- [Weer, zon en ruimte](#weer-zon-en-ruimte)
- [Leuk](#leuk)

## Basis en hulp

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `ping` | `ping` | Snelle controle: de bot antwoordt 'Pong!' met de hops, via welke repeater, SNR, RSSI en looptijd. |
| `test`<br><sub>ook: t</sub> | `test [zin]` | Verbindingsinfo van je bericht: route, bytes per hop (1, 2 of 3), SNR, RSSI en tijd. |
| `hello`<br><sub>ook: hi, hey, hola, bonjour, ...</sub> | `hello` | Groet terug (robotstijl). Let op: 'hallo' zit er niet bij. |
| `help` | `help  /  help 2  /  help dx` | Lijst van commando's per pagina, of uitleg over één commando. |
| `helpall` | `helpall` | De volledige commandolijst, elke keer de volgende pagina. |
| `cmd`<br><sub>ook: cmds, commands</sub> | `cmd` | Korte lijst van beschikbare commando's. |
| `version`<br><sub>ook: ver</sub> | `version` | Welke versie van de bot draait. |
| `contact` | `contact` | Contactgegevens van de bot. |
| `channels`<br><sub>ook: channel</sub> | `channels [lijst\|#kanaal]` | Overzicht van bekende hashtag-kanalen. |
| `dm` | `dm` | Typ in een kanaal: de bot stuurt je een DM, daarna kun je hem privé gebruiken. |
| `info bot`<br><sub>ook: infobot</sub> | `info bot` | Wat deze bot is en wat je nodig hebt voor een eigen bot. **DM** |
| `post`<br><sub>ook: brief, mail</sub> | `post Bob ik ben er zaterdag`  /  `post @[Dirk Jan] bel je?`  /  `post` | Brievenbus: een bericht voor iemand die er niet is. Zodra de bot die persoon weer hoort, stuurt hij het per DM door (7 dagen geldig, max 3 wachtend per afzender). `post` alleen toont wat van jou nog wacht. |
| `ha` | `ha`  /  `ha woonkamer temperatuur`  /  `ha tuinlicht aan` | Home Assistant via de mesh, **alleen voor de beheerder** van de bot (sleutel in *Admin public keys*). Alleen wat op de kaart *Ha_Command* staat: per entiteit een regel met het woord dat je achter `ha` typt (bv. `feest` voor switch.feest_verlichting: `ha feest aan`). `ha feest` zonder aan/uit zet hem om; `ha feest status` toont alleen de stand. Groepen (veld *Groups* op de kaart): `ha tuin uit` zet alles in de groep tuin uit. Staat niet in `help`. **DM** |

## Mesh en radio

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `pad` | `pad` | De route van je bericht in één regel: hops, km en repeaters (? = gok). |
| `sig`<br><sub>ook: signaal</sub> | `sig` | SNR, RSSI en hops van je bericht met een oordeel (goed/redelijk/zwak). Handig bij antenne-tuning. |
| `path`<br><sub>ook: decode, route</sub> | `path  /  path 4a,c2,8c` | Lange versie van de route: elke repeater op een eigen regel. Lange antwoorden krijgen (1/2), (2/2); op de kaart *path* kan *Max hops shown* het korter maken. |
| `trace`<br><sub>ook: tracer, tracert</sub> | `trace [pad]` | Trace langs een pad (heen en terug), met signaal per stap. Zonder pad: jouw berichtpad heen en terug. Lange paden (veel hops) lukken minder vaak; `tracer da,69` probeert een kort stuk. |
| `discover`<br><sub>ook: buren</sub> | `discover` | De repeaters die de bot direct hoort (0 hops), beste signaal eerst. Verstuurt zelf niets over de radio. |
| `multitest`<br><sub>ook: mt</sub> | `multitest` | Luistert 6 seconden en toont alle routes waarlangs je bericht binnenkwam. |
| `prefix`<br><sub>ook: lookup</sub> | `prefix 4a` | Welke repeaters een bepaalde prefix hebben, met locatie. 🌐 |
| `meshkaart`<br><sub>ook: nodes</sub> | `meshkaart` | Hoeveel nodes, repeaters en rooms de bot hoort (24 uur, 7 dagen, ooit). |
| `whois` | `whois <naam of sleutel>` | Contactkaart van een bekende node, met level en titel in Mesh RPG. |
| `rptr` | `rptr  /  rptr buren  /  rptr accu 7d` | Status van de repeater van de beheerder: batterij, uptime, airtime, buren. |
| `stats` | `stats [messages\|channels\|paths\|adverts]` | Statistieken van de afgelopen 24 uur. |
| `topu` | `topu  /  topu 7` | Top 5 actiefste gebruikers (24 uur of N dagen), zonder bots. |
| `topr` | `topr  /  topr 7` | Top 3 drukste repeaters. |
| `topc` | `topc  /  topc 7` | Top 5 meest gebruikte commando's. |
| `uptime` | `uptime` | Hoe lang de bot al draait. |

## Spellen en community

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `dx` | `dx  /  dx top [week\|maand\|ooit]  /  dx ik` | DX Jacht: records voor het bericht met de meeste hops, per week, maand en ooit. |
| `xp`<br><sub>ook: level</sub> | `xp  /  xp <naam>  /  xp top [week]` | Mesh RPG: XP, level en titel. Je verdient XP met berichten, commando's, inchecken, karma en DX. |
| `badge`<br><sub>ook: badges</sub> | `badge  /  badge <naam>` | Mesh RPG: je behaalde mijlpalen (berichten, actieve dagen, hops, reeksen, karma, levels). |
| `karma`<br><sub>ook: topkarma</sub> | `karma <naam>  /  karma  /  karma top` | Bedank iemand met een punt (max 3 per dag, niet jezelf of een bot). |
| `checkin`<br><sub>ook: meld, inchecken</sub> | `checkin  /  checkin top` | Dagelijks inchecken en een reeks opbouwen. |
| `voorspel` | `voorspel  /  voorspel nieuw Vraag? \| ja \| nee  /  voorspel 1` | Voorspellingsspel voor elke vraag. Vragen stellen en antwoorden via DM; 1 punt voor een goed antwoord. |
| `peiling`<br><sub>ook: kies</sub> | `peiling Waar eten we? \| pizza \| friet  →  kies 2` | Meerkeuze-peiling op een kanaal (2 tot 5 keuzes), stemmen met kies <nr>. |
| `stem`<br><sub>ook: poll, ja, nee</sub> | `stem 15m pizza vanavond?  →  ja / nee` | Ja/nee-stemming op een kanaal. |
| `prikbord` | `prikbord  /  prikbord pomp te leen  /  prikbord weg 3` | Prikbord: korte berichten die 7 dagen blijven staan. |
| `quiz` | `quiz` | Quizvraag op het kanaal. |
| `hangman` | `hangman` | Galgje op het kanaal. |
| `dice` | `dice 2d6` | Dobbelstenen gooien. |
| `roll` | `roll 100` | Willekeurig getal van 1 tot en met het getal. |
| `magic8` | `magic8 Wordt het droog?` | De Magic 8-Ball beantwoordt een ja/nee-vraag. |

## Farming Idle

Een boerderijspel dat je **via een DM** met de bot speelt (dan weet de bot dat jij het bent). Typ je `farm` in een kanaal, dan stuurt de bot je zelf een DM; antwoord daar met `farm start`. Zaai gewassen, oogst ze,
verwerk ze in je werkplaats tot iets wat meer oplevert, verkoop, spaar in de bank en groei van level 1 naar 10.

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `farm` | `farm` | Je stand: level, munten, bank, wat er rijp is en wanneer de rest rijp is. **DM** |
| `farm start` | `farm start` | Begin je boerderij: 4 velden en 200 munten. **DM** |
| `farm winkel`<br><sub>ook: shop, zaad</sub> | `farm winkel`  /  `farm winkel tomaat`  /  `farm zaad tomaat 5` | De zaadwinkel: wat je op jouw level kunt kopen (prijs, groeitijd, aantal oogsten), alles over één gewas, of zaad kopen voor je schuur (later zaaien of op de markt verkopen). **DM** |
| `farm zaai`<br><sub>ook: plant, sow</sub> | `farm zaai tomaat 4` | Zaai op je lege velden. Eigen zaad gaat eerst, de rest koop je. **DM** |
| `farm oogst`<br><sub>ook: harvest</sub> | `farm oogst` | Oogst alles wat rijp is; het gaat naar je schuur. Een plant geeft meerdere oogsten (tomaat 10x) en groeit daarna opnieuw; pas als hij op is, is het veld leeg. **DM** |
| `farm ruim`<br><sub>ook: clear</sub> | `farm ruim tomaat`  /  `farm ruim 2`  /  `farm ruim alles` | Maak velden leeg om iets anders te zaaien (de planten ben je kwijt). **DM** |
| `farm schuur` | `farm schuur` | Wat er in je schuur ligt: oogst, producten en zaad. **DM** |
| `farm verkoop` | `farm verkoop`  /  `farm verkoop jam` | Verkoop alles, of één soort. **DM** |
| `farm verwerk`<br><sub>ook: maak, make</sub> | `farm verwerk soep 2` | Maak in je werkplaats een product van je oogst (zie de tabel). **DM** |
| `farm bank` | `farm bank`  /  `farm stort 500`  /  `farm haal alles` | Je spaargeld: 1% rente per dag (max 500 per dag), veilig voor de zakkenroller. **DM** |
| `farm upgrade` | `farm upgrade`  /  `farm upgrade kas` | Extra veld, betere kas (sneller groeien), betere grond (meer oogst) of een grotere werkplaats. **DM** |
| `farm geef` | `farm geef Alex 100` | Geef munten aan een andere boer. **DM** |
| `farm opdracht` | `farm opdracht` | De opdracht van vandaag (voor iedereen dezelfde: oogsten, maken of verkopen; hoeveel hangt af van je level) en je voortgang. Beloning: munten, farm-XP en 5 XP voor Mesh RPG. **DM** |
| `farm markt` | `farm markt` | Wat andere boeren te koop aanbieden, en wat de markt zelf inkoopt (*Markt koopt*). Werkt ook in `#games`. |
| `farm lever` | `farm lever jam 5` | Verkoop aan de markt als die erom vraagt: je krijgt meteen de prijs die de markt biedt (vaak meer dan bij `farm verkoop`). Telt mee voor een verkoop-opdracht. **DM** |
| `farm bied` | `farm bied jam 3 60` | Bied oogst of producten aan op de markt (aantal, prijs per stuk), 3 dagen geldig. **DM** |
| `farm koop`<br><sub>ook: intrekken</sub> | `farm koop 2`  /  `farm intrekken 2` | Koop aanbieding 2 van de markt, of neem je eigen aanbieding terug. **DM** |
| `farm top` | `farm top` | De rijkste boeren (munten + bank). Werkt ook in `#games`. |
| `farm seizoen`<br><sub>ook: season</sub> | `farm seizoen` | Het seizoen (een maand, of een week als de beheerder dat kiest): de top 5 in farm-XP van dit seizoen, jouw plek en hoeveel dagen nog. De top 3 krijgt munten; de uitslag komt in `#games`. **DM** |

**Gewassen en producten**

| Level | Gewas | Zaad | Groeit | Opbrengst per oogst | Oogsten | Verwerken tot |
|---|---|---|---|---|---|---|
| 1 | tomaat | 20 | 1 u | 2–4 × 3 | 10× | tomatensoep (4 tomaat, 1 u), pasta (8 tomaat, 3 u) |
| 2 | aardbei | 60 | 2 u | 3–5 × 6 | 8× | jam (5 aardbei, 2 u) |
| 3 | pompoen | 150 | 4 u | 1–2 × 40 | 6× | lantaarn (1 pompoen, 1 u) |
| 4 | wiet | 300 | 6 u | 2–3 × 50 | 5× | joint (2 wiet, 1 u) |
| 5 | druif | 500 | 8 u | 4–6 × 45 | 8× | wijn (6 druif, 12 u) |
| 6 | zonnebloem | 800 | 10 u | 3–5 × 95 | 6× | olie (3 zonnebloem, 4 u) |
| 7 | appel | 1200 | 12 u | 5–7 × 100 | 10× | appeltaart (4 appel, 3 u) |
| 8 | hop | 2000 | 16 u | 4–6 × 210 | 8× | bier (3 hop, 8 u) |
| 9 | koffie | 3500 | 20 u | 3–5 × 430 | 8× | espresso (2 koffie, 2 u) |
| 10 | cacao | 6000 | 24 u | 3–5 × 700 | 8× | chocolade (2 cacao, 6 u) |

- Opbrengst: aantal stuks × verkoopprijs per stuk. Na het laatste aantal oogsten is de plant op en is het veld weer leeg.
- Bij elke geoogste vrucht is er 1% kans op een **zaadje**: gratis zaad voor de volgende keer.
- Je level stijgt met XP uit oogsten en verwerken; elk level brengt een nieuw gewas.
- Soms gebeurt er iets bij het oogsten: een **topoogst** (dubbel), **storm** (een veld kapot), een **zakkenroller** (10% van
  je munten, niet van de bank) of een **controle** als je wiet oogst.
- Elke ochtend om 06:00 zet de bot de opdracht van de dag in `#games`, om 12:00 wat de markt inkoopt (alleen als er een inkooporder open staat) en om 14:00 een uitnodiging om mee te doen (kaart *FarmDaily*).
- Een bot-eigenaar kan gewassen uitzetten (kaart *farm*), bijvoorbeeld wiet.

## Formule 1

Werkt in het kanaal `#f1` en via DM. De gegevens komen uit de F1-integratie van Home Assistant (f1_sensor).

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `f1`<br><sub>ook: volgende, next</sub> | `f1` | De volgende race: naam, plaats en de starttijden van het weekend. **#f1** |
| `f1 stand`<br><sub>ook: wk, rijders</sub> | `f1 stand` | WK-stand van de coureurs (top 10). **#f1** |
| `f1 team`<br><sub>ook: teams, constructeurs</sub> | `f1 team` | WK-stand van de teams (top 10). **#f1** |
| `f1 coureur`<br><sub>ook: rijder, driver</sub> | `f1 coureur VER`  /  `f1 coureur verstappen`  /  `f1 coureur 1` | Eén coureur: plek in het WK, punten, overwinningen, team en rugnummer. **#f1** |
| `f1 uitslag`<br><sub>ook: result</sub> | `f1 uitslag` | Uitslag van de laatste race. **#f1** |
| `f1 sprint` | `f1 sprint` | Uitslag van de laatste sprintrace. **#f1** |
| `f1 weekend`<br><sub>ook: schema, tijden</sub> | `f1 weekend` | Alle sessies van het volgende raceweekend in jouw tijd: vrije trainingen, kwalificatie, sprint en race. **#f1** |
| `f1 grid`<br><sub>ook: opstelling, start</sub> | `f1 grid` | De startopstelling (top 10) na de kwalificatie; daarvoor zegt de bot wanneer de kwalificatie is. **#f1** |
| `f1 kalender`<br><sub>ook: agenda, races</sub> | `f1 kalender` | De komende races met datum en tijd. **#f1** |
| `f1 nu`<br><sub>ook: live</sub> | `f1 nu` | Tijdens een sessie: welke sessie, ronde, vlag en de top van het veld. **#f1** |
| `f1 weer` | `f1 weer` | Tijdens een sessie: temperatuur van lucht en baan, vocht, wind en of het regent. **#f1** |
| `f1 pit`<br><sub>ook: pitstops</sub> | `f1 pit` | Tijdens een sessie: de laatste pitstops met ronde en stilstandtijd. **#f1** |
| `f1 voorspel` | `f1 voorspel VER`  /  `f1 voorspel VER NOR LEC` | Voorspel de winnaar, of je top 3 in volgorde. Met de afkorting van 3 letters. **DM** |
| `f1 spel`<br><sub>ook: punten</sub> | `f1 spel` | Stand van het voorspellingsspel dit seizoen. **#f1** |
| `f1 ik`<br><sub>ook: mijn</sub> | `f1 ik` | Jouw eigen punten, je plek en je voorspelling voor de volgende race. **DM** |

`f1 nu`, `f1 weer` en `f1 pit` werken alleen tijdens een sessie. Daarbuiten zegt de bot hoe lang het nog duurt tot de
volgende sessie begint, bijvoorbeeld "Over 2:15 uur begint de kwalificatie".

**Het voorspellingsspel**
- Voorspellen doe je via een DM aan de bot (daar zit je sleutel bij, zodat niemand namens jou speelt).
- Je kunt je voorspelling veranderen tot de eerste kwalificatie van het weekend begint; de laatste telt.
- **Alleen de winnaar** (`f1 voorspel VER`): goed = **5 punten**, je coureur werd 2e of 3e = **2 punten**.
- **Je top 3** (`f1 voorspel VER NOR LEC`): per coureur op de goede plek **5 punten**, in de top 3 maar op een andere
  plek **2 punten**, en **3 punten extra** als alle drie precies goed zijn. Dus maximaal 18 punten per race.
- De punten komen er na de race bij; `f1 spel` toont de stand. De punten zijn per bot aan te passen (kaart *F1*).

## Handig (Nederland en België)

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `herinner`<br><sub>ook: remind</sub> | `herinner 30m pizza  /  herinner 18:30 antenne  /  herinner lijst` | Persoonlijke herinnering, je krijgt een DM op het gekozen moment. **DM** |
| `noodnummers`<br><sub>ook: nood</sub> | `noodnummers` | 112 en de regionale hulpnummers. In een kanaal gevraagd komt het antwoord als DM. |
| `aed` | `aed Heerlen` | De dichtstbijzijnde AED's. In een kanaal gevraagd komt het antwoord als DM. 🌐 |
| `p2000` | `p2000`, `p2000 3`, `p2000 spoed`, `p2000 heerlen`, `p2000 vandaag` | P2000-meldingen op verzoek: de laatste, een plaats, alleen spoed, of de telling van 24 uur. Alleen in het P2000-kanaal en via DM (kaart **P2000**). 🌐 |
| `buien`<br><sub>ook: buienradar</sub> | `buien  /  buien Weert` | Regen de komende 2 uur, per 10 minuten (Buienradar). 🌐 |
| `weerwaarschuwing`<br><sub>ook: gladheid</sub> | `weerwaarschuwing` | Actuele KNMI-weerwaarschuwing. 🌐 |
| `beving` | `beving` | Recente aardbevingen in en rond Nederland (KNMI). 🌐 |
| `storing` | `storing kpn` | Storingen bij een telecomprovider. 🌐 |
| `file` | `file Maastricht` | Files en ongevallen bij een plaats. 🌐 |
| `wegwerk` | `wegwerk Sittard` | Wegwerkzaamheden bij een plaats. 🌐 |
| `ov` | `ov Heerlen station` | Eerstvolgende vertrektijden van het openbaar vervoer. 🌐 |
| `tanken` | `tanken` | Landelijke gemiddelde brandstofprijzen van vandaag (CBS). 🌐 |
| `laadpaal` | `laadpaal Kerkrade` | Laadpalen in de buurt. 🌐 |
| `energieprijs` | `energieprijs` | Huidige dynamische stroomprijs. 🌐 |
| `waterstand` | `waterstand` | Waterstand van de Maas. 🌐 |
| `straling` | `straling Maastricht` | Indicatief stralingsniveau. 🌐 |
| `kenteken` | `kenteken HDJ-60-R` | Nederlands kenteken opzoeken (RDW). Belgische en Duitse kentekens niet (geen gratis bron). 🌐 |
| `feestdag`<br><sub>ook: vandaag</sub> | `feestdag` | Feestdagen in Nederland en België. |

## Weer, zon en ruimte

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `wx`<br><sub>ook: weather</sub> | `wx Heerlen  /  wx Heerlen 7d` | Weerbericht voor een plaats. 🌐 |
| `rain`<br><sub>ook: nowcast, snow</sub> | `rain Heerlen` | Wanneer het gaat regenen of sneeuwen (ook buiten NL/BE). 🌐 |
| `aqi`<br><sub>ook: air, airquality</sub> | `aqi Maastricht` | Luchtkwaliteit voor een plaats. 🌐 |
| `sun` | `sun` | Zonsopgang en zonsondergang. |
| `moon` | `moon` | Maanfase en opkomst/ondergang. |
| `aurora`<br><sub>ook: kp</sub> | `aurora` | Noorderlicht-voorspelling (KP-index). 🌐 |
| `solar` | `solar` | Zonnecondities en HF-banden. 🌐 |
| `hfcond` | `hfcond` | HF-bandcondities voor zendamateurs. 🌐 |
| `solarforecast`<br><sub>ook: sf</sub> | `sf Heerlen 4000` | Verwachte opbrengst van zonnepanelen. 🌐 |
| `satpass` | `satpass iss` | Wanneer een satelliet overkomt. 🌐 |
| `airplanes`<br><sub>ook: planes, aircraft</sub> | `airplanes`  /  `airplanes here`  /  `airplanes 50.9,5.9` | Vliegtuigen boven de bot (of boven een plek), met hoogte en type. Staat standaard uit (kaart *airplanes*). 🌐 |
| `alert`<br><sub>ook: incident</sub> | `alert <plaats>` | Actieve noodmeldingen (PulsePoint, vooral VS). 🌐 |

## Leuk

| Commando | Voorbeeld | Wat het doet |
|---|---|---|
| `weetje`<br><sub>ook: wistje</sub> | `weetje` | Een willekeurig Nederlands weetje. |
| `quote`<br><sub>ook: citaat</sub> | `quote` | Een willekeurig citaat. |
| `joke`<br><sub>ook: jokes</sub> | `joke` | Een willekeurige mop (Engels). 🌐 |
| `dadjoke` | `dadjoke` | Een vadergrap (Engels). 🌐 |
| `morse` | `morse SOS` | Tekst naar morse en terug. |
| `sudo`<br><sub>ook: ls -la, rm -rf, ...</sub> | `sudo make coffee` | Doet alsof je een schurkencomputer hackt. |
| `catfact`<br><sub>ook: cat, meow</sub> | `catfact` | Kattenfeitje (verborgen commando). 🌐 |
| `sports`<br><sub>ook: score, scores</sub> | `sports ajax` | Sportuitslagen en programma. 🌐 |

## Spellen, goed om te weten

- **XP (Mesh RPG):** 1 per bericht (max 20 per dag), 2 per commando (max 10 per dag), 5 per check-in, 10 per karmapunt dat je krijgt, 5 per hop van je beste DX (tot 10 hops, dus max 50). Ook wat je in Publiek schrijft telt mee.
- **Bots doen niet mee**: ze staan niet in de ranglijsten, kunnen niet voorspellen in het F1-spel, en `xp`, `dx` of `badge` met een botnaam antwoordt "bots doen niet mee".
- **Spellenkanaal:** een bot kan de spellen in één kanaal houden (kaart *GamesChannel*). De **Vip|HA|🤖**-bot doet dat: `quiz`, `hangman`, `stem`, `peiling`, `checkin`, `karma`, `voorspel`, `xp` en `dx` werken in **`#games`** en via DM; in andere kanalen zegt de bot waar je moet zijn. XP blijft in elk kanaal tellen.
- `voorspel`, `herinner` en `f1 voorspel` gaan via een DM: daar zit je sleutel bij, zodat niemand namens jou kan spelen.
