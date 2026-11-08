#streamlit run Bord.py

import streamlit as st
import csv
import random
import io
import zipfile
import pandas as pd

def tell_felles_sittinger(historikk, person1, person2):
    """Teller hvor mange ganger to personer har sittet ved samme bord"""
    felles = 0
    for ukebord in historikk:
        for bord in ukebord:
            if person1 in bord and person2 in bord:
                felles += 1
    return felles

def evaluer_bordplassering(bord, historikk):
    """Gir en score til bordplasseringen basert på tidligere plasseringer"""
    score = 0
    for bordmedlemmer in bord:
        for i, person1 in enumerate(bordmedlemmer):
            for person2 in bordmedlemmer[i+1:]:
                score += tell_felles_sittinger(historikk, person1, person2)
    return score

def fordel_bord(stipper, elever, plasser_per_bord, historikk=None):
    if historikk is None:
        historikk = []
    
    beste_bord = None
    beste_score = float('inf')
    
    # Prøv flere tilfeldige kombinasjoner og velg den beste
    for _ in range(100):  # Antall forsøk per uke
        random.shuffle(stipper)
        random.shuffle(elever)
        bord = []
        elev_idx = 0
        stipp_idx = 0
        
        # Beregn minimum antall elever per bord
        gjenværende_elever = len(elever)
        gjenværende_bord = len(plasser_per_bord)
        
        valid = True
        # Velg hvilke bord som skal få en stipp (én per bord, tilfeldig)
        num_bord = len(plasser_per_bord)
        k = min(len(stipper), num_bord)
        stipp_table_indices = set(random.sample(range(num_bord), k)) if k > 0 else set()

        for i, plasser in enumerate(plasser_per_bord):
            bordmedlemmer = []
            # Legg til stipp hvis dette bordet er valgt for stipp
            if i in stipp_table_indices and stipp_idx < len(stipper):
                bordmedlemmer.append(stipper[stipp_idx])
                stipp_idx += 1
                antall_elever = min(plasser - 1, max(minimum_mennesker_per_bord, gjenværende_elever // gjenværende_bord))
            else:
                antall_elever = min(plasser, max(minimum_mennesker_per_bord, gjenværende_elever // gjenværende_bord))

            # Fyll på med elever
            for _ in range(antall_elever):
                if elev_idx < len(elever):
                    bordmedlemmer.append(elever[elev_idx])
                    elev_idx += 1
                    gjenværende_elever -= 1

            bord.append(bordmedlemmer)
            gjenværende_bord -= 1
        
        if not valid:
            continue
        
        # Fordel eventuelle gjenværende elever
        while elev_idx < len(elever):
            for b in bord:
                if len(b) < plasser_per_bord[bord.index(b)] and elev_idx < len(elever):
                    b.append(elever[elev_idx])
                    elev_idx += 1
        
        score = evaluer_bordplassering(bord, historikk)
        if score < beste_score:
            beste_score = score
            beste_bord = bord
    
    return beste_bord


plasser_per_bord = []

st.set_page_config(page_title="Fordelings App", layout="wide")

st.sidebar.subheader("Oversikt")
optinon = st.sidebar.selectbox("velg hva du vil fordele", ("Bordfordeling"))


if optinon == "Bordfordeling":
    elevfil = st.file_uploader("Last opp elevliste (CSV)", type=["xlsx"])
    col1, col2 = st.columns([0.5, 0.5])

    antall_bord = col1.number_input("Antall bord", min_value=1, max_value=60, value=10)
    minimum_mennesker_per_bord = col1.number_input("Minimum mennesker per bord", min_value=1, max_value=8, value=4)
    start_uke = col1.number_input("Start uke", min_value=1, max_value=52, value=1)
    slutt_uke = col1.number_input("Siste uke", min_value=1, max_value=52, value=1)

    plasser_per_bord = []
    for i in range(antall_bord):
        p = col2.number_input(
            f"Plasser ved bord {i+1}",
            min_value=1,
            max_value=40,
            value=7,
            step=1,
            key=f"plasser_{i}"
        )
        plasser_per_bord.append(p)

if col1.button("Generer bordfordeling"):
    if elevfil is None:
        st.error("Last opp en CSV-fil først!")
        st.stop()

    # Les navnefilen brukeren lastet opp
    stipper = []
    elever = []
    df = pd.read_excel(elevfil, engine="openpyxl")
    elevnavn = df["Elever"].dropna().astype(str).str.strip().tolist()
    rom = df["Stipp"].dropna().astype(str).str.strip().tolist()
    for i, elev in enumerate(elevnavn):
        if rom[i] != "etasje":
            if rom[i] != "stipp":
                elever.append(elev)
            else:
                stipper.append(elev)

    historikk = []
    zip_buffer = io.BytesIO()

    # Lag ZIP i minne
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

        for uke in range(start_uke, slutt_uke + 1):
            bord = fordel_bord(stipper, elever, plasser_per_bord, historikk)
            historikk.append(bord)

            # Lag CSV i minne
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)

            max_len = max(len(b) for b in bord)
            writer.writerow([f"Bord {i+1}" for i in range(len(bord))])

            for rad in range(max_len):
                row = []
                for b in bord:
                    row.append(b[rad] if rad < len(b) else "")
                writer.writerow(row)

            # Legg CSV i ZIP-fila
            zipf.writestr(f"Bordfordeling_uke{uke}.csv", csv_buffer.getvalue())

    st.success("Bordfordeling generert!")

    # Ferdig ZIP – vis nedlastingsknapp
    col1.download_button(
        label="Last ned alle ukene som ZIP",
        data=zip_buffer.getvalue(),
        file_name="Alle_bordfordelinger.zip",
        mime="application/zip",
    )