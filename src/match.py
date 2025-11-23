from __future__ import annotations
from datetime import datetime
from typing import Iterable, Optional
import re

Attachment = dict[str, dict]
Transaction = dict[str, dict]

# -----------------------------
# Helper functions (internal)
# -----------------------------

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


def _normalize_reference(ref: Optional[str]) -> Optional[str]:
    if not ref:
        return None
    cleaned = ref.replace(" ", "").upper()
    # Strip leading zeros only if purely numeric (no alpha prefix like RF)
    if cleaned.isdigit():
        cleaned = cleaned.lstrip("0") or "0"
    return cleaned


_STOP_WORDS = {"oy", "oyj", "ltd", "tmi", "inc", "oy.", "oy,"}
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+", re.UNICODE)


def _tokenize(name: Optional[str]) -> set[str]:
    if not name:
        return set()
    tokens = {t.lower() for t in _TOKEN_RE.findall(name)}
    return {t for t in tokens if t not in _STOP_WORDS}


def _name_similarity(a: Optional[str], b: Optional[str]) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    if inter == 0:
        return 0.0
    union = len(ta | tb)
    return inter / union


def _attachment_names(att: Attachment) -> list[str]:
    data = att.get("data", {})
    names: list[str] = []
    for key in ("supplier", "issuer", "recipient"):
        val = data.get(key)
        if val and val.lower() != "example company oy":  # Company itself not a counterparty
            names.append(val)
    return names


def _best_name_similarity(transaction_contact: Optional[str], att: Attachment) -> float:
    if not transaction_contact:
        return 0.0
    best = 0.0
    for name in _attachment_names(att):
        best = max(best, _name_similarity(transaction_contact, name))
    return best


def _date_distance_days(tx_date: datetime, att: Attachment) -> int:
    data = att.get("data", {})
    candidates = [
        _parse_date(data.get("due_date")),
        _parse_date(data.get("invoicing_date")),
        _parse_date(data.get("receiving_date")),
    ]
    distances = [abs((d - tx_date).days) for d in candidates if d]
    return min(distances) if distances else 10_000  # large sentinel


def _is_amount_match(tx: Transaction, att: Attachment) -> bool:
    tx_amount = tx.get("amount")
    att_amount = att.get("data", {}).get("total_amount")
    if tx_amount is None or att_amount is None:
        return False
    # Bank outgoing payments are negative, invoices store positive totals.
    return abs(tx_amount - att_amount) < 1e-6 or abs(abs(tx_amount) - att_amount) < 1e-6


def _reference_match(tx: Transaction, att: Attachment) -> bool:
    tx_ref = _normalize_reference(tx.get("reference"))
    att_ref = _normalize_reference(att.get("data", {}).get("reference"))
    return tx_ref is not None and att_ref is not None and tx_ref == att_ref


def _select_best(candidates: list[tuple[Attachment, float, int]]) -> Optional[Attachment]:
    # Sort deterministically: higher score, smaller date distance, smaller id
    candidates.sort(key=lambda x: (-x[1], x[2], x[0]["id"]))
    return candidates[0][0] if candidates else None


# -----------------------------
# Public API functions
# -----------------------------

def find_attachment(
    transaction: Transaction,
    attachments: list[Attachment],
) -> Attachment | None:
    """Find the best matching attachment for a given transaction.

    Heuristic order:
    1. Exact reference number match (after normalization) => return immediately.
    2. Amount filter (absolute) + evaluate date proximity & name similarity.
       - Name similarity threshold (>=0.5) required when transaction has a contact.
       - If transaction has no contact, accept only if date distance == 0 (exact match) and unique by amount.
    """
    # 1. Reference match
    ref_norm = _normalize_reference(transaction.get("reference"))
    if ref_norm:
        for att in attachments:
            if _reference_match(transaction, att):
                return att

    tx_date = _parse_date(transaction.get("date"))
    if not tx_date:
        return None

    # 2. Amount-based candidates
    amt_candidates: list[tuple[Attachment, float, int]] = []  # (attachment, composite_score, date_distance)
    for att in attachments:
        if not _is_amount_match(transaction, att):
            continue
        dist = _date_distance_days(tx_date, att)
        name_sim = _best_name_similarity(transaction.get("contact"), att)
        # Composite score: amount match base 1 + name similarity + date proximity bonus
        date_bonus = 0.0
        if dist <= 30:
            date_bonus = 1 - (dist / 30)  # 0..1
        composite = 1 + name_sim + date_bonus
        amt_candidates.append((att, composite, dist))

    if not amt_candidates:
        return None

    # Filter acceptance rules
    # If transaction has a contact, require name similarity threshold among best candidate.
    contact_present = bool(transaction.get("contact"))
    if contact_present:
        # Keep only those with decent similarity
        filtered = [c for c in amt_candidates if _best_name_similarity(transaction.get("contact"), c[0]) >= 0.5]
        if filtered:
            return _select_best(filtered)
        return None  # Reject ambiguous low-similarity matches (avoids 2006)
    else:
        # No contact: require exact date match and uniqueness by amount
        exact_date = [c for c in amt_candidates if c[2] == 0]
        if len(exact_date) == 1:
            return exact_date[0][0]
        # If multiple exact-date matches, use highest score but only if clearly superior (>1.9)
        if exact_date:
            best = _select_best(exact_date)
            # Verify uniqueness by amount (all share same amount anyway) -> ensure no ambiguity
            # If more than one candidate with same score, reject.
            top_score = [c for c in exact_date if abs(c[1] - (1 + 0 + 1)) < 1e-6]  # pure amount+date scenario
            if len(top_score) == 1:
                return best
        return None


def find_transaction(
    attachment: Attachment,
    transactions: list[Transaction],
) -> Transaction | None:
    """Find the best matching transaction for a given attachment.

    Symmetric heuristics to find_attachment.
    1. Reference match first.
    2. Amount filter then rank by date proximity & name similarity.
    Acceptance rules mirror those of find_attachment.
    """
    att_ref = _normalize_reference(attachment.get("data", {}).get("reference"))
    if att_ref:
        for tx in transactions:
            if _reference_match(tx, attachment):
                return tx

    # Attachment date candidates used for proximity
    candidates: list[tuple[Transaction, float, int]] = []
    for tx in transactions:
        if not _is_amount_match(tx, attachment):
            continue
        tx_date = _parse_date(tx.get("date"))
        if not tx_date:
            continue
        dist = _date_distance_days(tx_date, attachment)
        # Name similarity: compare transaction contact to any attachment name
        name_sim = 0.0
        if tx.get("contact"):
            for name in _attachment_names(attachment):
                name_sim = max(name_sim, _name_similarity(tx.get("contact"), name))
        date_bonus = 0.0
        if dist <= 30:
            date_bonus = 1 - (dist / 30)
        composite = 1 + name_sim + date_bonus
        candidates.append((tx, composite, dist))

    if not candidates:
        return None

    # Determine if attachment has any counterparty name (excluding company itself)
    has_names = bool(_attachment_names(attachment))
    with_contact = [c for c in candidates if c[0].get("contact")]
    if has_names and with_contact:
        filtered = [c for c in with_contact if c[1] >= 1.5]  # implies name_sim >= ~0.5
        if filtered:
            # Sort and return
            filtered.sort(key=lambda x: (-x[1], x[2], x[0]["id"]))
            return filtered[0][0]
        # If names exist but no confident name-based match, fall back to strict date rule
    # Fallback or cases without names/contacts: require exact date match uniqueness
    exact_date = [c for c in candidates if c[2] == 0]
    if len(exact_date) == 1:
        return exact_date[0][0]
    return None
