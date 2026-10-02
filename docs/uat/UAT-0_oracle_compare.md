# UAT-0 oracle vs code

Generated 2026-10-02 by `tools/compare_oracle.py`. Tally: MATCH 120, DIFF 6, OPEN 3, NOT IN ORACLE 0

| Stock | Metric | Oracle | Code | Result | Note |
|---|---|---|---|---|---|
| HDFCBANK | pe_discount_own_3y | 0.1784 | 0.18 | DIFF | rel gap 0.88% |
| HDFCBANK | ev_ebitda_discount_own | 0.01542 | 0.01588 | DIFF | rel gap 2.96% |
| INDIGO | pb_discount_own_5y | -0.238 | -0.2355 | DIFF | rel gap 1.08% |
| INDIGO | dividend_yield | N/A (FY26 dividend blank) | 0.002051 | DIFF | oracle N/A (FY26 dividend blank); code gives a number |
| INDIGO | roe_5y_avg | 1.508 | -9.578 | DIFF | rel gap 735.01% |
| INDIGO | pb_justified_gap | -0.5543 | -3.836 | DIFF | rel gap 592.02% |
