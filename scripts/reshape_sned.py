#!/usr/bin/env python3
"""
reshape_sned.py

Reshapes the wide, 9-row-merged-header SNED Database into:
  - sned_database_wide_summary.csv   (one row per school, clean headers,
                                       totals recomputed from disaggregated data)
  - sned_database_tidy_long.parquet  (one row per School x Level x Program x
                                       Diagnosis Type x Category x Grade x Sex)

Speed strategy:
  1. One single streaming pass over the source file (read_only + values_only),
     instead of thousands of individual cell lookups.
  2. Split schools into "has SNED enrollment" vs "zero enrollment" using the
     SCHOOL WITH SNED LEARNERS flag (col ARL). Zero-enrollment schools skip
     leaf-value extraction and totals computation entirely -- they're just
     zero-filled.
  3. All totals/subtotals/indicators for the non-zero schools are computed
     with vectorized numpy boolean masks (no per-cell Excel formulas, no
     per-row Python loops).

Run:  python reshape_sned.py
"""

import time
import gc
from operator import itemgetter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import openpyxl
from openpyxl.utils import column_index_from_string

# ============================================================================
# CONFIG -- edit these
# ============================================================================
_ROOT = Path.cwd().parent
DATA  = _ROOT / "data"
SRC_PATH   = DATA / "edcom" / "SY 2025-2026 SNED Database (All Sector by School)_FR - (with school id).xlsx" 
SHEET_NAME = "ALL_SECTOR_BY SCHOOL"
OUT_WIDE_CSV = "sned_database_wide_summary.csv"
OUT_LONG_PARQUET = "sned_database_tidy_long.parquet"

# Pre-insertion letter -- "beis_school_id" was added at column D in the
# source workbook, shifting this (and every letter below) right by one.
# Actual position is scol(FILTER_COL_LETTER); see scol() definition below.
FILTER_COL_LETTER = "ARL"     # "School with SNED Learners" 0/1 flag column
PROGRESS_EVERY = 100         # print a progress line every N school rows read

# Schools in these Sectors are dropped entirely (not just filtered post-hoc) --
# skipped during the streaming pass so they never enter the wide summary or
# the long table.
EXCLUDED_SECTORS = {"SUCsLUCs", "PSO"}

# Long table is written in chunks of roughly this many EXPANDED rows
# (schools_per_chunk = this // n_leaf). ~2M rows/chunk keeps peak memory for
# that step in the low hundreds of MB. Lower this if you still see OOM.
LONG_TABLE_TARGET_CHUNK_ROWS = 100_000

# Sorting the ~66M-row long table back into the exact original file order
# needs a full sort of the school-level record list (cheap, ~60k items) but
# means chunks are drawn from an interleaved nz/z order instead of "all nz
# then all z". Off by default; flip to True if exact source order matters.
SORT_LONG_TABLE_BY_ORIGINAL_ORDER = False


def col(letter):
    return column_index_from_string(letter)


# "beis_school_id" was inserted at column D in the source workbook (2026-09
# update), so every column from School_name onward (all originally mapped
# constants below, which sit at O or later) shifts right by exactly one
# position: old O -> new P, old ARL -> new ARM, etc. scol() applies that
# shift on top of the already-validated pre-insertion letters rather than
# re-deriving ~40 new letters by hand.
def scol(letter):
    return col(letter) + 1


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ============================================================================
# STRUCTURE CONSTANTS -- validated against the source file's own header
# hierarchy and its embedded reference-totals row (every recomputed subtotal
# matched the original exactly: Elementary=401,027; JHS=114,415; Overall=524,160)
# ============================================================================

DIAG_CATS = [
    'Visual Impairment', 'Hearing Impairment', 'Learning Disability',
    'Intellectual Disability', 'Autism Spectrum Disorder',
    'Emotional-Behavioral Disorder', 'Orthopedic/Physical Handicap',
    'Speech/Language Disorder', 'Cerebral Palsy',
    'Special Health Problem/Chronic Disease', 'Multiple Disabilities',
]
MANIFEST_CATS = [
    'Difficulty in Seeing', 'Difficulty in Hearing',
    'Difficulty in Applying Knowledge',
    'Difficulty in Remembering, Concentrating, Paying Attention and Understanding',
    'Difficulty in Applying Adaptive Skills',
    'Difficulty in Displaying Inter-Personal Behavior',
    'Difficulty in Mobility (Walking, Climbing and Grasping)',
    'Difficulty in Communicating',
]
CATEGORIES = DIAG_CATS + MANIFEST_CATS  # 19, fixed order

ES_GRADES = ['Kindergarten', 'Grade 1', 'Grade 2', 'Grade 3', 'Grade 4', 'Grade 5', 'Grade 6']
ES_NG_LEVELS = ['Kindergarten', 'Level I', 'Level II', 'Level III', 'Transition']
JHS_GRADES = ['Grade 7', 'Grade 8', 'Grade 9', 'Grade 10']
SHS_GRADES = ['Grade 11', 'Grade 12']

DATA_BLOCKS = [
    dict(level='Elementary', program='Mainstreamed', start=scol('O'), grades=ES_GRADES),
    dict(level='Elementary', program='Self-contained', start=scol('JY'), grades=ES_GRADES),
    dict(level='Elementary', program='Non-Graded', start=scol('UI'), grades=ES_NG_LEVELS),
    dict(level='Junior High School', program='Mainstreamed', start=scol('ABY'), grades=JHS_GRADES),
    dict(level='Junior High School', program='Self-contained', start=scol('AHY'), grades=JHS_GRADES),
    dict(level='Senior High School', program='N/A', start=scol('AOC'), grades=SHS_GRADES),
]

SPACER_COLS = {scol(letter) for letter in ['JX', 'UH', 'ABX', 'AHX', 'AOB']}
# 15 info columns now (Region, Division, District, beis_school_id, School_name,
# street_address, Province, Municipality, Leg_district, Barangay, Sector,
# School_subclassification, School_type, "IU/NON-IU", "Modified Curricular
# Offering Classification") -- was 14 before beis_school_id was inserted.
INFO_COLS = list(range(1, 16))

TOTAL_GROUPS = [
    dict(cols=(scol('JU'), scol('JV'), scol('JW')), kind='subtotal',
         level='Elementary', program='Mainstreamed', label='Elementary | Mainstreamed | Subtotal'),
    dict(cols=(scol('UE'), scol('UF'), scol('UG')), kind='subtotal',
         level='Elementary', program='Self-contained', label='Elementary | Self-contained | Subtotal'),
    dict(cols=(scol('ABQ'), scol('ABR'), scol('ABS')), kind='subtotal',
         level='Elementary', program='Non-Graded', label='Elementary | Non-Graded | Subtotal'),
    dict(cols=(scol('ABT'), scol('ABU'), scol('ABV')), kind='level_total',
         label='Elementary | TOTAL SNED Learners',
         refs=[(scol('JU'), scol('JV')), (scol('UE'), scol('UF')), (scol('ABQ'), scol('ABR'))]),
    dict(cols=(scol('ABW'),), kind='indicator',
         label='Elementary | School with SNED Learners', ref=scol('ABV')),

    dict(cols=(scol('AHU'), scol('AHV'), scol('AHW')), kind='subtotal',
         level='Junior High School', program='Mainstreamed', label='Junior High School | Mainstreamed | Subtotal'),
    dict(cols=(scol('ANU'), scol('ANV'), scol('ANW')), kind='subtotal',
         level='Junior High School', program='Self-contained', label='Junior High School | Self-contained | Subtotal'),
    dict(cols=(scol('ANX'), scol('ANY'), scol('ANZ')), kind='level_total',
         label='Junior High School | TOTAL SNED Learners',
         refs=[(scol('AHU'), scol('AHV')), (scol('ANU'), scol('ANV'))]),
    dict(cols=(scol('AOA'),), kind='indicator',
         label='Junior High School | School with SNED Learners', ref=scol('ANZ')),

    dict(cols=(scol('ARA'), scol('ARB'), scol('ARC'), scol('ARD'), scol('ARE'), scol('ARF'), scol('ARG')),
         kind='shs_total', label='Senior High School | Grand Total'),
    dict(cols=(scol('ARH'),), kind='indicator',
         label='Senior High School | School with SNED Learners', ref=scol('ARG')),

    dict(cols=(scol('ARI'), scol('ARJ'), scol('ARK')), kind='overall_total',
         label='TOTAL SNED Learners (ES + JHS + SHS)',
         refs=[(scol('ABT'), scol('ABU')), (scol('ANX'), scol('ANY')), (scol('ARE'), scol('ARF'))]),
    dict(cols=(scol('ARL'),), kind='indicator',
         label='School with SNED Learners (Overall)', ref=scol('ARK')),
]


# ============================================================================
# HELPERS
# ============================================================================

def build_leaf_meta():
    leaf_meta = {}
    for blk in DATA_BLOCKS:
        n_grades = len(blk['grades'])
        cols_per_cat = n_grades * 2
        for offset in range(len(CATEGORIES) * cols_per_cat):
            c = blk['start'] + offset
            cat_idx = offset // cols_per_cat
            within = offset % cols_per_cat
            grade_idx = within // 2
            sex = 'Male' if within % 2 == 0 else 'Female'
            diag_type = ('With Diagnosis from Licensed Medical Specialist'
                         if cat_idx < 11 else 'With Manifestations')
            leaf_meta[c] = dict(level=blk['level'], program=blk['program'], diag_type=diag_type,
                                 category=CATEGORIES[cat_idx], grade=blk['grades'][grade_idx], sex=sex)
    return leaf_meta


def build_column_order(max_column, leaf_meta):
    total_cols_flat = {c for g in TOTAL_GROUPS for c in g['cols']}
    covered = set(INFO_COLS) | set(leaf_meta) | total_cols_flat | SPACER_COLS
    missing = sorted(set(range(1, max_column + 1)) - covered)
    if missing or max_column != len(covered):
        raise ValueError(
            f"Column mapping doesn't match this file (max_col={max_column}, covered={len(covered)}, "
            f"missing={missing}). The larger file likely has a different template "
            "(extra/renamed sections) than the one this mapping was built from -- check before proceeding."
        )
    return [c for c in range(1, max_column + 1) if c not in SPACER_COLS]


def leaf_header(m):
    prog = '' if m['program'] == 'N/A' else f"{m['program']} | "
    dt = 'With Diagnosis' if m['diag_type'].startswith('With Diagnosis') else 'With Manifestations'
    return f"{m['level']} | {prog}{dt} | {m['category']} | {m['grade']} | {m['sex']}"


def total_group_headers(g):
    if g['kind'] in ('subtotal', 'level_total', 'overall_total'):
        return [f"{g['label']} - Male", f"{g['label']} - Female", f"{g['label']} - Total"]
    if g['kind'] == 'indicator':
        return [g['label']]
    if g['kind'] == 'shs_total':
        return [f"{g['label']} - Grade 11 - Male", f"{g['label']} - Grade 11 - Female",
                f"{g['label']} - Grade 12 - Male", f"{g['label']} - Grade 12 - Female",
                f"{g['label']} - Grand Total - Male", f"{g['label']} - Grand Total - Female",
                f"{g['label']} - Grand Total - Total"]
    raise ValueError(g)


# ============================================================================
# MAIN
# ============================================================================

def main():
    t_start = time.perf_counter()

    log(f"Opening {SRC_PATH} (read-only, values-only mode)...")
    wb = openpyxl.load_workbook(SRC_PATH, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    max_col, max_row = ws.max_column, ws.max_row
    log(f"Source shape: {max_row:,} rows x {max_col:,} columns")

    leaf_meta = build_leaf_meta()
    leaf_cols_sorted = sorted(leaf_meta)
    n_leaf = len(leaf_cols_sorted)
    new_order = build_column_order(max_col, leaf_meta)
    old_to_new = {old: i + 1 for i, old in enumerate(new_order)}
    col_to_group = {c: g for g in TOTAL_GROUPS for c in g['cols']}
    log(f"Column mapping OK: {n_leaf:,} leaf columns, "
        f"{len(new_order):,} columns in final output (after dropping {max_col - len(new_order)} spacers)")

    meta_rows = [leaf_meta[c] for c in leaf_cols_sorted]
    level_arr = np.array([m['level'] for m in meta_rows])
    program_arr = np.array([m['program'] for m in meta_rows])
    sex_arr = np.array([m['sex'] for m in meta_rows])
    grade_arr = np.array([m['grade'] for m in meta_rows])
    diag_arr = np.array([m['diag_type'] for m in meta_rows])
    category_arr = np.array([m['category'] for m in meta_rows])

    leaf_idx0 = tuple(c - 1 for c in leaf_cols_sorted)
    get_leaf = itemgetter(*leaf_idx0)
    filter_idx0 = scol(FILTER_COL_LETTER) - 1
    ark_idx0 = scol('ARK') - 1

    # ------------------------------------------------------------------
    # 1. SINGLE STREAMING PASS: find header row, split schools zero/nonzero
    # ------------------------------------------------------------------
    log("Streaming source rows (single pass)...")
    t0 = time.perf_counter()

    info_headers = None
    header_row_idx = None
    sector_idx0 = None
    info_rows_nz, leaf_rows_nz, orig_idx_nz, ark_nz = [], [], [], []
    info_rows_z, orig_idx_z = [], []
    zero_flag_but_nonzero_total = 0
    n_seen = 0
    n_excluded_sector = 0

    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if header_row_idx is None:
            if row[0] == 'Region':
                header_row_idx = i
                info_headers = list(row[:15])
                sector_idx0 = info_headers.index("Sector")
                log(f"  found header row at row {i:,}")
            continue
        if row[0] is None:
            continue
        if row[sector_idx0] in EXCLUDED_SECTORS:
            n_excluded_sector += 1
            continue

        n_seen += 1
        flag = row[filter_idx0] or 0
        if flag:
            info_rows_nz.append(row[:15])
            leaf_rows_nz.append(get_leaf(row))
            orig_idx_nz.append(i)
            ark_nz.append(row[ark_idx0] or 0)
        else:
            info_rows_z.append(row[:15])
            orig_idx_z.append(i)
            if (row[ark_idx0] or 0) != 0:
                zero_flag_but_nonzero_total += 1

        if n_seen % PROGRESS_EVERY == 0:
            elapsed = time.perf_counter() - t0
            rate = n_seen / elapsed
            log(f"  ...{n_seen:,} school rows read ({elapsed:,.1f}s, {rate:,.0f} rows/s) "
                f"-- {len(info_rows_nz):,} with SNED enrollment, {len(info_rows_z):,} zero")

    wb.close()
    n_nz, n_z = len(info_rows_nz), len(info_rows_z)
    log(f"Streaming done in {time.perf_counter() - t0:,.1f}s: "
        f"{n_nz:,} schools with SNED enrollment, {n_z:,} with zero ({n_nz + n_z:,} total), "
        f"{n_excluded_sector:,} excluded for Sector in {sorted(EXCLUDED_SECTORS)}")
    if zero_flag_but_nonzero_total:
        log(f"  WARNING: {zero_flag_but_nonzero_total:,} rows had a zero '{FILTER_COL_LETTER}' flag "
            f"but a nonzero ARK total -- check the filter column choice for this file.")

    # ------------------------------------------------------------------
    # 2. Build leaf-value matrix for schools with enrollment
    # ------------------------------------------------------------------
    log("Building leaf-value matrix for schools with enrollment...")
    t0 = time.perf_counter()
    leaf_matrix = pd.DataFrame(leaf_rows_nz).fillna(0).to_numpy(dtype='int32')
    del leaf_rows_nz
    log(f"  leaf_matrix shape {leaf_matrix.shape} built in {time.perf_counter() - t0:,.1f}s")

    # ------------------------------------------------------------------
    # 3. Vectorized totals/subtotals/indicators (nonzero schools only)
    # ------------------------------------------------------------------
    log("Computing subtotal / total / indicator columns (vectorized)...")
    t0 = time.perf_counter()
    computed_nz = {}

    for g in TOTAL_GROUPS:
        if g['kind'] == 'subtotal':
            m_mask = (level_arr == g['level']) & (program_arr == g['program']) & (sex_arr == 'Male')
            f_mask = (level_arr == g['level']) & (program_arr == g['program']) & (sex_arr == 'Female')
            m_col, f_col, t_col = g['cols']
            computed_nz[m_col] = leaf_matrix[:, m_mask].sum(axis=1)
            computed_nz[f_col] = leaf_matrix[:, f_mask].sum(axis=1)
            computed_nz[t_col] = computed_nz[m_col] + computed_nz[f_col]
        elif g['kind'] == 'shs_total':
            c_g11m, c_g11f, c_g12m, c_g12f, c_gtm, c_gtf, c_gtt = g['cols']
            base = (level_arr == 'Senior High School')
            computed_nz[c_g11m] = leaf_matrix[:, base & (sex_arr == 'Male') & (grade_arr == 'Grade 11')].sum(axis=1)
            computed_nz[c_g11f] = leaf_matrix[:, base & (sex_arr == 'Female') & (grade_arr == 'Grade 11')].sum(axis=1)
            computed_nz[c_g12m] = leaf_matrix[:, base & (sex_arr == 'Male') & (grade_arr == 'Grade 12')].sum(axis=1)
            computed_nz[c_g12f] = leaf_matrix[:, base & (sex_arr == 'Female') & (grade_arr == 'Grade 12')].sum(axis=1)
            computed_nz[c_gtm] = computed_nz[c_g11m] + computed_nz[c_g12m]
            computed_nz[c_gtf] = computed_nz[c_g11f] + computed_nz[c_g12f]
            computed_nz[c_gtt] = computed_nz[c_gtm] + computed_nz[c_gtf]

    for g in TOTAL_GROUPS:
        if g['kind'] in ('level_total', 'overall_total'):
            m_col, f_col, t_col = g['cols']
            computed_nz[m_col] = sum(computed_nz[rm] for rm, rf in g['refs'])
            computed_nz[f_col] = sum(computed_nz[rf] for rm, rf in g['refs'])
            computed_nz[t_col] = computed_nz[m_col] + computed_nz[f_col]

    for g in TOTAL_GROUPS:
        if g['kind'] == 'indicator':
            (ind_col,) = g['cols']
            computed_nz[ind_col] = (computed_nz[g['ref']] > 0).astype('int8')

    log(f"  totals computed in {time.perf_counter() - t0:,.1f}s")

    overall_total_col = [g for g in TOTAL_GROUPS if g['kind'] == 'overall_total'][0]['cols'][2]
    recomputed_ark = computed_nz[overall_total_col]
    ark_arr = np.array(ark_nz, dtype='int64')
    n_mismatch = int((recomputed_ark != ark_arr).sum())
    if n_mismatch:
        log(f"  VALIDATION WARNING: {n_mismatch:,}/{n_nz:,} rows' recomputed overall total "
            f"doesn't match the source file's own ARK column -- inspect before trusting totals.")
    else:
        log(f"  Validation OK: recomputed overall total matches source ARK column for all {n_nz:,} rows.")

    # ------------------------------------------------------------------
    # 4. Wide_Summary -> CSV
    # ------------------------------------------------------------------
    log("Assembling wide table...")
    t0 = time.perf_counter()

    wide_cols_order = []
    for old_c in new_order:
        if old_c in INFO_COLS:
            continue
        if old_c in leaf_meta:
            wide_cols_order.append((old_c, leaf_header(leaf_meta[old_c])))
        else:
            g = col_to_group[old_c]
            idx = g['cols'].index(old_c)
            wide_cols_order.append((old_c, total_group_headers(g)[idx]))
    body_headers = [h for _, h in wide_cols_order]

    info_df_nz = pd.DataFrame(info_rows_nz, columns=info_headers)
    leaf_df_nz = pd.DataFrame(leaf_matrix, columns=[old_to_new[c] for c in leaf_cols_sorted])
    tot_df_nz = pd.DataFrame({old_to_new[c]: v for c, v in computed_nz.items()})
    body_nz = pd.concat([leaf_df_nz, tot_df_nz], axis=1)[[old_to_new[c] for c, _ in wide_cols_order]]
    body_nz.columns = body_headers
    wide_nz = pd.concat([info_df_nz.reset_index(drop=True), body_nz.reset_index(drop=True)], axis=1)
    wide_nz['_orig_row'] = orig_idx_nz

    info_df_z = pd.DataFrame(info_rows_z, columns=info_headers)
    zero_body = pd.DataFrame(0, index=np.arange(n_z), columns=body_headers, dtype='int32')
    wide_z = pd.concat([info_df_z.reset_index(drop=True), zero_body], axis=1)
    wide_z['_orig_row'] = orig_idx_z

    wide_df = pd.concat([wide_nz, wide_z], ignore_index=True)
    wide_df = wide_df.sort_values('_orig_row').drop(columns='_orig_row').reset_index(drop=True)
    log(f"  wide table assembled: {wide_df.shape} in {time.perf_counter() - t0:,.1f}s")

    log(f"Saving wide table to {OUT_WIDE_CSV} ...")
    t0 = time.perf_counter()
    wide_df.to_csv(OUT_WIDE_CSV, index=False)
    log(f"  saved in {time.perf_counter() - t0:,.1f}s")

    del wide_df, wide_nz, wide_z, body_nz, leaf_df_nz, tot_df_nz, info_df_nz, info_df_z, zero_body, computed_nz
    gc.collect()

    # ------------------------------------------------------------------
    # 5. Tidy_Long -> Parquet, written in CHUNKS (fixes the OOM)
    # ------------------------------------------------------------------
    log("Assembling long (tidy) table in chunks...")
    batch_size_schools = max(1, LONG_TABLE_TARGET_CHUNK_ROWS // n_leaf)
    log(f"  chunk size: {batch_size_schools:,} schools/chunk (~{batch_size_schools * n_leaf:,} rows/chunk)")

    # Lightweight per-school records: (orig_row, info_tuple, leaf_row_view_or_None).
    # Building this list is cheap (~60k small objects) -- no large arrays yet.
    records = []
    for i in range(n_nz):
        records.append((orig_idx_nz[i], info_rows_nz[i], leaf_matrix[i]))
    for j in range(n_z):
        records.append((orig_idx_z[j], info_rows_z[j], None))
    del info_rows_nz, info_rows_z, orig_idx_nz, orig_idx_z
    gc.collect()

    if SORT_LONG_TABLE_BY_ORIGINAL_ORDER:
        log("  sorting school records into original file order before chunking...")
        records.sort(key=lambda r: r[0])
    else:
        log("  keeping schools grouped as [with SNED enrollment] then [zero enrollment] "
            "(set SORT_LONG_TABLE_BY_ORIGINAL_ORDER=True for exact source row order)")

    n_total_schools = len(records)
    zero_leaf_row = np.zeros(n_leaf, dtype='int32')

    # Fixed-vocabulary metadata columns are safe to store as pandas Categorical
    # with a PRE-DECLARED category list -- same categories every chunk, so the
    # Arrow/Parquet schema stays identical across chunks (unlike school-name-
    # style columns, whose distinct values differ chunk to chunk).
    level_dtype = pd.CategoricalDtype(categories=sorted(set(level_arr)))
    program_dtype = pd.CategoricalDtype(categories=sorted(set(program_arr)))
    diag_dtype = pd.CategoricalDtype(categories=sorted(set(diag_arr)))
    category_dtype = pd.CategoricalDtype(categories=CATEGORIES)
    grade_dtype = pd.CategoricalDtype(categories=sorted(set(grade_arr), key=grade_arr.tolist().index))
    sex_dtype = pd.CategoricalDtype(categories=['Male', 'Female'])

    n_chunks = (n_total_schools + batch_size_schools - 1) // batch_size_schools
    writer = None
    t0 = time.perf_counter()
    rows_written = 0

    for chunk_i, start in enumerate(range(0, n_total_schools, batch_size_schools), start=1):
        chunk = records[start:start + batch_size_schools]
        n_chunk = len(chunk)

        info_arr = np.array([r[1] for r in chunk], dtype=object)
        leaf_arr = np.vstack([r[2] if r[2] is not None else zero_leaf_row for r in chunk])

        block = pd.DataFrame(np.repeat(info_arr, n_leaf, axis=0), columns=info_headers)
        block['School_Level'] = pd.Categorical(np.tile(level_arr, n_chunk), dtype=level_dtype)
        block['Program'] = pd.Categorical(np.tile(program_arr, n_chunk), dtype=program_dtype)
        block['Diagnosis_Type'] = pd.Categorical(np.tile(diag_arr, n_chunk), dtype=diag_dtype)
        block['Category'] = pd.Categorical(np.tile(category_arr, n_chunk), dtype=category_dtype)
        block['Grade_Level'] = pd.Categorical(np.tile(grade_arr, n_chunk), dtype=grade_dtype)
        block['Sex'] = pd.Categorical(np.tile(sex_arr, n_chunk), dtype=sex_dtype)
        block['Learner_Count'] = leaf_arr.astype('int32').flatten()

        table = pa.Table.from_pandas(block, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(OUT_LONG_PARQUET, table.schema, compression='snappy')
        writer.write_table(table)

        rows_written += len(block)
        elapsed = time.perf_counter() - t0
        rate = rows_written / elapsed if elapsed > 0 else 0
        eta = (n_total_schools - start - n_chunk) / (n_chunk / elapsed) if elapsed > 0 else 0
        log(f"  chunk {chunk_i}/{n_chunks}: {n_chunk:,} schools -> {len(block):,} rows "
            f"({rows_written:,} total, {rate:,.0f} rows/s, ~{eta:,.0f}s remaining)")

        del block, table, info_arr, leaf_arr
        if chunk_i % 5 == 0:
            gc.collect()

    writer.close()
    log(f"Long table complete: {rows_written:,} rows written to {OUT_LONG_PARQUET} "
        f"in {time.perf_counter() - t0:,.1f}s")

    log(f"ALL DONE in {time.perf_counter() - t_start:,.1f}s total")


if __name__ == '__main__':
    main()