# Kjør lokalt:  streamlit run Bord.py
#
# Personvern: Opplastede navn og genererte fordelinger lagres aldri på disk
# og logges ikke. Alt holdes kun i minnet for den åpne nettleserøkten.
# Publisert via index.html (stlite) kjører hele appen i brukerens nettleser,
# så navnene sendes ikke til noen server i det hele tatt.

import csv
import difflib
import io
import zipfile
from collections import Counter

import pandas as pd
import streamlit as st

from fordeling import FordelingsFeil, generer_uker

st.set_page_config(page_title="Bordfordeling", layout="wide")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _norm(verdi):
    """Tekst uten mellomrom i endene og med små bokstaver ('' for tomme celler)."""
    return "" if pd.isna(verdi) else str(verdi).strip().lower()


def _les_ark(fil):
    """Returnerer {arknavn: rutenett} uten å tolke noen rad som overskrift."""
    try:
        if fil.name.lower().endswith(".csv"):
            raw = fil.getvalue()
            try:
                tekst = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                tekst = raw.decode("cp1252")
            # Norsk Excel lagrer ofte CSV med semikolon: bruk det mest brukte skilletegnet
            skilletegn = max(",;\t", key=tekst.count)
            return {"CSV": pd.DataFrame(list(csv.reader(io.StringIO(tekst), delimiter=skilletegn)))}
        return pd.read_excel(fil, sheet_name=None, header=None, dtype=str, engine="openpyxl")
    except Exception as e:
        raise FordelingsFeil(
            "Kunne ikke lese fila. Sjekk at det er en Excel-fil (.xlsx) eller en "
            "CSV-fil, og at den ikke er skadet eller passordbeskyttet."
        ) from e


def _finn_overskrift(ark, maks_rader=20):
    """Finner første ark og rad som har en celle med «Elever»."""
    for arknavn, df in ark.items():
        for i in range(min(len(df), maks_rader)):
            rad = [_norm(v) for v in df.iloc[i]]
            if "elever" in rad:
                return arknavn, df, i, rad
    return None


def les_navneliste(fil):
    """Leser Excel/CSV med kolonnene «Elever» og (valgfritt) «Stipp».

    Store/små bokstaver i overskriftene spiller ingen rolle, rader over
    overskriften (f.eks. en tittel) hoppes over, og alle ark søkes gjennom.
    Returnerer (stipper, elever, advarsler).
    """
    ark = _les_ark(fil)
    funnet = _finn_overskrift(ark)
    if funnet is None:
        alle = {_norm(v): str(v).strip() for df in ark.values()
                for v in df.head(20).to_numpy().ravel() if _norm(v)}
        lik = difflib.get_close_matches("elever", list(alle), n=1, cutoff=0.6)
        hint = f" Fant «{alle[lik[0]]}» – skal den hete «Elever»?" if lik else ""
        raise FordelingsFeil(
            "Fant ingen kolonne som heter «Elever» i fila. Overskriften må stå "
            "i en egen rad over navnene." + hint
        )
    arknavn, df, rad_nr, overskrifter = funnet
    advarsler = []

    kol_elev = overskrifter.index("elever")
    kol_stipp = overskrifter.index("stipp") if "stipp" in overskrifter else None
    if kol_stipp is None:
        andre = {h: str(df.iat[rad_nr, k]).strip() for k, h in enumerate(overskrifter)
                 if h and k != kol_elev}
        lik = difflib.get_close_matches("stipp", list(andre), n=1, cutoff=0.6)
        if lik:
            advarsler.append(
                f"Fant ingen kolonne «Stipp», men kolonnen «{andre[lik[0]]}» ligner. "
                "Alle er derfor behandlet som vanlige elever. Rett overskriften til "
                "«Stipp» hvis det var meningen."
            )

    stipper, elever = [], []
    ukjente = {}  # ukjent verdi -> navn
    for _, rad in df.iloc[rad_nr + 1:].iterrows():
        navn = "" if pd.isna(rad.iloc[kol_elev]) else str(rad.iloc[kol_elev]).strip()
        if not navn:
            continue
        rolle = _norm(rad.iloc[kol_stipp]) if kol_stipp is not None else ""
        if rolle == "stipp":
            stipper.append(navn)
        else:
            elever.append(navn)
            if rolle:
                ukjente.setdefault(str(rad.iloc[kol_stipp]).strip(), []).append(navn)

    if arknavn != next(iter(ark)):
        advarsler.append(f"Navnene ble lest fra arket «{arknavn}».")
    for verdi, navn in ukjente.items():
        advarsler.append(
            f"Ukjent verdi «{verdi}» i Stipp-kolonnen for {_liste(navn)}. "
            "De er behandlet som vanlige elever. Bare «stipp» eller tom celle er gyldig."
        )
    doble = [n for n, c in Counter(stipper + elever).items() if c > 1]
    if doble:
        advarsler.append(
            f"Disse navnene står flere ganger i lista: {_liste(doble)}. Hver forekomst "
            "får sin egen plass. Fjern dobbeltføringer, eller skill personene "
            "med f.eks. etternavn."
        )
    return stipper, elever, advarsler


def _liste(navn, maks=5):
    tekst = ", ".join(navn[:maks])
    return tekst + (f" og {len(navn) - maks} til" if len(navn) > maks else "")


def som_dataframe(bordliste):
    """Én kolonne per bord, kortere bord fylles ut med tomme celler."""
    lengst = max(len(m) for _, m in bordliste)
    return pd.DataFrame({
        f"Bord {nr}": m + [""] * (lengst - len(m)) for nr, m in bordliste
    })


def lag_excel(ark):
    """Lager en Excel-fil i minnet. ``ark`` er {arknavn: DataFrame}."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        for navn, df in ark.items():
            df.to_excel(xl, sheet_name=navn, index=False)
    return buf.getvalue()


def lag_zip(tabeller):
    """Én CSV per uke. ``tabeller`` er {ukenavn: DataFrame}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for navn, df in tabeller.items():
            # utf-8-sig (BOM) gjør at Excel viser æ, ø og å riktig
            z.writestr(f"Bordfordeling_{navn.replace(' ', '_')}.csv",
                       df.to_csv(index=False).encode("utf-8-sig"))
    return buf.getvalue()


# ---------------------------------------------------------------- grensesnitt
st.title("Bordfordeling")
st.caption(
    "🔒 Navnene du laster opp lagres ikke. De brukes bare i minnet mens siden er "
    "åpen og forsvinner når du lukker fanen eller trykker «Nullstill»."
)

EKSEMPEL = pd.DataFrame({
    "Elever": ["Ola Nordmann", "Kari Hansen", "Per Olsen", "Lise Berg",
               "Ahmed Ali", "Sofie Lie", "Jonas Dahl", "Emma Moe"],
    "Stipp": ["", "", "stipp", "", "", "stipp", "", ""],
})


with st.expander("Hvordan skal fila se ut? (se eksempel)", expanded=True):
    st.markdown(
        "Last opp en Excel-fil (`.xlsx`) eller CSV med disse overskriftene:\n\n"
        "- **Elever** – ett navn per rad (påkrevd).\n"
        "- **Stipp** – valgfri. La cellen stå tom for vanlige elever, skriv `stipp` "
        "for personer som skal spres utover bordene (helst én per bord). "
        "Alle i lista får bordplass.\n\n"
        "Store og små bokstaver spiller ingen rolle, andre kolonner hoppes over, og "
        "navnelista kan ligge i hvilket som helst ark."
    )
    eks1, eks2 = st.columns([2, 1])
    eks1.dataframe(EKSEMPEL, hide_index=True, width="stretch")
    eks2.markdown("Slik ser fila ut i Excel. Last ned eksempelet, bytt ut navnene "
                  "og last det opp igjen.")
    eks2.download_button(
        "Last ned eksempelfil", lag_excel({"Navneliste": EKSEMPEL}),
        file_name="Eksempel_navneliste.xlsx", mime=XLSX_MIME, width="stretch",
    )

elevfil = st.file_uploader("Last opp navneliste", type=["xlsx", "csv"])
col1, col2 = st.columns(2)

antall_bord = col1.number_input("Antall bord", min_value=1, max_value=60, value=10)
minimum = col1.number_input("Minimum personer per bord", min_value=1, max_value=8, value=4)
start_uke = col1.number_input("Første uke", min_value=1, max_value=52, value=1)
slutt_uke = col1.number_input("Siste uke", min_value=1, max_value=52, value=1)

like_store = col2.checkbox("Alle bord har like mange plasser", value=True)
if like_store:
    p = col2.number_input("Plasser per bord", min_value=1, max_value=40, value=7)
    plasser_per_bord = [int(p)] * int(antall_bord)
else:
    plasser_per_bord = [
        int(col2.number_input(f"Plasser ved bord {i + 1}", min_value=1, max_value=40,
                              value=7, key=f"plasser_{i}"))
        for i in range(int(antall_bord))
    ]

knapp1, knapp2 = col1.columns(2)
if knapp2.button("Nullstill", width="stretch"):
    st.session_state.pop("resultat", None)
    st.rerun()

if knapp1.button("Generer bordfordeling", type="primary", width="stretch"):
    st.session_state.pop("resultat", None)
    if elevfil is None:
        st.error("Last opp en navneliste først!")
        st.stop()
    if slutt_uke < start_uke:
        st.error("Siste uke kan ikke være før første uke.")
        st.stop()
    try:
        stipper, elever, advarsler = les_navneliste(elevfil)
        antall_uker = int(slutt_uke - start_uke + 1)
        linje = st.progress(0.0, text="Lager fordeling …")
        uker, stat = generer_uker(
            stipper, elever, plasser_per_bord, int(minimum), antall_uker,
            framdrift=lambda i, n: linje.progress(i / n, text=f"Uke {i} av {n} ferdig"),
        )
        linje.empty()
    except FordelingsFeil as e:
        st.error(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001 – vis en lesbar feil, ikke navn/data
        st.error(f"Noe gikk galt ({type(e).__name__}). Sjekk fila og innstillingene.")
        st.stop()

    tabeller = {f"Uke {int(start_uke) + i}": som_dataframe(b) for i, b in enumerate(uker)}
    oversikt = pd.DataFrame(stat["per_person"], columns=["Navn", "Antall ulike bordkamerater"])
    st.session_state["resultat"] = {
        "tabeller": tabeller, "stat": stat, "advarsler": advarsler,
        "zip": lag_zip(tabeller),
        "xlsx": lag_excel({**tabeller, "Oversikt": oversikt}),
    }

res = st.session_state.get("resultat")
if res:
    stat, tabeller = res["stat"], res["tabeller"]
    ulike = [u for _, u in stat["per_person"]]
    st.success("Bordfordeling generert!")
    for advarsel in res["advarsler"]:
        st.warning(advarsel, icon="⚠️")
    m1, m2, m3 = st.columns(3)
    m1.metric("Snitt ulike bordkamerater", f"{sum(ulike) / len(ulike):.1f}")
    m2.metric("Færrest ulike bordkamerater", min(ulike))
    m3.metric("Par som har sittet sammen mer enn én gang", stat["gjentatte_par"])

    d1, d2 = st.columns(2)
    d1.download_button("Last ned Excel (alle uker)", res["xlsx"],
                       file_name="Bordfordeling.xlsx", mime=XLSX_MIME, width="stretch")
    d2.download_button("Last ned alle ukene som ZIP (CSV)", res["zip"],
                       file_name="Alle_bordfordelinger.zip", mime="application/zip",
                       width="stretch")

    for fane, df in zip(st.tabs(list(tabeller)), tabeller.values()):
        fane.dataframe(df, hide_index=True, width="stretch")
