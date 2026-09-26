"""Optional live collector: listens to Bitcoin peers for new transactions and writes BEANS input CSVs.

A separate tool; the BEANS product itself stays offline. Point it at peers you choose (`--peer host:port`, or
`--dns-seed` to ask the public DNS seeds), and it writes one row per (transaction, announcing peer): exactly the
network-observation data BEANS analyses (first relay, relay timing, ASN / country after enrichment). Files rotate into
a folder that `beans watch` monitors.

Protocol: version / verack handshake, answers pings, receives `inv` announcements and fetches each new transaction
once with `getdata` (witness form). Behaves like a light, well-mannered peer: bounded peers, no relaying, no spam.

Limits, stated rather than papered over:
  * A transaction names the coins it spends (prev txid:vout) but not their amounts or addresses, and the P2P protocol
    cannot look them up. Inputs are resolved from transactions the collector has already seen (this covers chains such
    as peel chains, whose parent came through first); unresolved inputs are counted in `unresolved_inputs`, never guessed.
  * With unresolved inputs the fee is unknown and left empty.
"""
import asyncio
import csv
import hashlib
import os
import random
import socket
import struct
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MAGIC = bytes.fromhex("f9beb4d9")          # mainnet
PROTOCOL_VERSION = 70016
USER_AGENT = b"/beans-collector:1.0/"
MSG_TX, MSG_WITNESS_TX = 1, 0x40000001
DNS_SEEDS = ["seed.bitcoin.sipa.be", "dnsseed.bluematt.me", "seed.bitcoinstats.com", "seed.bitcoin.jonasschnelli.ch",
             "seed.btc.petertodd.net", "seed.bitcoin.sprovoost.nl"]
COLS = ["timestamp", "src_ip", "src_port", "dst_ip", "dst_port", "txid", "input_addresses", "input_amounts",
        "output_addresses", "output_amounts", "fee", "script_type", "tx_version", "locktime", "rbf", "unresolved_inputs"]


# ---------------------------------------------------------------------------------------------- encoding helpers
def sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def hash160(b: bytes) -> bytes:
    return hashlib.new("ripemd160", hashlib.sha256(b).digest()).digest()


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58check(version: int, payload: bytes) -> str:
    raw = bytes([version]) + payload
    raw += sha256d(raw)[:4]
    n, out = int.from_bytes(raw, "big"), ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + out


BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def _convertbits(data, frombits, tobits):
    acc = bits = 0
    ret, maxv = [], (1 << tobits) - 1
    for v in data:
        acc = (acc << frombits) | v
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


def segwit_address(witver: int, program: bytes, hrp: str = "bc") -> str:
    """BIP-173 (v0, bech32) / BIP-350 (v1+, bech32m) address."""
    data = [witver] + _convertbits(program, 8, 5)
    const = 1 if witver == 0 else 0x2BC830A3
    hrpx = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    pm = _polymod(hrpx + data + [0] * 6) ^ const
    checksum = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH32[d] for d in data + checksum)


def script_address(spk: bytes) -> Tuple[Optional[str], str]:
    """(address, script type) for standard output scripts; (None, 'UNKNOWN') otherwise."""
    if len(spk) == 25 and spk[:3] == b"\x76\xa9\x14" and spk[23:] == b"\x88\xac":
        return base58check(0x00, spk[3:23]), "P2PKH"
    if len(spk) == 23 and spk[:2] == b"\xa9\x14" and spk[22:] == b"\x87":
        return base58check(0x05, spk[2:22]), "P2SH"
    if len(spk) == 22 and spk[:2] == b"\x00\x14":
        return segwit_address(0, spk[2:]), "P2WPKH"
    if len(spk) == 34 and spk[:2] == b"\x00\x20":
        return segwit_address(0, spk[2:]), "P2WSH"
    if len(spk) == 34 and spk[:2] == b"\x51\x20":
        return segwit_address(1, spk[2:]), "P2TR"
    return None, "UNKNOWN"


# ---------------------------------------------------------------------------------------------- transaction parsing
class _Reader:
    def __init__(self, b: bytes):
        self.b, self.i = b, 0

    def take(self, n: int) -> bytes:
        if self.i + n > len(self.b):
            raise ValueError("truncated")
        out = self.b[self.i:self.i + n]
        self.i += n
        return out

    def u8(self): return self.take(1)[0]
    def u32(self): return struct.unpack("<I", self.take(4))[0]
    def i32(self): return struct.unpack("<i", self.take(4))[0]
    def u64(self): return struct.unpack("<Q", self.take(8))[0]

    def varint(self) -> int:
        n = self.u8()
        return n if n < 0xFD else struct.unpack({0xFD: "<H", 0xFE: "<I", 0xFF: "<Q"}[n], self.take({0xFD: 2, 0xFE: 4, 0xFF: 8}[n]))[0]

    def varbytes(self) -> bytes:
        return self.take(self.varint())


def varint(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


@dataclass
class Tx:
    txid: str
    version: int
    locktime: int
    inputs: List[Tuple[str, int, bytes, List[bytes], int]]        # prev txid, vout, scriptSig, witness, sequence
    outputs: List[Tuple[Optional[str], int, str]]                 # address, value (sat), script type

    @property
    def rbf(self) -> bool:
        return any(seq < 0xFFFFFFFE for *_, seq in self.inputs)


def parse_tx(raw: bytes) -> Tx:
    r = _Reader(raw)
    version = r.i32()
    segwit = raw[4:6] == b"\x00\x01"
    if segwit:
        r.take(2)
    ins = []
    for _ in range(r.varint()):
        prev = r.take(32)[::-1].hex()
        vout = r.u32()
        ins.append([prev, vout, r.varbytes(), [], r.u32()])
    outs = []
    for _ in range(r.varint()):
        value = r.u64()
        addr, typ = script_address(r.varbytes())
        outs.append((addr, value, typ))
    if segwit:
        for vin in ins:
            vin[3] = [r.varbytes() for _ in range(r.varint())]
    locktime = r.u32()
    # txid = double SHA-256 of the serialisation without marker, flag and witnesses
    base = struct.pack("<i", version) + varint(len(ins)) + b"".join(
        bytes.fromhex(p)[::-1] + struct.pack("<I", v) + varint(len(s)) + s + struct.pack("<I", q) for p, v, s, _, q in ins) \
        + varint(len(outs)) + b"".join(_out_bytes(raw, outs)) + struct.pack("<I", locktime)
    return Tx(sha256d(base)[::-1].hex(), version, locktime, [tuple(x) for x in ins], outs)


def _out_bytes(raw, outs):
    """Re-serialise outputs from the raw bytes (scripts are not kept on the Tx, so re-read them)."""
    r = _Reader(raw)
    r.i32()
    if raw[4:6] == b"\x00\x01":
        r.take(2)
    for _ in range(r.varint()):
        r.take(36)
        r.varbytes()
        r.u32()
    res = []
    for _ in range(r.varint()):
        v = r.take(8)
        s = r.varbytes()
        res.append(v + varint(len(s)) + s)
    return res


def input_address(script_sig: bytes, witness: List[bytes]) -> Optional[str]:
    """Spender address derivable from the input itself (P2WPKH, P2PKH, P2SH-P2WPKH, P2WSH); None when not derivable."""
    if not script_sig and len(witness) == 2 and len(witness[1]) == 33:                        # P2WPKH
        return segwit_address(0, hash160(witness[1]))
    if not script_sig and len(witness) >= 2 and witness[-1]:                                  # P2WSH
        return segwit_address(0, hashlib.sha256(witness[-1]).digest())
    if script_sig and len(script_sig) == 23 and script_sig[:3] == b"\x16\x00\x14":           # P2SH-P2WPKH
        return base58check(0x05, hash160(script_sig[1:]))
    if script_sig and not witness:                                                             # P2PKH: <sig> <pubkey>
        r = _Reader(script_sig)
        try:
            r.take(r.u8())
            pub = r.take(r.u8())
            if len(pub) in (33, 65) and r.i == len(script_sig):
                return base58check(0x00, hash160(pub))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------------------------- P2P messages
def message(command: str, payload: bytes = b"") -> bytes:
    return MAGIC + command.encode().ljust(12, b"\0") + struct.pack("<I", len(payload)) + sha256d(payload)[:4] + payload


def _netaddr(ip: str, port: int) -> bytes:
    try:
        raw = socket.inet_pton(socket.AF_INET6, ip)
    except OSError:
        raw = b"\0" * 10 + b"\xff\xff" + socket.inet_aton(ip)
    return struct.pack("<Q", 0) + raw + struct.pack(">H", port)


def version_payload(peer_ip: str, peer_port: int) -> bytes:
    return (struct.pack("<iQq", PROTOCOL_VERSION, 0, int(time.time())) + _netaddr(peer_ip, peer_port)
            + _netaddr("0.0.0.0", 0) + struct.pack("<Q", random.getrandbits(64)) + varint(len(USER_AGENT)) + USER_AGENT
            + struct.pack("<i", 0) + b"\x01")        # start height 0, relay = 1 (we want tx announcements)


async def read_message(reader: asyncio.StreamReader) -> Tuple[str, bytes]:
    head = await reader.readexactly(24)
    if head[:4] != MAGIC:
        raise ConnectionError("bad magic")
    command = head[4:16].rstrip(b"\0").decode(errors="replace")
    length, checksum = struct.unpack("<I", head[16:20])[0], head[20:24]
    if length > 4_000_000:
        raise ConnectionError("oversized message")
    payload = await reader.readexactly(length)
    if sha256d(payload)[:4] != checksum:
        raise ConnectionError("bad checksum")
    return command, payload


# ---------------------------------------------------------------------------------------------- collector
@dataclass
class Collector:
    out_dir: Path
    rotate_s: int = 300
    max_peers: int = 8
    seen_limit: int = 200_000
    outputs: "OrderedDict[str, List[Tuple[Optional[str], int]]]" = field(default_factory=OrderedDict)
    txs: Dict[str, Tx] = field(default_factory=dict)
    requested: Dict[str, float] = field(default_factory=dict)
    pending_obs: Dict[str, list] = field(default_factory=dict)
    stats: Dict[str, int] = field(default_factory=lambda: {"peers": 0, "inv": 0, "tx": 0, "rows": 0, "files": 0,
                                                          "txid_mismatch": 0})

    def __post_init__(self):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._rows: List[list] = []
        self._opened = time.time()

    def remember(self, tx: Tx):
        self.outputs[tx.txid] = [(a, v) for a, v, _ in tx.outputs]
        self.txs[tx.txid] = tx
        while len(self.outputs) > self.seen_limit:
            old, _ = self.outputs.popitem(last=False)
            self.txs.pop(old, None)

    def row(self, tx: Tx, ts: float, ip: str, port: int) -> list:
        in_addr, in_amt, unresolved = [], [], 0
        for prev, vout, *_ in tx.inputs:
            parent = self.outputs.get(prev)
            if parent and vout < len(parent) and parent[vout][0]:
                in_addr.append(parent[vout][0])
                in_amt.append(parent[vout][1] / 1e8)
            else:
                unresolved += 1
        outs = [(a, v) for a, v, _ in tx.outputs if a]
        fee = "" if unresolved else round(sum(in_amt) - sum(v for _, v in outs) / 1e8, 8)
        stype = next((t for _, _, t in tx.outputs if t != "UNKNOWN"), "UNKNOWN")
        return [datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", ip, port,
                "collector", 8333, tx.txid, ";".join(in_addr), ";".join(f"{x:.8f}" for x in in_amt),
                ";".join(a for a, _ in outs), ";".join(f"{v / 1e8:.8f}" for _, v in outs), fee, stype,
                tx.version, tx.locktime, int(tx.rbf), unresolved]

    def observe(self, txid: str, ts: float, ip: str, port: int):
        tx = self.txs.get(txid)
        if tx is None:
            self.pending_obs.setdefault(txid, []).append((ts, ip, port))
            return
        if not tx.outputs or not any(a for a, _, _ in tx.outputs):
            return
        self._rows.append(self.row(tx, ts, ip, port))
        self.stats["rows"] += 1
        if time.time() - self._opened >= self.rotate_s:
            self.flush()

    def on_tx(self, raw: bytes):
        tx = parse_tx(raw)
        if self.requested and tx.txid not in self.requested:   # our txid must equal the hash the peer announced
            self.stats["txid_mismatch"] += 1
        self.remember(tx)
        self.stats["tx"] += 1
        for ts, ip, port in self.pending_obs.pop(tx.txid, []):
            self.observe(tx.txid, ts, ip, port)

    def flush(self) -> Optional[Path]:
        self._opened = time.time()
        if not self._rows:
            return None
        name = self.out_dir / f"mempool_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        tmp = name.with_suffix(".part")
        with open(tmp, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(COLS)
            w.writerows(self._rows)
        os.replace(tmp, name)          # atomic: `beans watch` never sees a half-written file
        self._rows = []
        self.stats["files"] += 1
        return name

    async def peer(self, host: str, port: int, stop: asyncio.Event):
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 10)
        except (OSError, asyncio.TimeoutError):
            return
        ip = writer.get_extra_info("peername")[0]
        try:
            writer.write(message("version", version_payload(ip, port)))
            await writer.drain()
            self.stats["peers"] += 1
            while not stop.is_set():
                cmd, payload = await asyncio.wait_for(read_message(reader), 120)
                now = time.time()
                if cmd == "version":
                    writer.write(message("verack"))
                elif cmd == "ping":
                    writer.write(message("pong", payload))
                elif cmd == "inv":
                    r = _Reader(payload)
                    want = []
                    for _ in range(r.varint()):
                        typ, h = r.u32(), r.take(32)[::-1].hex()
                        if typ in (MSG_TX, MSG_WITNESS_TX):
                            self.stats["inv"] += 1
                            self.observe(h, now, ip, port)
                            if h not in self.txs and now - self.requested.get(h, 0) > 60:
                                self.requested[h] = now
                                want.append(h)
                    if want:
                        writer.write(message("getdata", varint(len(want)) + b"".join(
                            struct.pack("<I", MSG_WITNESS_TX) + bytes.fromhex(h)[::-1] for h in want)))
                elif cmd == "tx":
                    try:
                        self.on_tx(payload)
                    except ValueError:
                        pass
                await writer.drain()
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.stats["peers"] -= 1
            writer.close()

    async def run(self, peers: List[Tuple[str, int]], seconds: Optional[float] = None, log=print):
        stop = asyncio.Event()
        tasks = [asyncio.create_task(self.peer(h, p, stop)) for h, p in peers[:self.max_peers]]
        start = time.time()
        try:
            while any(not t.done() for t in tasks) and (seconds is None or time.time() - start < seconds):
                await asyncio.sleep(5)
                log(f"peers {self.stats['peers']} · announcements {self.stats['inv']} · transactions {self.stats['tx']} · "
                    f"rows {self.stats['rows']} · files {self.stats['files']}")
                if time.time() - self._opened >= self.rotate_s:
                    self.flush()
        finally:
            stop.set()
            for t in tasks:
                t.cancel()
            self.flush()


def dns_seed_peers(n: int = 8) -> List[Tuple[str, int]]:
    found = []
    for seed in DNS_SEEDS:
        try:
            found += [(a[4][0], 8333) for a in socket.getaddrinfo(seed, 8333, proto=socket.IPPROTO_TCP)]
        except OSError:
            continue
    random.shuffle(found)
    return list(dict.fromkeys(found))[:n]
