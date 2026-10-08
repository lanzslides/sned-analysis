# SNED / ILRC Centers Analysis (Philippines)

This analysis started from the research questions posed by **EDCOM II** on Special Needs Education (SNED) and Inclusive Learning Resource Centers (ILRCs) in the Philippines. It uses EDCOM-provided data on SPED Centers, ILRCs, SNED-implementing schools, SNED teaching items, and learner records, combined with DepEd datasets for enrollment, location, and municipal context.

**General research question:**

> What is the geographic distribution of learners with diagnosed disabilities and learners with recorded manifestations relative to the location of existing SPED Centers and Inclusive Learning Resource Centers (ILRCs), disaggregated by municipal income class?

**Specific research questions:**

1. What is the geographic distribution, disability profile, and enrollment share of learners with diagnosed disabilities and learners with recorded manifestations, and which municipalities have the highest absolute numbers and proportions relative to total enrollment, by diagnosis and manifestation type?
2. How do learner counts, disability profiles, and geographic distribution differ when analyzed using diagnosed disability records compared with manifestation records?
3. What is the ratio of learners with diagnosed disabilities and recorded manifestations to each existing SPED Center or ILRC, by municipality and disability type? How about relative to SPED plantilla positions for teachers?
4. Which municipalities and school clusters have the largest numbers and proportions of learners with disabilities enrolled in schools without a SPED Center or ILRC within a 3-kilometer radius? For each existing center or ILRC, what are the numbers and disability profiles of learners in the host school and in surrounding schools within the same radius?
5. How do learner numbers, disability profiles, access to a SPED Center or ILRC within a 3-kilometer radius, and enrollment in schools hosting these centers vary across municipalities of different income classes?
6. Which municipalities, school clusters, and existing SPED Centers meet combinations of the following characteristics:
   a. High learner counts or enrollment shares;
   b. High concentrations of specific disability or manifestation types;
   c. No SPED Center or ILRC within a 3-kilometer radius;
   d. High enrollment in schools hosting existing centers; and
   e. Lower municipal income class.

## Key Findings

**Q1 — Profiling Learners with Disabilities**

- There are 523,939 LWDs nationally (94.08% in public schools), but this still captures only ~10.39% of the PhilHealth-estimated population of children with disabilities.
- Public and private sectors show reversed diagnosis/manifestation patterns driven almost entirely by manifestation volume (diagnosis prevalence is similar at ~0.82% public vs. 0.65% private), suggesting formal diagnostic capacity is lagging behind need rather than true prevalence differing by sector.
- The top 15 provinces hold about half the national LWD count, with diagnosis-heavy clusters in Greater Manila and manifestation-heavy, low-diagnosis clusters in Mindanao (e.g., Davao Oriental at <10% diagnosed despite high LWD volume).

**Q2 — Formal Diagnosis vs. Observed Manifestations of LWDs**

- Diagnosis-heavy regions cluster in urban Luzon (NCR, Central Luzon, CALABARZON) while manifestation-heavy clusters emerge in Mindanao (Davao, Zamboanga Peninsula) and Northern Luzon (CAR-Cagayan Valley), hinting at a terrain/specialist-access barrier.
- Diagnosis rates drop sharply from Kindergarten to Grade 1 nationwide, with NCR persistently highest at every level and BARMM/Zamboanga Peninsula failing to recover after JHS exit.
- Cognitive/Learning disabilities form the largest functional domain but have the lowest diagnosis rate, while Socio-behavioral conditions (driven by ASD) are diagnosed over 4x more often, against a 38% national diagnosis average.

**Q3 — SNED Facility and Staffing (incl. Staffing Ratios)**

- The 495 existing SNED facilities (ILRCs + SPED centers) serve only 10.3% of the national LWD population and reach just 1 in 4 municipalities, leaving 1,251 municipalities with no dedicated facility.
- 10.84% of authorized SPED teaching positions remain vacant, with JHS vacancy (24.16%) nearly triple ES (8.75%), pushing the realistic student-to-teacher ratio to 87.3 even if positions were theoretically full.
- Nearly half (46.3%) of the 1,906 schools with Non-Graded enrollment have zero teacher inventory, and both learner-per-facility and student-per-filled-teacher ratios vary by orders of magnitude across municipalities (67.5–4,158 L/F; 4.83–3,706 students per filled position).

**Q4 — SNED Facility Access @ 3-km Road Distance**

- 97.1% of routable schools (47,658 of 54,119) and 42.91% of SNED learners (216,904) lack access to any ILRC/SPED center within 3 km, with 543 municipalities (“SNED deserts”) having zero facility at all.
- Facility-rich areas are almost uniformly urban, high-income HUCs (Davao City, Quezon City, Zamboanga City), while access is most lacking in BARMM, Eastern Visayas, and Ilocos Region.
- Access to a SNED facility is statistically linked to diagnosis rates — schools without access show roughly 1 diagnosed learner per 3 with manifestations, versus a near 1:1 ratio in schools with access (Cramer’s V = 0.2653, p < 0.05).

**Q5 — Variation by municipal income class**

- First-class municipalities hold 75.09% of all SNED learners (393,438) despite making up less than half (47.9%) of all municipalities, concentrating both the SNED population and facility access in wealthier areas.
- Location quotients show ASD diagnosis falling monotonically as income class declines while Orthopedic/Physical Handicap and Speech/Language Disorder rise, suggesting conditions requiring clinical screening are systematically underdiagnosed in poorer areas.
- The share of schools lacking 3-km SNED access rises from 64.9% in 1st-class to 86.5% in 5th-class municipalities, yet distance for already-connected schools barely changes — meaning the inequality is about whether access exists at all, not how far away it is.

**Q6 — Priority municipalities, clusters, and centers**

- A composite disadvantage index (learner volume, disability concentration, access rate, income class, host-enrollment share) puts the national average municipality at a score of 1.86, with Boljoon (Cebu), Camaligan (Camarines Sur), and Tigbao (Zamboanga del Sur) scoring the maximum of 5.
- High-prevalence regions (Zamboanga Peninsula, Davao Region, CAR) tend to have the highest disadvantage scores (r = 0.84), though NCR is a notable outlier — 4th in disadvantage despite only 10th in prevalence, driven by structural strain rather than raw learner volume.
- Counterintuitively, “SNED deserts” carry a lower mean disadvantage score (1.77) than municipalities with access (2.14) despite being poorer, suggesting the index captures strain on existing facilities more than absence itself — with DBSCAN clustering flagging Davao Oriental as the top priority area (9 municipalities in unserved clusters).

## Data Sources

Data is not stored in this repository (for privacy purposes) — see [data/README.md](data/README.md) for how to obtain it and where it goes. All RAW inputs:

| File                                                                                                         | Format  | What it is                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------ | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| [1] Status of Inclusive Learning Resource Centers (ILRCs).xlsx                                               | xlsx    | EDCOM list of ILRCs: converted SPED Centers (2022–23) and ILRCs funded in FY 2024, with location and infrastructure status |
| [2] Inventory of Number and List of SPED Centers and SPED Implementing Schools_SY2023-2024_EBEIS_100324.xlsx | xlsx    | EBEIS lists of SPED Centers and SNED-implementing schools, SY 2023–24                                                      |
| [3.2] Number of Receiving Teachers Handling SPED Classes_051325.xlsx                                         | xlsx    | Elementary teachers handling SPED classes without SPED plantilla, by region and SDO                                        |
| [3.3] Status of Filling Up_SNED Teaching Items.xlsx                                                          | xlsx    | Status of authorized SNED teaching positions by region and SDO                                                             |
| SY 2025-2026 SNED Database (All Sector by School)\_FR - (with school id).xlsx                                | xlsx    | School-level SNED learners (mainstreamed, self-contained, non-graded), ES/JHS, SY 2025–26                                  |
| SY 2022-2023 List of Schools with Coordinates.xlsx                                                           | xlsx    | School list with geographic coordinates, SY 2022–23                                                                        |
| SY 2025-2026 SCHOOL LEVEL DATA ON ENROLLMENT BY SCHOOL.xlsx                                                  | xlsx    | Latest school-level enrollment, SY 2025–26 (primary enrollment source)                                                     |
| private_school_coordinates.parquet                                                                           | parquet | Coordinates of private schools                                                                                             |
| public_school_coordinates.parquet                                                                            | parquet | Coordinates of public schools                                                                                              |
| consolidated_geodata_matched.gpkg                                                                            | gpkg    | Barangay-level boundary polygons for mapping                                                                               |
