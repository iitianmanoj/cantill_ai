# Decisions and assumptions

- Clubbing: deterministic ascending creation timestamp / PR number / line number; join the earliest qualifying group, comparing against its first line.
- New item: do not club, estimate from requester's unit price, no suggested suppliers.
- Unmatched descriptions: use normalized exact match, then SequenceMatcher similarity threshold 0.74. Ambiguous near matches should be manually reviewed; heuristic matching can misclassify items.
- Valuation: first usable rate contract, otherwise lowest eligible out-of-ceiling rate, otherwise latest item PO in 365 days, otherwise standard price. New items use estimated price.
- Contracts: use the register's consumed value as the starting ceiling, consume across requirements in a batch. This is not yet persisted across separately uploaded batches.
- Supplier ranking: PO frequency (3 points per PO, capped at 15), recency (up to 20), prior contract (+10), on-time percent (0.2 per point), quality rating (4 per point). Reference price is most recent supplier PO in 548 days, otherwise latest contract rate. Ties broken by supplier ID. Blocked and inactive suppliers excluded.
- Fallback suggestions: add Active category-matching suppliers ordered by delivery percentage, quality, then ID.
- Direct PO consolidation: same supplier, plant and route within 24h of first requirement.
- Incomplete lines: NOT_PROCESSED with reason, to avoid silently fabricating data.
- The policy is stored as JSON data with ordered conditions. Additional rules can use plant, category, item_type, value thresholds, emergency, capex, contract availability and recent PO flags without code changes. New predicate types require engine development.
- Important remaining gaps: policy effective-date selection, PDF contract extraction, PDF policy amendment ingestion, contract lines for newly added contracts, and persistent ceiling across batches.
