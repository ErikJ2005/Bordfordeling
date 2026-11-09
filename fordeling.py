"""Algoritmen for bordfordeling.

Ingen filer skrives og ingenting logges: alt skjer i minnet.

Idé
---
Vi holder en tellematrise ``treff[i][j]`` = antall uker person i og j har
sittet ved samme bord. Hver uke søker vi etter en fordeling som minimerer

    sum over alle par ved samme bord av  treff[i][j] ** 2

Kvadratet gjør at et par som allerede har sittet sammen to ganger er mye
"dyrere" enn to par som har sittet sammen én gang, så gjentakelser spres
jevnt og alle får sitte med flest mulig forskjellige.

Søket er simulert gløding (simulated annealing) med bytter mellom to
personer av samme type (stipp <-> stipp, elev <-> elev) ved forskjellige
bord. Kostnadsendringen for et bytte regnes ut i O(1) ved hjelp av
``S[p][b]`` = summen av straff mellom person p og alle ved bord b, så hvert
forsøk er svært billig sammenlignet med å regne ut hele scoren på nytt.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


class FordelingsFeil(ValueError):
    """Feil som skal vises til brukeren."""


@dataclass
class Bordplan:
    bord_indeks: int  # hvilket fysisk bord (0-basert)
    stipp_plasser: int
    elev_plasser: int

    @property
    def storrelse(self) -> int:
        return self.stipp_plasser + self.elev_plasser


def lag_bordplan(antall_stipper, antall_elever, plasser_per_bord, minimum, rng):
    """Bestem hvor mange som skal sitte ved hvert bord.

    * Bruker så mange bord som mulig så lenge hvert bord får minst ``minimum``.
    * Fordeler folk så jevnt som mulig, innenfor kapasiteten til hvert bord.
    * Stipper spres jevnt (maks én per bord når det er nok bord).
    """
    n = antall_stipper + antall_elever
    if n == 0:
        raise FordelingsFeil("Fant ingen navn i fila.")
    kapasitet = sum(plasser_per_bord)
    if n > kapasitet:
        raise FordelingsFeil(
            f"Det er {n} personer, men bare {kapasitet} plasser totalt. "
            "Legg til flere bord eller plasser."
        )

    # Største bord først (stabil sortering beholder rekkefølgen ved likhet)
    rekkefolge = sorted(range(len(plasser_per_bord)), key=lambda i: -plasser_per_bord[i])
    antall = max(1, min(len(plasser_per_bord), n // max(1, minimum)))
    while sum(plasser_per_bord[i] for i in rekkefolge[:antall]) < n:
        antall += 1
    valgte = sorted(rekkefolge[:antall])
    kap = [plasser_per_bord[i] for i in valgte]

    # Jevn fordeling ("vannfylling"): gi neste person til minste bord med plass
    storrelser = [0] * antall
    for _ in range(n):
        j = min(
            (k for k in range(antall) if storrelser[k] < kap[k]),
            key=lambda k: (storrelser[k], -(kap[k] - storrelser[k])),
        )
        storrelser[j] += 1

    # Stipper: jevnt fordelt, tilfeldig hvilke bord som får ekstra
    stipp = [0] * antall
    rest = antall_stipper
    while rest > 0:
        kandidater = [k for k in range(antall) if stipp[k] < storrelser[k]]
        minst = min(stipp[k] for k in kandidater)
        kandidater = [k for k in kandidater if stipp[k] == minst]
        rng.shuffle(kandidater)
        for k in kandidater[:rest]:
            stipp[k] += 1
            rest -= 1

    return [
        Bordplan(valgte[k], stipp[k], storrelser[k] - stipp[k]) for k in range(antall)
    ]


def _straff(antall_ganger: int) -> float:
    return float(antall_ganger * antall_ganger)


def _fordel_en_uke(antall_stipper, plan, W, rng, iterasjoner):
    """Returnerer (bord_for_person, kostnad) for én uke.

    ``W[i][j]`` er straffen for at i og j sitter ved samme bord.
    """
    T = len(plan)
    n = len(W)

    # Startløsning: tilfeldig, men respekterer stipp-/elevplasser.
    # Gruppene brukes også senere: bare personer i samme gruppe byttes.
    grupper = [list(range(antall_stipper)), list(range(antall_stipper, n))]
    for g in grupper:
        rng.shuffle(g)
    koer = [iter(g) for g in grupper]
    bord_for = [0] * n
    for b, p in enumerate(plan):
        for ko, plasser in zip(koer, (p.stipp_plasser, p.elev_plasser)):
            for _ in range(plasser):
                bord_for[next(ko)] = b

    # S[p][b] = sum av straff mellom p og alle ved bord b
    S = [[0.0] * T for _ in range(n)]
    for p in range(n):
        Wp, Sp = W[p], S[p]
        for q in range(n):
            Sp[bord_for[q]] += Wp[q]
    kostnad = sum(S[p][bord_for[p]] for p in range(n)) / 2

    if kostnad == 0 or iterasjoner <= 0 or T < 2:
        return bord_for, kostnad

    grupper = [g for g in grupper if len(g) > 1]
    if not grupper:
        return bord_for, kostnad
    vekter = [len(g) for g in grupper]

    beste, beste_kostnad = bord_for[:], kostnad
    temp0, temp1 = 2.0, 0.02
    faktor = (temp1 / temp0) ** (1.0 / iterasjoner)
    temp = temp0
    rand, randrange, exp = rng.random, rng.randrange, math.exp

    for _ in range(iterasjoner):
        temp *= faktor
        g = grupper[0] if len(grupper) == 1 else rng.choices(grupper, vekter)[0]
        a = g[randrange(len(g))]
        b = g[randrange(len(g))]
        A, B = bord_for[a], bord_for[b]
        if A == B:
            continue
        Sa, Sb = S[a], S[b]
        wab = W[a][b]
        delta = (Sa[B] - wab - Sa[A]) + (Sb[A] - wab - Sb[B])
        if delta <= 0 or rand() < exp(-delta / temp):
            bord_for[a], bord_for[b] = B, A
            Wa, Wb = W[a], W[b]
            for p in range(n):
                d = Wa[p] - Wb[p]
                if d:
                    Sp = S[p]
                    Sp[A] -= d
                    Sp[B] += d
            kostnad += delta
            if kostnad < beste_kostnad - 1e-9:
                beste, beste_kostnad = bord_for[:], kostnad
                if beste_kostnad <= 0:
                    break

    return beste, beste_kostnad


def generer_uker(stipper, elever, plasser_per_bord, minimum, antall_uker,
                 seed=None, framdrift=None):
    """Lag bordfordeling for flere uker.

    Returnerer en liste (én per uke) med lister av bord. Hvert bord er
    ``(bordnummer, [navn, ...])`` der stipper står først.
    """
    rng = random.Random(seed)
    navn = list(stipper) + list(elever)
    n = len(navn)
    ns = len(stipper)
    treff = [[0] * n for _ in range(n)]
    resultat = []

    iterasjoner = max(3000, 240 * n)
    omstarter = 3

    for uke in range(antall_uker):
        plan = lag_bordplan(ns, n - ns, plasser_per_bord, minimum, rng)
        W = [[_straff(c) for c in rad] for rad in treff]
        beste, beste_kost = None, float("inf")
        for _ in range(omstarter):
            bord_for, kost = _fordel_en_uke(ns, plan, W, rng, iterasjoner)
            if kost < beste_kost:
                beste, beste_kost = bord_for, kost
            if beste_kost <= 0:
                break

        medlemmer = [[] for _ in plan]
        for p, b in enumerate(beste):
            medlemmer[b].append(p)
        for m in medlemmer:
            for i, p in enumerate(m):
                rad = treff[p]
                for q in m[i + 1:]:
                    rad[q] += 1
                    treff[q][p] += 1

        resultat.append([
            (plan[b].bord_indeks + 1, [navn[p] for p in sorted(m)])
            for b, m in enumerate(medlemmer)
        ])
        if framdrift:
            framdrift(uke + 1, antall_uker)

    return resultat, statistikk(navn, treff)


def statistikk(navn, treff):
    n = len(navn)
    per_person = []
    gjentatte_par = 0
    for i in range(n):
        ulike = sum(1 for j in range(n) if j != i and treff[i][j] > 0)
        per_person.append((navn[i], ulike))
        for j in range(i + 1, n):
            if treff[i][j] > 1:
                gjentatte_par += 1
    return {"per_person": per_person, "gjentatte_par": gjentatte_par}
