# Variables and event windows

The complete machine-checkable variable dictionary is available in [`docs/Appendix_Variable_Dictionary.csv`](Appendix_Variable_Dictionary.csv).

## Outcome variables

Each scenario outcome is the close-to-close sum of daily log returns, `log(adjClose_t / adjClose_t-1)`, for each firm.

The filter applies to the date attached to each daily return. Because a return dated on a given trading day measures the prior trading close to that day's close, the code includes return rows after the start boundary and through the end boundary: `start_date < date <= end_date`. Thus a February 19 to March 13 window measures the return from the February 19 close through the March 13 close.

| Variable | Interpretation | Close-to-close window |
|---|---|---|
| `S1_Decline` | Initial tariff-driven decline | 2025-02-19 to 2025-03-13 |
| `S2_Escalation_Collapse` | Escalation collapse | 2025-03-25 to 2025-04-08 |
| `S3_Policy_Shock_Jump` | Policy-shock jump | 2025-04-08 to 2025-04-09 |
| `S4_Uncertainty_Decline` | Uncertainty-driven decline | 2025-04-09 to 2025-04-21 |
| `S5_Long_Term_Adjustment` | Long-term adjustment | 2025-02-19 to 2025-12-31 |

Adjacent windows are separate analyses and should not be added together.

## Exposure

`X` consists of sector indicator variables plus an intercept. Utilities is the omitted baseline sector. The archived original contains an inaccurate comment about Basic Materials, although its positional selection also omitted Utilities; the working script now names the sector columns explicitly.

## Candidate mediators

Financial variables come from three FMP quarterly statements:

- `IS:` — income statement.
- `BS:` — balance sheet.
- `CF:` — cash-flow statement.

For each curated raw field, stage 1 can construct:

| Suffix | Construction |
|---|---|
| none | value at the selected anchor quarter |
| `_YoY` | change from the corresponding quarter one year earlier, divided by the absolute lagged value |
| `_QoQ` | change from the preceding quarter, divided by the absolute lagged value |
| `_CAGR3` | compound annual growth over 12 quarters; unavailable when either endpoint is non-positive |
| `_Avg5` | mean over up to 20 quarters beginning at the anchor |

`read.csv` converts names such as `IS:revenue_CAGR3` to `IS.revenue_CAGR3` in R. The analysis selects mediator names beginning with `IS.`, `BS.`, or `CF.`.

Before modeling, all-missing and zero-variance mediator columns are removed and reported. Remaining missing mediator values are set to zero after standardization, which is equivalent to imputing the observed-variable mean on the standardized scale.

## Data provenance still needed for publication

The paper and repository release should state the FMP product/plan, retrieval dates, endpoint names, historical constituent definition, symbol exclusions, missing-data treatment, sector taxonomy version, and any FMP revisions observed between the original and replication runs.
