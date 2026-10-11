# Human tasks

These decisions are open. This checkout does not implement them.

- SEC EDGAR needs a real User-Agent contact string before any fetch.
- FRED stays blocked unless a key is supplied outside the repo and the 2024 terms are accepted.
- A stored public rate is not copied into the ledger unless a later explicit accept step is authorized.
- Market-data vendors and issuer announcement feeds stay unconnected until access is verified.
- Statistics Norway table 03013 is discontinued through 2025M12. Do not call it. Table 14700 replaces it. Table 14700 cell 2026M07 total is now the one connected extract, and other SSB tables remain unconnected.
- The desk process that is already listening was not restarted. Seeing /portfolio and /portfolio/valuation requires a later explicit restart approval.
- Connecting a bank or broker is not part of onboarding.
