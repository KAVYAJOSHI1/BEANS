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


def test_address_only_inputs_and_resolver(tmp_path):
    seg, pub = _tx(True)                      # spends aa..aa:1, a coin the collector never saw
    t = p2p.parse_tx(seg)
    spender = p2p.segwit_address(0, p2p.hash160(pub))
    c = p2p.Collector(tmp_path)
    row = dict(zip(p2p.COLS, c.row(t, 1_790_000_000, "1.2.3.4", 8333)))
    # amount unknown, but the address is read from the witness → clustering can still use it
    assert row["input_addresses"] == spender and row["input_amounts"] == "" and row["unresolved_inputs"] == 1

    calls = []
    def resolver(outpoints):
        calls.append(list(outpoints))
        return {("aa" * 32, 1): (spender, 80_000)}
    c = p2p.Collector(tmp_path / "r", resolver=resolver)
    c.remember(t)
    c.observe(t.txid, 1_790_000_000, "1.2.3.4", 8333)
    text = c.flush().read_text().splitlines()
    r = dict(zip(p2p.COLS, text[1].split(",")))
    assert calls == [[("aa" * 32, 1)]] and c.stats["resolved_prevouts"] == 1
    assert r["input_amounts"] == "0.00080000" and r["unresolved_inputs"] == "0" and float(r["fee"]) == 0.0003

    def broken(_):
        raise OSError("node down")
    c = p2p.Collector(tmp_path / "b", resolver=broken)       # an outage never stops collection
    c.remember(t)
    c.observe(t.txid, 1_790_000_000, "1.2.3.4", 8333)
    assert c.flush() is not None and c.stats["resolver_errors"] == 1


def _serve(handler_body):
    import http.server
    import json
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def _reply(self, obj):
            data = json.dumps(obj).encode()
            self.send_response(200 if obj is not None else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._reply(handler_body("GET", self.path, None, self.headers))

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._reply(handler_body("POST", self.path, body, self.headers))

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_resolvers_against_local_servers():
    from beans.collector.resolve import BitcoindResolver, EsploraResolver, from_args
    A = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"

    def esplora(method, path, body, headers):
        if path == "/api/tx/" + "11" * 32:
            return {"vout": [{"scriptpubkey_address": "x", "value": 1}, {"scriptpubkey_address": A, "value": 123_456}]}
        return None
    srv = _serve(esplora)
    r = EsploraResolver(f"http://127.0.0.1:{srv.server_port}/api/")
    assert r([("11" * 32, 1), ("22" * 32, 0), ("11" * 32, 9)]) == {("11" * 32, 1): (A, 123_456)}
    srv.shutdown()

    seen = {}
    def bitcoind(method, path, body, headers):
        seen["auth"] = headers.get("Authorization")
        return [{"id": q["id"], "error": None,
                 "result": {"value": 0.0005, "scriptPubKey": {"address": A}} if q["params"][1] == 0 else None}
                for q in body]
    srv = _serve(bitcoind)
    r = BitcoindResolver(f"http://user:p%40ss@127.0.0.1:{srv.server_port}")
    assert r([("33" * 32, 0), ("33" * 32, 1)]) == {("33" * 32, 0): (A, 50_000)}
    import base64
    assert seen["auth"] == "Basic " + base64.b64encode(b"user:p@ss").decode()
    srv.shutdown()
    assert from_args(None, None) is None
    import pytest
    with pytest.raises(ValueError):
        from_args("http://a", "http://b")


def test_esplora_gives_up_when_every_lookup_fails():
    import time
    from beans.collector.resolve import EsploraResolver
    hits = []
    def always_404(method, path, body, headers):
        hits.append(path)
        return None
    srv = _serve(always_404)
    r = EsploraResolver(f"http://127.0.0.1:{srv.server_port}", workers=2, give_up_after=6)
    t0 = time.monotonic()
    assert r([(f"{i:064x}", 0) for i in range(500)]) == {}
    assert time.monotonic() - t0 < 10 and len(hits) < 100      # stopped early, did not walk all 500
    srv.shutdown()
