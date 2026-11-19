# Open-source candidate scope

- This directory is a source-distribution candidate, not a deployed service. Keep shop operations read-only. No GitHub publication without an explicit request.
- Do not add real reports, credentials, cookies, private identifiers, infrastructure mappings, database dumps or local runtime configuration to the distribution. Use synthetic fixtures only.
- Local PostgreSQL only. Installation, resource names and schema changes require an explicit target and authorization. Never use a production or remote database for tests.
- Preserve report grain, stable IDs, currency, timezone, dates and attribution maturity. Missing is not zero. Candidate actions are not executed actions.
- Run `python3 -m unittest discover -s tests -q`; enable `AEE_TEST_DB_CONFIG` only for an explicitly authorized isolated local test database. XLSX tests need the optional openpyxl dependency.
- Public artifacts must use the allowlist exporter and pass the privacy scan. No commit/push is implied by work on this candidate.
