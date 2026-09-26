"""Live collector: encodings against published test vectors, transaction parsing, CSV rows."""
import struct

from beans.collector import p2p


def test_address_vectors():
    # BIP-173 / BIP-350 test vectors and the genesis-block address
    assert p2p.script_address(bytes.fromhex("0014751e76e8199196d454941c45d1b3a323f1433bd6")) == \
        ("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "P2WPKH")
    assert p2p.script_address(bytes.fromhex("00201863143c14c5166804bd19203356da136c985678cd4d27a1b8c6329604903262"))[0] == \
        "bc1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qccfmv3"
    assert p2p.script_address(bytes.fromhex("512079be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"))[0] == \
        "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"
    assert p2p.script_address(bytes.fromhex("76a91462e907b15cbf27d5425399ebf6f0fb50ebb88f1888ac"))[0] == \
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    assert p2p.script_address(b"\x6a\x04test") == (None, "UNKNOWN")        # OP_RETURN


def _tx(witness: bool, seq=0xFFFFFFFD):
    pub = bytes.fromhex("02" + "11" * 32)
    ins = bytes.fromhex("aa" * 32) + struct.pack("<I", 1) + (b"\x00" if witness else b"\x02\x00\x00") + struct.pack("<I", seq)
    spk = bytes.fromhex("0014") + p2p.hash160(pub)
    outs = struct.pack("<Q", 50_000) + p2p.varint(len(spk)) + spk
    body = struct.pack("<i", 2) + b"\x01" + ins + b"\x01" + outs
    wit = b"\x02" + p2p.varint(71) + b"\x30" * 71 + p2p.varint(33) + pub if witness else b""
    lock = struct.pack("<I", 862000)
    if witness:
        return struct.pack("<i", 2) + b"\x00\x01" + body[4:] + wit + lock, pub
    return body + lock, pub


def test_txid_and_fields():
    legacy, _ = _tx(False)
    t = p2p.parse_tx(legacy)
    assert t.txid == p2p.sha256d(legacy)[::-1].hex()          # non-witness: txid is the hash of the raw bytes
    seg, pub = _tx(True)
    ts = p2p.parse_tx(seg)
    assert ts.version == 2 and ts.locktime == 862000 and ts.rbf
    assert ts.outputs[0] == (p2p.segwit_address(0, p2p.hash160(pub)), 50_000, "P2WPKH")
    assert p2p.input_address(ts.inputs[0][2], ts.inputs[0][3]) == p2p.segwit_address(0, p2p.hash160(pub))


def test_message_framing_and_rows(tmp_path):
    m = p2p.message("ping", b"12345678")
    assert m[:4] == p2p.MAGIC and m[4:16].rstrip(b"\0") == b"ping" and m[20:24] == p2p.sha256d(b"12345678")[:4]
    c = p2p.Collector(tmp_path)
    parent, pub = _tx(True)
    ptx = p2p.parse_tx(parent)
    c.remember(ptx)
    # a child spending the parent's output 0 is fully resolved; an unknown input is counted, not guessed
    child = p2p.Tx("cc" * 32, 2, 0, [(ptx.txid, 0, b"", [], 0xFFFFFFFF), ("ee" * 32, 3, b"", [], 0xFFFFFFFF)],
                   [(p2p.segwit_address(0, b"\x22" * 20), 40_000, "P2WPKH")])
    row = dict(zip(p2p.COLS, c.row(child, 1_790_000_000, "1.2.3.4", 8333)))
    assert row["input_amounts"] == "0.00050000" and row["unresolved_inputs"] == 1 and row["fee"] == ""
    c.observe(ptx.txid, 1_790_000_000, "5.6.7.8", 8333)
    f = c.flush()
    text = f.read_text().splitlines()
    assert text[0].split(",")[:6] == p2p.COLS[:6] and len(text) == 2 and "5.6.7.8" in text[1]
