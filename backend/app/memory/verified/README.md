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

| Ref | Publisher |
|---|---|
| RBI/2020-21/63 (Co-Lending Model) | Reserve Bank of India |
| Master Direction DBR.AML.BC.No.81/... (KYC) | Reserve Bank of India |
| RBI/2022-23/111 (Digital Lending) | Reserve Bank of India |
| Aadhaar (Authentication) Regulations, 2016 | UIDAI |
