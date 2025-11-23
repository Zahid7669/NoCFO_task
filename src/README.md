# Matching Logic (src)

This directory contains the core matching functionality for the homework assignment.

## Key File
- `match.py` implements two public functions:
  - `find_attachment(transaction, attachments)`
  - `find_transaction(attachment, transactions)`

Both functions return a single best match or `None` when no confident match exists.

## How To Run
From the project root:
```bash
python run.py
```
This script loads fixture JSON data from `src/data/` and prints a comparison of expected vs found matches.

## How To Test
Install pytest if needed:
```bash
pip install pytest
```
Run tests:
```bash
pytest -q
```

## Heuristic Summary
1. Normalize and compare references first (spaces removed, leading zeros trimmed for numeric-only). Exact match => immediate result.
2. Filter candidates by amount (handles negative transaction amounts vs positive invoice totals).
3. Score remaining candidates with name similarity (token Jaccard ignoring common suffixes) and date proximity (0..30 day linear decay bonus).
4. Acceptance rules:
   - If a contact/name exists: require name similarity ≥ 0.5.
   - If no contact: require exact date match and uniqueness.
5. Deterministic selection: by score, then date distance, then id.

## Data Fields Considered
- Transaction: `id`, `date`, `amount`, `contact`, `reference`
- Attachment (data block): `total_amount`, `reference`, counterparty fields (`supplier`, `issuer`, `recipient`), dates (`due_date`, `invoicing_date`, `receiving_date`)

## Determinism
No randomness is used; sorting criteria ensure repeatable results for the same input data.

## Extending
If new data fields appear (e.g., currency, VAT), add them as additional filters or modifiers to the composite score while keeping acceptance thresholds clear.
