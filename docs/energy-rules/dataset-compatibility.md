# Dataset compatibility preflight — LEAD and Smart Company Building

Reviewed: 2026-11-08. **Documentation/metadata review only**: no dataset archives downloaded, local data profiled, models loaded/trained or adapters implemented. Published properties below are not measurements of files in our environment. Any unverified item is an explicit execution gate, not an assumed pass.

## LEAD

| Item | Evidence / assessment |
|---|---|
| Labels | LEAD paper describes manual point/sequence annotations, not repair-confirmed faults. Author README offers a competition subset with200 labelled training buildings;206 test buildings have withheld labels. The repository lists `lead1.0-small.zip`; do not assume the complete paper dataset is available in that ZIP [L1–L3] |
| Rights | Official Kaggle data card says **Subject to Competition Rules**. Applicable rules text and annotation/underlying-data redistribution terms must be recorded before acquisition. No top-level dataset license was verified in the author README. Do not infer MIT/CC0 from public GitHub access or apply an article license to the data [L2,L3] |
| Cadence / units | Hourly `meter_reading` is consumption in **kWh**; treat as interval consumption, not a cumulative counter. Binary `anomaly` labels exist in public train. Confirm exact label convention (interval start/end) and timezone from acquired documentation; do not invent them [L3] |
| Missingness | Missing points are acknowledged by the paper; actual per-source gaps/duplicates and label coverage require a later file audit. Do not convert missing readings into normal zeros [L1] |
| Preprocessing | Original benchmark applies log/z-score and daily windows. This is a different evaluation unit; do not claim comparability with our event metrics. Reject supplied winner-engineered features by default until their causality is audited [L1,L3] |
| Current compatibility | **Not directly compatible**: standalone rules require600s, not3600s. No sixfold upsampling, forward-fill or interpolation to manufacture10-minute readings. An explicitly approved native-hourly rule/feature version and newly prepared models are required. No reuse of UCI source-bound weights |

Status: promising **behaviour-anomaly** benchmark, gated by specific artifact/rights, timezone/interval-label audit and native-hourly preparation. Public competition test without labels cannot provide locally computed recall/F1. Split the labelled training subset as prescribed in the protocol instead.

## Smart Company Building

| Item | Evidence / assessment |
|---|---|
| Artifacts / rights | Dryad DOI has versioned measurement, issues and reduced bundles. Dryad publishes data under **CC0**; preserve DOI/version/license evidence with any future download. The journal article's CC BY-NC-ND license is a separate work, not the dataset license [C1,C3,C4] |
| Labels | `issues.zip` separates manual and automatic issue YAMLs. Automatic gaps/zero/leap labels must not be an independent gold standard for similar rules. Manual labels require meter/channel/time mapping and inspection of completeness; absence of a manual issue is not proof of normal operation [C1,C2] |
| Cadence | Raw acquisition includes change-of-value logging; exported corrected series include1min/15min/1h. Lack of a change-of-value record alone does not mean sensor silence/failure. Native600s is not provided by this description [C1,C2] |
| Units / accumulation | Electrical `P` is power in W; electrical energy variable **named `W`** is cumulative kWh. Do not confuse its variable name with watts or sum cumulative values. Net/import/export channels differ [C1,C2] |
| Time | CSV `datetime_utc` has explicit UTC information; facility context is Europe/Berlin. Use the documented source clock, handling DST explicitly; it is different from UCI dataset-naive labels [C1] |
| Gaps / processing | Corrected files contain interpolation/fill and temporal corrections. Those operations can use future samples, remove faults, or create repeated values. Keep native/raw issue-detection and corrected-data analyses separate; a filled plateau is not evidence of a stuck meter [C1,C2] |
| Current compatibility | **Conditional, not ready**. A future adapter may derive600s consumption by differencing valid cumulative endpoints (`1000×ΔkWh`), with reset/replacement/sign/gap handling. No interpolation across missing endpoints. Genuine interval-energy channels can be summed only when coverage and semantics are verified; power integration requires a documented sampling assumption. Corrected1min sampling must not be described as untouched minute telemetry |

Status: promising **telemetry-quality/context** dataset; not automatically a fully labelled consumption-fault benchmark. Prefer manual issues for primary positive references, publish automatic-label results separately as agreement. It is one facility with related/submetered channels: splitting meters is not an unseen-building test. Forecast models and anomaly calibration must be newly prepared in a separate approved stage.

## Required file audit before an experiment

Record exact URLs/DOI versions, SHA256, license text, meter/channel hierarchy, units, accumulation/sign convention, timestamp reference/zone, native cadence and transformation lineage. Produce per-source temporal coverage/missing/duplicate/reset statistics separately for each split and label-origin counts. Audit splits using training metadata; never select only easy test intervals. No fabricated gap filling, label invention, automatic model transfer or use of published future-aware corrections as proof of online causality.

Unknowns above stay unknown until that audit; this document authorizes neither acquisition of restricted data nor experiment execution.

## Primary sources (accessed 2026-11-08)

- L1: [LEAD authors' paper](https://www.samy101.com/assets/pdf/2022-eenergy-lead.pdf).
- L2: [Author repository and availability notice](https://github.com/samy101/lead-dataset), [data directory](https://github.com/samy101/lead-dataset/tree/main/data).
- L3: [Official LEAD data card](https://www.kaggle.com/competitions/energy-anomaly-detection/data), [competition rules](https://www.kaggle.com/competitions/energy-anomaly-detection/rules). Data-card search rendering was readable; rules text was not readable in this review.
- C1: [Dryad dataset/README](https://datadryad.org/dataset/doi:10.5061/dryad.73n5tb363).
- C2: [Company dataset paper: acquisition, processing, data records](https://www.nature.com/articles/s41597-025-05186-3).
- C3: [Dryad publication policy, CC0 data](https://datadryad.org/publication_policy).
- C4: [Dryad reuse guidance](https://dev.datadryad.org/help/guides/reuse).

Direct metadata API access was unavailable during this review; no DOI-specific rights JSON was verified. The CC0 assessment rests on the repository's published policy; preserve dataset-specific evidence during acquisition. No missing numeric coverage rates or issue counts have been guessed.
