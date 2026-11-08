# Kjør lokalt:  streamlit run Bord.py
#
# Personvern: Opplastede navn og genererte fordelinger lagres aldri på disk
# og logges ikke. Alt holdes kun i minnet for den åpne nettleserøkten.
# Publisert via index.html (stlite) kjører hele appen i brukerens nettleser,
# så navnene sendes ikke til noen server i det hele tatt.

import csv
import io
import zipfile

import pandas as pd
import streamlit as st

from fordeling import FordelingsFeil, generer_uker

st.set_page_config(page_title="Bordfordeling", layout="wide")

INNSATS = {"Rask": 0.25, "Normal": 0.6, "Grundig": 1.5}


def les_navneliste(fil):
    """Leser Excel/CSV med kolonnene 'Elever' og (valgfritt) 'Stipp'."""
    if fil.name.lower().endswith(".csv"):
        raw = fil.getvalue()
        try:
            tekst = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            tekst = raw.decode("cp1252")
        df = pd.read_csv(io.StringIO(tekst), sep=None, engine="python", dtype=str)
    else:
        df = pd.read_excel(fil, engine="openpyxl", dtype=str)

    df.columns = [str(c).strip() for c in df.columns]
    if "Elever" not in df.columns:
        raise FordelingsFeil("Fila må ha en kolonne som heter «Elever».")
    rolle = df["Stipp"] if "Stipp" in df.columns else pd.Series([""] * len(df))
    # Les navn og rolle rad for rad, så kolonnene ikke kommer i utakt
    stipper, elever = [], []
    for navn, r in zip(df["Elever"].fillna(""), rolle.fillna("")):
        navn, r = str(navn).strip(), str(r).strip().lower()
        if not navn or r == "etasje":
            continue
        (stipper if r == "stipp" else elever).append(navn)
    return stipper, elever


def lag_csv(bordliste):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Bord {nr}" for nr, _ in bordliste])
    lengst = max(len(m) for _, m in bordliste)
    for rad in range(lengst):
        w.writerow([m[rad] if rad < len(m) else "" for _, m in bordliste])
    # BOM gjør at Excel viser æ, ø og å riktig
    return "﻿" + buf.getvalue()


def som_dataframe(bordliste):
    lengst = max(len(m) for _, m in bordliste)
    return pd.DataFrame({
        f"Bord {nr}": m + [""] * (lengst - len(m)) for nr, m in bordliste
    })


def lag_zip(uker, start_uke):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, bordliste in enumerate(uker):
            z.writestr(f"Bordfordeling_uke{start_uke + i}.csv", lag_csv(bordliste))
    return buf.getvalue()


def lag_excel(uker, start_uke, stat):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        for i, bordliste in enumerate(uker):
            som_dataframe(bordliste).to_excel(xl, sheet_name=f"Uke {start_uke + i}", index=False)
        pd.DataFrame(stat["per_person"], columns=["Navn", "Antall ulike bordkamerater"]) \
            .to_excel(xl, sheet_name="Oversikt", index=False)
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
    "Stipp": ["", "", "stipp", "", "", "stipp", "", "etasje"],
})


def lag_eksempelfil():
    buf = io.BytesIO()
    EKSEMPEL.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


with st.expander("Hvordan skal fila se ut? (se eksempel)", expanded=True):
    st.markdown(
        "Last opp en Excel-fil (`.xlsx`) eller CSV. Første rad må være overskrifter:\n\n"
        "- **Elever** – ett navn per rad (påkrevd).\n"
        "- **Stipp** – valgfri. La cellen stå tom for vanlige elever, skriv `stipp` "
        "for personer som skal spres utover bordene (helst én per bord), eller "
        "`etasje` for personer som ikke skal ha bordplass."
    )
    eks1, eks2 = st.columns([2, 1])
    eks1.dataframe(EKSEMPEL, hide_index=True, width="stretch")
    eks2.markdown("Slik ser fila ut i Excel. Last ned eksempelet, bytt ut navnene "
                  "og last det opp igjen.")
    eks2.download_button(
        "Last ned eksempelfil", lag_eksempelfil(), file_name="Eksempel_navneliste.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

elevfil = st.file_uploader("Last opp navneliste", type=["xlsx", "csv"])
col1, col2 = st.columns(2)

antall_bord = col1.number_input("Antall bord", min_value=1, max_value=60, value=10)
minimum = col1.number_input("Minimum personer per bord", min_value=1, max_value=8, value=4)
start_uke = col1.number_input("Første uke", min_value=1, max_value=52, value=1)
slutt_uke = col1.number_input("Siste uke", min_value=1, max_value=52, value=1)
innsats = col1.select_slider(
    "Søkeinnsats", options=list(INNSATS), value="Normal",
    help="Grundig gir litt færre gjentatte bordkamerater, men tar lengre tid.",
)

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
        stipper, elever = les_navneliste(elevfil)
        antall_uker = int(slutt_uke - start_uke + 1)
        linje = st.progress(0.0, text="Lager fordeling …")
        uker, stat = generer_uker(
            stipper, elever, plasser_per_bord, int(minimum), antall_uker,
            innsats=INNSATS[innsats],
            framdrift=lambda i, n: linje.progress(i / n, text=f"Uke {i} av {n} ferdig"),
        )
        linje.empty()
    except FordelingsFeil as e:
        st.error(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001 – vis en lesbar feil, ikke navn/data
        st.error(f"Kunne ikke lese fila: {type(e).__name__}")
        st.stop()

    st.session_state["resultat"] = {
        "uker": uker, "stat": stat, "start": int(start_uke),
        "zip": lag_zip(uker, int(start_uke)),
        "xlsx": lag_excel(uker, int(start_uke), stat),
    }

res = st.session_state.get("resultat")
if res:
    stat, uker = res["stat"], res["uker"]
    ulike = [u for _, u in stat["per_person"]]
    st.success("Bordfordeling generert!")
    m1, m2, m3 = st.columns(3)
    m1.metric("Snitt ulike bordkamerater", f"{sum(ulike) / len(ulike):.1f}")
    m2.metric("Færrest ulike bordkamerater", min(ulike))
    m3.metric("Par som har sittet sammen mer enn én gang", stat["gjentatte_par"])

    d1, d2 = st.columns(2)
    d1.download_button("Last ned Excel (alle uker)", res["xlsx"],
                       file_name="Bordfordeling.xlsx", width="stretch",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d2.download_button("Last ned alle ukene som ZIP (CSV)", res["zip"],
                       file_name="Alle_bordfordelinger.zip", mime="application/zip",
                       width="stretch")

    faner = st.tabs([f"Uke {res['start'] + i}" for i in range(len(uker))])
    for fane, bordliste in zip(faner, uker):
        fane.dataframe(som_dataframe(bordliste), hide_index=True, width="stretch")
