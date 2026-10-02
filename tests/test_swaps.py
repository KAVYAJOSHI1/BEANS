"""Swap memos: OP_RETURN capture in the collector, memo grammar, ingest, and the CROSS_CHAIN_EXIT directive."""
import struct

import pandas as pd

from beans.collector import p2p
from beans.enrich import swaps
from tests.test_nextgen import VASP_IN, _decide, _frames

MEMO = "=:ETH.ETH:0x3021C479f7F8C9f1D5c7d8523BA5e22C0Bcb5430:1000000:t:30"


def test_memo_grammar_is_strict():
    p = swaps.parse_memo(MEMO)
    assert p["destination_chain"] == "ETH" and p["destination_address"].startswith("0x3021") and p["limit"] == "1000000"
    assert swaps.parse_memo("=:e:0xabc")["asset"] == "ETH.ETH"            # short asset form is expanded
    assert swaps.parse_memo("SWAP:BTC.BTC:bc1qxyz")["destination_chain"] == "BTC"
    for bad in (None, "", "hello world", "=:ETH.ETH", "=::0xabc", "ADD:ETH.ETH:0xabc", "=:ETH.ETH:has space"):
        assert swaps.parse_memo(bad) is None


def test_op_return_payloads():
    ok = b"\x6a" + bytes([len(MEMO)]) + MEMO.encode()
    assert p2p.op_return_memo(ok) == MEMO
    long = ("=:ETH.ETH:" + "a" * 70)
    assert p2p.op_return_memo(b"\x6a\x4c" + bytes([len(long)]) + long.encode()) == long   # OP_PUSHDATA1
    assert p2p.op_return_memo(b"\x6a\x04\x00\x01\x02\x03") is None                        # binary payload
    assert p2p.op_return_memo(b"\x76\xa9\x14" + b"\x00" * 20 + b"\x88\xac") is None       # not OP_RETURN


def test_collector_row_carries_the_memo_and_the_unconfirmed_flag(tmp_path):
    raw_out = struct.pack("<Q", 0) + bytes([len(MEMO) + 2, 0x6A, len(MEMO)]) + MEMO.encode()
    pay = struct.pack("<Q", 50_000) + bytes([22]) + b"\x00\x14" + b"\x11" * 20
    raw = (struct.pack("<i", 2) + b"\x01" + b"\xaa" * 32 + struct.pack("<I", 0) + b"\x00" + struct.pack("<I", 0xFFFFFFFD)
           + b"\x02" + pay + raw_out + struct.pack("<I", 0))
    tx = p2p.parse_tx(raw)
    assert tx.memo == MEMO and tx.rbf
    row = dict(zip(p2p.COLS, p2p.Collector(tmp_path).row(tx, 1.7e9, "1.2.3.4", 8333)))
    assert row["op_return"] == MEMO and row["confirmed"] == 0


def _swap_frames():
    f = _frames([("t0", 0, [("src", 1.0)], [("W", 0.5)]), ("t1", 30, [("W", 0.5)], [("VAULT", 0.45), ("W", 0.04)])])
    f.tx["op_return"] = [None, MEMO]
    return f


def test_swap_memo_on_the_path_is_a_cross_chain_exit_with_the_destination():
    ra = _decide(_swap_frames(), "W", {"X": VASP_IN})
    assert ra["action"] == "CROSS_CHAIN_EXIT"
    d = ra["facts"]["destination"]
    assert d["destination_chain"] == "ETH" and d["destination_address"].startswith("0x3021")
    assert ra["facts"]["deposit_address"] == "VAULT"       # largest output that does not return to the sender
    assert "swap memo" in ra["facts"]["check"] and ra["cross_chain_exits"][0]["entity_type"] == "SWAP"


def test_no_memo_no_exit_and_frames_without_the_column_still_work():
    f = _swap_frames()
    f.tx["op_return"] = [None, None]
    assert _decide(f, "W", {"X": VASP_IN})["action"] != "CROSS_CHAIN_EXIT"
    f2 = _frames([("t0", 0, [("src", 1.0)], [("W", 0.5)])])          # no op_return column at all
    assert _decide(f2, "W", {})["action"] != "CROSS_CHAIN_EXIT"


def test_memo_survives_csv_ingest(tmp_path):
    from beans.ingest.pipeline import ForensicPipeline
    from beans.store.duck import DuckStore
    f = tmp_path / "m.csv"
    f.write_text("timestamp,src_ip,txid,input_addresses,input_amounts,output_addresses,output_amounts,fee,script_type,memo\n"
                 f"2026-09-01T10:00:00Z,1.2.3.4,{'ab' * 32},bc1qa,0.5,bc1qb,0.49,0.01,P2WPKH,{MEMO}\n")
    store = DuckStore(tmp_path / "m.duckdb")
    ForensicPipeline(store).run_file_ingestion(f)
    con = store.get_connection()
    try:
        assert con.execute("SELECT op_return FROM transactions").fetchone()[0] == MEMO
    finally:
        con.close()
