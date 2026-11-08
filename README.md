# Bordfordeling

Lager bordfordeling for flere uker slik at alle sitter med flest mulig
forskjellige personer.

## Personvern

- Ingen navn eller fordelinger skrives til disk, logges eller sendes videre.
  Alt holdes i minnet mens siden er åpen og forsvinner når fanen lukkes
  (eller når du trykker «Nullstill»).
- Den publiserte versjonen (`index.html`) kjører **hele appen i nettleseren**
  med [stlite](https://github.com/whitphx/stlite). Fila du laster opp forlater
  aldri datamaskinen din; serveren leverer bare selve programkoden.
- Streamlits bruksstatistikk er slått av (`.streamlit/config.toml`).

## Filformat

Excel (`.xlsx`) eller CSV med kolonnene:

| Elever | Stipp |
|--------|-------|
| Ola    |       |
| Kari   | stipp |
| Per    |       |

- `stipp`: spres jevnt utover bordene (helst én per bord).
- Tom: vanlig elev.

Alle som står i lista får bordplass.

## Publisere gratis med GitHub Pages (anbefalt)

1. Slå sammen endringene til `main`.
2. På GitHub: **Settings → Pages → Build and deployment**, velg
   *Deploy from a branch*, gren `main`, mappe `/ (root)`, og lagre.
3. Etter et minutt er appen tilgjengelig på
   `https://<brukernavn>.github.io/Bordfordeling/`.

Første lasting tar litt tid (Python lastes ned til nettleseren), deretter går
det raskt.

## Kjøre lokalt

```bash
pip install -r requirements.txt
streamlit run Bord.py
```

## Hvordan algoritmen fungerer

For hvert par telles hvor mange uker de har sittet sammen. Hver uke søkes det
(simulert gløding med bytter mellom bord) etter en fordeling som minimerer
summen av *antall ganger²* for alle par ved samme bord. Kvadratet gjør at
gjentakelser spres jevnt, slik at ingen par sitter sammen mange ganger.

Sammenlignet med den gamle versjonen (100 tilfeldige forsøk per uke), med 65
personer, 10 bord og 10 uker:

|                                   | Før | Nå |
|-----------------------------------|-----|----|
| Par som satt sammen mer enn én gang | 403 | ~150 |
| Flest ganger samme par satt sammen | 4   | 2  |
| Snitt ulike bordkamerater          | 41  | 51 |

Med 158 personer og 15 uker gikk tiden fra ca. 11 s til 2–4 s.
