# Verified memory corpus

Genuine, **source-cited** policy entries the Knowledge agent grounds on. Each file
is a concise **cited summary** of a real circular/regulation — with the actual
reference number and URL for verification — not verbatim official text. Consult
the cited source for authoritative wording.

## Integrity (the "verified" part)

`manifest.json` records the SHA-256 of every `.md`. `VerifiedMemoryStore` re-hashes
each file on load; only files whose hash matches the manifest are searchable. A
tampered or unlisted file is quarantined and reported by `verify_integrity()` —
so an answer can only be grounded in content provably unchanged since it was
vouched for.

## Adding / editing an entry

1. Add or edit a `.md` with frontmatter: `policy_name`, `section`, `ref`,
   `publisher`, `url`, `date`, `kind: cited-summary`.
2. Regenerate the manifest:
   ```bash
   cd backend && python -m app.memory.verified_store --rebuild-manifest
   ```
3. Commit the file **and** the updated `manifest.json` together.

## Sources

| Ref | Publisher | Topic |
|---|---|---|
| RBI/2020-21/63 | Reserve Bank of India | Co-Lending Model (20% retention) |
| Master Direction DBR.AML.BC.No.81/... | Reserve Bank of India | KYC periodic updation |
| RBI/2022-23/111 | Reserve Bank of India | Digital Lending Guidelines |
| Aadhaar (Authentication) Regulations, 2016 | UIDAI | Aadhaar number / auth |
| FIDD.CO.Plan.BC.5/04.09.01/2020-21 | Reserve Bank of India | Priority Sector Lending |
| DBS.CO.CFMC.BC.No.1/23.04.001/2016-17 | Reserve Bank of India | Frauds — EWS / RFA / reporting |
| RBI/2023-24/41 | Reserve Bank of India | Default Loss Guarantee (DLG/FLDG) |
| DNBR.PD.008/03.10.119/2016-17 | Reserve Bank of India | Fair Practices Code (NBFC) |
| PMLA, 2002 & PML Rules | FIU-IND | AML — STR / CTR reporting |
