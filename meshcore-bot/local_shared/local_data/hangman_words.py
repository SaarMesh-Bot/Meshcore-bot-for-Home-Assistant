"""Word list for the 'hangman' command, grouped by category (German, SaarMesh fork). Kept free of umlauts and ß
(ae/oe/ue/ss) so letter-by-letter guessing stays simple."""

HANGMAN_WORDS = {
    "tiere": [
        "elefant", "giraffe", "krokodil", "pinguin", "kaenguru", "schmetterling",
        "igel", "eichhoernchen", "delfin", "wal", "zebra", "leopard",
        "koala", "panda", "flamingo", "strauss", "spinne", "ameise",
        "kamel", "nashorn",
    ],
    "laender": [
        "belgien", "niederlande", "deutschland", "frankreich", "spanien", "italien",
        "portugal", "schweden", "norwegen", "finnland", "polen", "griechenland",
        "tuerkei", "marokko", "aegypten", "kanada", "brasilien", "japan",
        "australien", "luxemburg",
    ],
    "essen": [
        "lyoner", "schwenker", "dibbelabbes", "hoorische", "gefillde", "pizza",
        "nudeln", "hamburger", "sushi", "pfannkuchen", "apfelkuchen", "suppe",
        "salat", "kaese", "brot", "kuchen", "spaghetti", "currywurst",
        "brezel", "flammkuchen",
    ],
    "sport": [
        "fussball", "radfahren", "tennis", "schwimmen", "leichtathletik", "hockey",
        "basketball", "volleyball", "boxen", "judo", "golf", "badminton",
        "handball", "eislaufen", "klettern", "rudern", "darts", "billard",
    ],
    "berufe": [
        "installateur", "elektriker", "baecker", "metzger", "lehrer",
        "pfleger", "feuerwehrmann", "zimmermann", "friseur", "landwirt",
        "fahrer", "anwalt", "tierarzt", "apotheker", "mechaniker",
    ],
    "funk": [
        "antenne", "repeater", "frequenz", "reichweite", "rauschen",
        "akku", "funkgeraet", "kanal", "wellenlaenge", "verstaerker",
        "koaxkabel", "mesh", "sender", "empfaenger", "solarpanel",
    ],
}
