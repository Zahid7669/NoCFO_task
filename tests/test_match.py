import pytest
from src.match import find_attachment, find_transaction
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'src' / 'data'

with open(DATA_DIR / 'transactions.json', 'r', encoding='utf-8') as f:
    TRANSACTIONS = json.load(f)
with open(DATA_DIR / 'attachments.json', 'r', encoding='utf-8') as f:
    ATTACHMENTS = json.load(f)

# Helper maps
TX_MAP = {tx['id']: tx for tx in TRANSACTIONS}
ATT_MAP = {att['id']: att for att in ATTACHMENTS}


def test_reference_match():
    tx = TX_MAP[2001]
    att = find_attachment(tx, ATTACHMENTS)
    assert att is not None and att['id'] == 3001
    tx_back = find_transaction(att, TRANSACTIONS)
    assert tx_back is not None and tx_back['id'] == 2001


def test_amount_name_date_combo():
    # Transaction 2007 should match attachment 3006 via amount+name+due date
    tx = TX_MAP[2007]
    att = find_attachment(tx, ATTACHMENTS)
    assert att is not None and att['id'] == 3006


def test_no_false_positive_similar_name():
    # 2005 matches 3005; 2006 (typo in name) should return None
    tx_good = TX_MAP[2005]
    att_good = find_attachment(tx_good, ATTACHMENTS)
    assert att_good is not None and att_good['id'] == 3005

    tx_bad = TX_MAP[2006]
    att_bad = find_attachment(tx_bad, ATTACHMENTS)
    assert att_bad is None


def test_outgoing_with_no_contact():
    # 2004 should match 3004 (amount + date proximity) even without contact name
    tx = TX_MAP[2004]
    att = find_attachment(tx, ATTACHMENTS)
    assert att is not None and att['id'] == 3004


def test_sales_invoice_direction():
    # Attachment 3002 should map to transaction 2002 by reference
    att = ATT_MAP[3002]
    tx = find_transaction(att, TRANSACTIONS)
    assert tx is not None and tx['id'] == 2002


def test_unmatched_items():
    # 2009 has reference not present in attachments -> None
    tx_unmatched = TX_MAP[2009]
    att = find_attachment(tx_unmatched, ATTACHMENTS)
    assert att is None

    # Attachment 3008 should not match (different amount/reference not present in transactions)
    att_unmatched = ATT_MAP[3008]
    tx = find_transaction(att_unmatched, TRANSACTIONS)
    assert tx is None


def test_receipt_vs_invoice_logic():
    # Ensure receipt with unique reference does NOT accidentally match incorrect transaction
    att_receipt = ATT_MAP[3008]
    tx_found = find_transaction(att_receipt, TRANSACTIONS)
    assert tx_found is None


def test_symmetry_where_expected():
    # For pairs that are expected to match both ways
    pairs = [(2003, 3003), (2008, 3007)]
    for tx_id, att_id in pairs:
        tx = TX_MAP[tx_id]
        att = ATT_MAP[att_id]
        att_found = find_attachment(tx, ATTACHMENTS)
        tx_found = find_transaction(att, TRANSACTIONS)
        assert att_found and att_found['id'] == att_id
        assert tx_found and tx_found['id'] == tx_id


if __name__ == '__main__':
    pytest.main([__file__])
