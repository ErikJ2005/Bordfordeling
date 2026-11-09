# Kjør lokalt:  streamlit run Bord.py
#
# Personvern: Opplastede navn og genererte fordelinger lagres aldri på disk
# og logges ikke. Alt holdes kun i minnet for den åpne nettleserøkten.
# Publisert via index.html (stlite) kjører hele appen i brukerens nettleser,
# så navnene sendes ikke til noen server i det hele tatt.

import io
import zipfile

import pandas as pd
import streamlit as st

from fordeling import FordelingsFeil, generer_uker

st.set_page_config(page_title="Bordfordeling", layout="wide")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
        if not navn:
            continue
        (stipper if r == "stipp" else elever).append(navn)
    return stipper, elever


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
        "Last opp en Excel-fil (`.xlsx`) eller CSV. Første rad må være overskrifter:\n\n"
        "- **Elever** – ett navn per rad (påkrevd).\n"
        "- **Stipp** – valgfri. La cellen stå tom for vanlige elever, skriv `stipp` "
        "for personer som skal spres utover bordene (helst én per bord). "
        "Alle i lista får bordplass."
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
        stipper, elever = les_navneliste(elevfil)
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
        st.error(f"Kunne ikke lese fila: {type(e).__name__}")
        st.stop()

    tabeller = {f"Uke {int(start_uke) + i}": som_dataframe(b) for i, b in enumerate(uker)}
    oversikt = pd.DataFrame(stat["per_person"], columns=["Navn", "Antall ulike bordkamerater"])
    st.session_state["resultat"] = {
        "tabeller": tabeller, "stat": stat,
        "zip": lag_zip(tabeller),
        "xlsx": lag_excel({**tabeller, "Oversikt": oversikt}),
    }

res = st.session_state.get("resultat")
if res:
    stat, tabeller = res["stat"], res["tabeller"]
    ulike = [u for _, u in stat["per_person"]]
    st.success("Bordfordeling generert!")
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
