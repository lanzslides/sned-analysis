"""
match_sned_to_facilities.py

Fuzzy-matches SNED_ENR school records (no school ID) to FACILITIES records
(ILRCs / SPED Centers / SNED Implementing Schools -- all of which DO carry a
school_id) via geographic blocking on (province, municipality) + fuzzy name
matching within each block.

Deliberately conservative: a single high threshold (default 99), no
"review" tier. Anything below the threshold is treated as no_match rather
than flagged for manual review -- false negatives (a real facility left
unmatched) are preferable here to false positives (two different schools
merged as one).

Only run this against the UNIQUE (School_name, Province, Municipality,
Barangay) combinations from SNED_ENR, not the full 66M-row long table --
build the crosswalk on the small unique-school set, then merge it back:

    sned_schools = (
        SNED_ENR[["School_name", "Province", "Municipality", "Barangay"]]
        .drop_duplicates()
    )
    crosswalk = match_sned_to_facilities(sned_schools, FACILITIES)
    SNED_ENR = SNED_ENR.merge(
        crosswalk[["School_name", "Province", "Municipality", "Barangay",
                   "school_id", "match_score", "is_match"]],
        on=["School_name", "Province", "Municipality", "Barangay"],
        how="left",
    )
"""
import re

import pandas as pd
from rapidfuzz import fuzz, process

_ABBREV = {
    r"\bCES\b": "CENTRAL ELEMENTARY SCHOOL",
    r"\bICHS\b": "INTEGRATED COMMUNITY HIGH SCHOOL",
    r"\bNHS\b": "NATIONAL HIGH SCHOOL",
    r"\bES\b": "ELEMENTARY SCHOOL",
    r"\bIS\b": "INTEGRATED SCHOOL",
    r"\bHS\b": "HIGH SCHOOL",
    r"\bSPED\b": "SPECIAL EDUCATION",
    r"\bELEM\b": "ELEMENTARY",
    r"\bSCH\b": "SCHOOL",
    r"\bMEM\b": "MEMORIAL",
    r"\bBRGY\b": "BARANGAY",
    r"\bSTA\b": "SANTA",
    r"\bSTO\b": "SANTO",
}
_PUNCT_RE = re.compile(r"[.,\-/'’()]")
_WS_RE = re.compile(r"\s+")


def normalize_name(name):
    if pd.isna(name):
        return ""
    s = _PUNCT_RE.sub(" ", str(name).upper())
    for pat, repl in _ABBREV.items():
        s = re.sub(pat, repl, s)
    return _WS_RE.sub(" ", s).strip()


def normalize_place(name):
    if pd.isna(name):
        return ""
    s = _PUNCT_RE.sub(" ", str(name).upper().strip())
    return _WS_RE.sub(" ", s).strip()


# Standalone tokens that distinguish otherwise-identical school names, e.g.
# "Kabayan I ES" vs "Kabayan II ES" or "Marbel 3 ES" vs "Marbel 6 ES" --
# token_sort_ratio scores these very high (every other token matches) but a
# differing ordinal almost always means a different school.
_ROMAN_TOKENS = {
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"
}


def _ordinal_tokens(name):
    return {t for t in name.split() if t.isdigit() or t in _ROMAN_TOKENS}


def _ordinals_conflict(name_a, name_b):
    a, b = _ordinal_tokens(name_a), _ordinal_tokens(name_b)
    return bool(a) and bool(b) and a != b


def match_sned_to_facilities(
    sned_schools,
    facilities,
    sned_name_col="School_name",
    sned_province_col="Province",
    sned_municipality_col="Municipality",
    sned_barangay_col="Barangay",
    fac_name_col="school_name",
    fac_province_col="province",
    fac_municipality_col="municipality",
    fac_barangay_col="barangay",
    fac_id_col="school_id",
    threshold=99,
    scorer=fuzz.token_sort_ratio,
):
    """
    Returns sned_schools with columns added:
      - <fac_id_col>   : matched FACILITIES school_id (NA if no match)
      - matched_name   : the FACILITIES school_name that was matched
      - match_score    : rapidfuzz similarity (0-100) on normalized names
      - is_match       : True iff score >= threshold AND no ordinal conflict
      - barangay_agrees: whether normalized barangay also matches (extra
                          verification signal only -- doesn't gate is_match,
                          since barangay entries are noisier than province/
                          municipality)

    Blocking is done on (province, municipality) so names are only ever
    compared against candidates in the same LGU -- keeps runtime down and
    avoids false positives between same-named schools in different
    municipalities.
    """
    sned = sned_schools.copy()
    fac = facilities.copy()

    sned["_name_norm"] = sned[sned_name_col].map(normalize_name)
    sned["_prov_norm"] = sned[sned_province_col].map(normalize_place)
    sned["_muni_norm"] = sned[sned_municipality_col].map(normalize_place)
    sned["_brgy_norm"] = (
        sned[sned_barangay_col].map(normalize_place) if sned_barangay_col in sned else ""
    )

    fac["_name_norm"] = fac[fac_name_col].map(normalize_name)
    fac["_prov_norm"] = fac[fac_province_col].map(normalize_place)
    fac["_muni_norm"] = fac[fac_municipality_col].map(normalize_place)
    fac["_brgy_norm"] = (
        fac[fac_barangay_col].map(normalize_place) if fac_barangay_col in fac else ""
    )

    fac_blocks = {
        key: grp[["_name_norm", "_brgy_norm", fac_id_col, fac_name_col]].reset_index(drop=True)
        for key, grp in fac.groupby(["_prov_norm", "_muni_norm"])
    }

    school_ids, matched_names, scores, is_match, brgy_agrees = [], [], [], [], []

    for _, row in sned.iterrows():
        block = fac_blocks.get((row["_prov_norm"], row["_muni_norm"]))
        if block is None or block.empty or not row["_name_norm"]:
            school_ids.append(pd.NA)
            matched_names.append(pd.NA)
            scores.append(0)
            is_match.append(False)
            brgy_agrees.append(False)
            continue

        result = process.extractOne(row["_name_norm"], block["_name_norm"], scorer=scorer)
        if result is None:
            school_ids.append(pd.NA)
            matched_names.append(pd.NA)
            scores.append(0)
            is_match.append(False)
            brgy_agrees.append(False)
            continue

        _, score, idx = result
        match_row = block.iloc[idx]
        matched = score >= threshold and not _ordinals_conflict(row["_name_norm"], match_row["_name_norm"])

        school_ids.append(match_row[fac_id_col])
        matched_names.append(match_row[fac_name_col])
        scores.append(score)
        is_match.append(matched)
        brgy_agrees.append(bool(row["_brgy_norm"]) and row["_brgy_norm"] == match_row["_brgy_norm"])

    sned[fac_id_col] = school_ids
    sned["matched_name"] = matched_names
    sned["match_score"] = scores
    sned["is_match"] = is_match
    sned["barangay_agrees"] = brgy_agrees

    # Unmatched rows carry no meaningful school_id / matched_name
    sned.loc[~sned["is_match"], [fac_id_col, "matched_name"]] = pd.NA

    return sned.drop(columns=["_name_norm", "_prov_norm", "_muni_norm", "_brgy_norm"])


def flag_duplicate_matches(crosswalk, fac_id_col="school_id"):
    """
    Facility rows matched (is_match=True) by more than one SNED_ENR school --
    signals a normalization gap (two distinct schools collapsing to the same
    normalized name) rather than a genuine one-to-many relationship. Inspect
    these before trusting the crosswalk.
    """
    matched = crosswalk[crosswalk["is_match"]]
    dupe_ids = matched[fac_id_col][matched[fac_id_col].duplicated(keep=False)].unique()
    return matched[matched[fac_id_col].isin(dupe_ids)].sort_values(fac_id_col)
