# Sector Effects and Financial Mediators During the 2025 U.S. Tariff Episodes

## Overview

This repository contains the code and data used in a study of how S&P 500 sectors responded to five tariff-policy episodes in 2025. It looks at both sector-level return differences and whether firm financial characteristics may help explain those effects using a sparse generalized mediation approach.

The repository is organized in the order the empirical analysis is performed:

1. construct firm-level financial metrics from Financial Modeling Prep (FMP) statements;
2. add sector classifications;
3. obtain adjusted daily prices and calculate five event-window log returns;
4. estimate direct, indirect, and selected mediator effects for each event window.

## Event windows

| Scenario | Description | Dates |
|---|---|---|
| S1 | Initial tariff-driven decline | 2025-02-19 to 2025-03-13 |
| S2 | Escalation collapse | 2025-03-25 to 2025-04-08 |
| S3 | Policy-shock jump | 2025-04-08 to 2025-04-09 |
| S4 | Uncertainty-driven decline | 2025-04-09 to 2025-04-21 |
| S5 | Long-term adjustment | 2025-02-19 to 2025-12-31 |

Returns are calculated as sums of daily log returns for observations dated within each inclusive window. See [Variable definitions](docs/VARIABLES.md) for the boundary-date convention and mediator constructions.

## Repository contents

```text
analysis/          generalized mediation analysis and result-table export
archive/original/  unchanged historical source files and checksums
data/reference/    frozen 503-symbol analysis universe
docs/              study context, variables, and computational workflow
scripts/           pipeline and validation entry points
src/stage1/        financial-statement and firm-characteristic construction
src/stage2/        adjusted-price collection and event-return construction
tests/             offline validation tests
```

The working pipeline implements only the five tariff-window outcomes. Earlier exploratory code is retained separately under `archive/original/` for provenance and is not part of the working analysis.

## Computational environment

- Python 3.10 or later
- R 4.2 or later
- Python packages listed in `requirements.txt`
- R packages listed in `requirements-r.txt`
- FMP credentials with access to the cited endpoints

API credentials, downloaded data, caches, and generated result tables are excluded from version control. The complete command sequence and validation criteria are documented in the [Computational workflow](docs/COMPUTATIONAL_WORKFLOW.md).

The verified full-run dimensions, model checks, and the remaining long-window coverage decision are recorded in the [Computational validation report](docs/VALIDATION_REPORT.md).

## Design and provenance notes

- The 503-symbol universe is frozen from the analysis dataset used in the project, avoiding later changes caused by querying current index membership.
- Utilities is the omitted sector category in the working analysis.
- Financial-statement metrics use an anchor window of 2025-01-01 through 2025-04-30.
- Exact historical scripts from the project Drive are preserved separately from the working code and verified by `archive/original/SHA256SUMS`.
- The core generalized mediation method below the marked boundary in the R source has not been rewritten.

## Citation, authorship, and release

The article citation, author affiliations, funding statement, data-access statement, and software license will be added before the public journal release. Redistribution of FMP-derived data will be determined separately from publication of the analysis code.
