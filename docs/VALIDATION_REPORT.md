# Computational validation report

Validation date: 2026-07-16

Environment: Python 3.12.11; R 4.5.1; `glmnet` 4.1-9

Data service: Financial Modeling Prep `stable` API routes

## Validation status

The working pipeline completed from FMP collection through all five generalized mediation analyses. On 2026-07-16, the event-return construction was updated to close-to-close windows and the event-return stage plus all five generalized mediation analyses were rerun from the existing validated local FMP downloads. Seven offline tests also passed, including syntax, required-column, event-window, frozen-universe, stable-endpoint, and API-key transport checks.

## Stage-level checks

| Artifact | Validation result |
|---|---|
| Frozen analysis universe | 503 unique symbols |
| Statement-metric table | 503 rows × 220 columns |
| Analysis table | 503 rows × 231 columns |
| Candidate financial mediators | 215 before variance screening |
| Usable financial mediators | 214 after screening |
| Mean mediator missingness | 8.48% before standardized-mean imputation |
| Sector encoding | exactly one of 11 sectors for every firm |
| Daily adjusted prices | 125,697 rows; 503 unique symbols |
| Price-date range | 2025-01-02 through 2025-12-31 |
| Duplicate firm-date price rows | 0 |
| Nonpositive adjusted prices | 0 |
| Event-return table | 503 rows × 6 columns |
| Missing or nonfinite event returns | 0 |
| Model dimensions | Y: 503 × 1; X: 503 × 11; M: 503 × 214 |
| Completed model runs | S1, S2, S3, S4, and S5 |

All income-statement, balance-sheet, and cash-flow anchor dates were present. They range from 2025-01-31 through 2025-04-30, consistent with firms' differing fiscal calendars.

The event-return stage uses close-to-close windows. Because each daily return is labeled by its ending date, a window from `start_date` to `end_date` includes return rows with `start_date < date <= end_date`.

| Scenario | Complete-window daily returns |
|---|---:|
| S1 | 16 |
| S2 | 10 |
| S3 | 1 |
| S4 | 7 |
| S5 | 218 |

## Mediator screening

`CF:capitalExpenditure_CAGR3` is missing for all firms and is removed before modeling. The CAGR function requires positive endpoints, whereas capital expenditure is commonly reported as a negative cash outflow. All-missing and zero-variance columns are now reported and excluded automatically.

The five analyses selected the following numbers of mediators:

| Scenario | Selected mediators | Direct/indirect rows |
|---|---:|---:|
| S1 | 15 | 11 |
| S2 | 13 | 11 |
| S3 | 13 | 11 |
| S4 | 9 | 11 |
| S5 | 19 | 11 |

All exported numeric estimates and standard errors are finite, and no result table contains duplicate variable names. Removing the all-missing mediator produced identical exported result tables in all five scenarios.

## Long-window coverage decision

Three firms have fewer than 250 price observations:

| Symbol | Available 2025 rows |
|---|---:|
| FI | 234 |
| IPG | 227 |
| K | 236 |

Their S1–S4 windows have the required dates, but their S5 cumulative returns stop at the last price available from FMP rather than 2025-12-31. Under the close-to-close S5 convention, FI, IPG, and K have 202, 195, and 204 S5 return observations, respectively, rather than the 218-return complete window. The manuscript should explicitly choose and justify one treatment: retain the available cumulative return, exclude these firms from S5, or reconstruct terminal returns using verified corporate-action data. The code does not silently impose that research decision.

## Rate-limit behavior

The original instruction of eight requests per second triggered FMP HTTP 429 responses. The public workflow now uses two requests per second with concurrency three, writes failed ticker names explicitly, and stops before downstream analysis if statement collection is incomplete. Successful responses are cached for safe reruns.

## Repository boundary

API credentials, FMP response caches, full derived datasets, local checking files, and generated result folders are excluded from Git. Whether to publish derived coefficient tables separately should be decided under the journal policy and the FMP data terms.
