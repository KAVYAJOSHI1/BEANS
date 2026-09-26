"""Event-driven Bitcoin economy simulator with ground truth (generator v2).

Every input spends an earlier output (real UTXO ledger), so money flows form a connected graph that
clustering, peel-chain detection and risk propagation can work on. Each address belongs to exactly one
simulated entity, which gives address-level and transaction-level labels. IPs are sampled from real
prefixes of the bundled DB-IP databases (data/intel/ip_pools.json) so enrichment behaves exactly as it
would on real traffic. Deterministic for a given seed.

Legitimate: miners (coinbase + pool payouts), exchanges (withdrawal batches, deposit sweeps, cold→hot
refills), merchants (daily sweeps), retail users (payments with change), privacy users (legit CoinJoin).
Illicit: RANSOMWARE, PEEL_CHAIN, HACK_LAUNDERING, DARKNET_MARKET, FAN_OUT_SMURF, ROUND_TRIP, DUSTING.
Hardness: exchange payouts look like smurfing fan-outs, legit users CoinJoin, some origin IPs are never
observed, relays add noise, shared residential IPs.
"""
import hashlib
import heapq
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from ipaddress import ip_network
from typing import Callable, Dict, List, Optional, Tuple

from beans.config import settings

B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
DUST = 0.00000546
DENOMS = [1.0, 0.5, 0.1, 0.05, 0.01]
ILLICIT = {"RANSOMWARE", "PEEL_CHAIN", "HACK_LAUNDERING", "DARKNET_MARKET", "FAN_OUT_SMURF", "ROUND_TRIP", "DUSTING"}
T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
T0_HEIGHT = 862_000                 # block height at T0 (one block per 10 minutes)

# Wallet-software fingerprints: (tx version, anti-fee-sniping locktime?, signals RBF?). Individuals (illicit or not)
# draw from the SAME distribution, so fingerprints can link one owner's transactions but never mark someone as a
# criminal by itself. Services run batch software. Chosen by a hash of the entity id: the simulation's random stream,
# and so every dataset, is unchanged by this.
SOFTWARE = {"core": (2, True, True), "electrum": (2, True, False), "mobile_a": (2, False, True),
            "mobile_b": (1, False, False), "service_batch": (2, False, False)}
PERSONAL_SOFTWARE = [("core", 40), ("electrum", 25), ("mobile_a", 20), ("mobile_b", 15)]
SERVICE_TYPOLOGIES = {"EXCHANGE", "MINER", "MERCHANT"}


@dataclass
class Entity:
    eid: str
    typology: str
    script: str = "P2WPKH"
    ips: List[str] = field(default_factory=list)
    hopping: bool = False           # picks a different (VPN/Tor) IP per broadcast
    tz: int = 0                     # UTC offset of the operator (for diurnal behaviour)
    utxos: List[list] = field(default_factory=list)   # [address, amount]
    addresses: List[str] = field(default_factory=list)

    @property
    def illicit(self) -> bool:
        return self.typology in ILLICIT

    def balance(self) -> float:
        return sum(u[1] for u in self.utxos)


class Sim:
    def __init__(self, seed: int = 42, days: int = 7):
        self.rng = random.Random(seed)
        self.seed, self.days = seed, days
        self.end = T0 + timedelta(days=days)
        self.events: list = []
        self.n_events = 0
        self.entities: Dict[str, Entity] = {}
        self.owner: Dict[str, str] = {}
        self.txs: List[dict] = []
        self.tx_counter = 0
        self.cj_queue: List[Tuple[Entity, list, Callable]] = []
        self.pools = json.loads((settings.INTEL_DIR / "ip_pools.json").read_text())
        self.by_type: Dict[str, List[str]] = {}
        for k, v in self.pools.items():
            self.by_type.setdefault(v["type"], []).append(k)
        self.observers = [self.ip("DATACENTER") for _ in range(3)]
        self.relays = [self.ip(self.rng.choice(["DATACENTER", "RESIDENTIAL", "RESIDENTIAL"])) for _ in range(150)]

    # ------------------------------------------------------------------ primitives
    def ip(self, kind: str) -> str:
        pool = self.pools[self.rng.choice(self.by_type[kind])]
        if "ips" in pool:
            return self.rng.choice(pool["ips"])
        net = ip_network(self.rng.choice(pool["prefixes"])[0])
        return str(net.network_address + self.rng.randrange(1, net.num_addresses - 1))

    def address(self, script: str) -> str:
        r = self.rng
        if script == "P2WPKH":
            return "bc1q" + "".join(r.choice(B32) for _ in range(38))
        if script == "P2WSH":
            return "bc1q" + "".join(r.choice(B32) for _ in range(58))
        if script == "P2TR":
            return "bc1p" + "".join(r.choice(B32) for _ in range(58))
        return ("1" if script == "P2PKH" else "3") + "".join(r.choice(B58) for _ in range(33))

    def entity(self, prefix: str, typology: str, ip_kind: Optional[str], n_ips: int = 1, script: str = "P2WPKH",
               hopping: bool = False, tz: int = 0) -> Entity:
        eid = f"{prefix}-{len(self.entities):05d}"
        ips = [self.ip(ip_kind) for _ in range(n_ips)] if ip_kind else []
        e = Entity(eid, typology, script, ips, hopping, tz)
        self.entities[eid] = e
        return e

    def software(self, e: Entity) -> str:
        if e.typology in SERVICE_TYPOLOGIES or e.eid.startswith("CJCOORD"):
            return "service_batch"
        h = int(hashlib.sha256(f"{self.seed}|sw|{e.eid}".encode()).hexdigest(), 16) % 100
        for name, share in PERSONAL_SOFTWARE:
            if h < share:
                return name
            h -= share
        return PERSONAL_SOFTWARE[-1][0]

    def new_addr(self, e: Entity, script: Optional[str] = None) -> str:
        a = self.address(script or e.script)
        e.addresses.append(a)
        self.owner[a] = e.eid
        return a

    def at(self, t: datetime, fn: Callable, *args) -> None:
        if t < self.end:
            self.n_events += 1
            heapq.heappush(self.events, (t, self.n_events, fn, args))

    def minutes(self, lo: float, hi: float) -> timedelta:
        return timedelta(minutes=self.rng.uniform(lo, hi))

    def fee(self, n_in: int, n_out: int) -> float:
        vbytes = 11 + 68 * max(n_in, 1) + 31 * n_out
        return round(vbytes * self.rng.choice([2, 4, 6, 10, 15, 25]) * 1e-8, 8)

    # ------------------------------------------------------------------ transactions
    def select(self, e: Entity, need: float, only: Optional[List[list]] = None) -> Optional[List[list]]:
        cands = list(only) if only is not None else sorted(e.utxos, key=lambda u: -u[1])
        chosen, s = [], 0.0
        for u in cands:
            chosen.append(u)
            s += u[1]
            if s >= need:
                return chosen
        return None

    def tx(self, t: datetime, e: Entity, outputs: List[Tuple[str, float]], tx_class: str, *,
           inputs: Optional[List[list]] = None, typology: Optional[str] = None, illicit: Optional[bool] = None,
           change_to: Optional[Entity] = None, extra_inputs: Optional[List[Tuple[Entity, list]]] = None,
           broadcaster: Optional[Entity] = None, fee_override: Optional[float] = None) -> Optional[List[Tuple[str, float]]]:
        """Build and record a transaction. Returns the outputs (with change) or None if unfunded."""
        outputs = [(a, round(v, 8)) for a, v in outputs if v >= DUST]
        total_out = sum(v for _, v in outputs)
        fee = self.fee(len(inputs or []) + 1, len(outputs) + 1)
        coinbase = inputs == []
        ins: List[Tuple[Entity, list]] = []
        if not coinbase:
            chosen = inputs if inputs is not None else self.select(e, total_out + fee)
            if not chosen:
                return None
            ins = [(e, u) for u in chosen] + list(extra_inputs or [])
            if any(u not in owner.utxos for owner, u in ins) or len({id(u) for _, u in ins}) != len(ins):
                return None   # already spent, or the same coin listed twice
        total_in = sum(u[1] for _, u in ins)
        if not coinbase:
            fee = fee_override if fee_override is not None else self.fee(len(ins), len(outputs) + 1)
            change = round(total_in - total_out - fee, 8)
            if change < 0:
                if not extra_inputs or total_in < total_out:
                    return None
                change, fee = 0.0, round(total_in - total_out, 8)   # coinjoin: participants' slack pays the fee
            if change > 0.00002 and not extra_inputs:
                outputs.append((self.new_addr(change_to or e), change))
            elif change > 0:
                fee = round(fee + change, 8)
        for owner, u in ins:
            owner.utxos.remove(u)
        for a, v in outputs:
            self.entities[self.owner[a]].utxos.append([a, v])
        self.tx_counter += 1
        txid = hashlib.sha256(f"beans-{self.seed}-{self.tx_counter}".encode()).hexdigest()
        typ = typology or e.typology
        version, anti_snipe, rbf = SOFTWARE[self.software(broadcaster or e)]
        height = T0_HEIGHT + int((t - T0).total_seconds() // 600)
        self.txs.append({
            "txid": txid, "t": t, "entity": (broadcaster or e).eid, "typology": typ,
            "illicit": self.entities[(broadcaster or e).eid].illicit if illicit is None else illicit,
            "tx_class": tx_class, "fee": 0.0 if coinbase else round(total_in - sum(v for _, v in outputs), 8),
            "inputs": [(u[0], u[1]) for _, u in ins], "outputs": outputs,
            "script": (broadcaster or e).script,
            "tx_version": version, "locktime": height if anti_snipe else 0, "rbf": rbf,
        })
        return outputs

    # ------------------------------------------------------------------ legitimate economy
    def build_legit(self, n_tx: int) -> None:
        r = self.rng
        self.miners = [self.entity("MINER", "MINER", "DATACENTER") for _ in range(2)]
        self.exchanges = []
        for _ in range(3):
            ex = self.entity("EXCH", "EXCHANGE", "DATACENTER", n_ips=2)
            ex.hot = self.new_addr(ex)
            ex.cold = self.new_addr(ex, "P2WSH")
            ex.deposit_utxo_addrs = set()
            self.exchanges.append(ex)
        self.merchants = [self.entity("MERCH", "MERCHANT", "DATACENTER") for _ in range(8)]
        n_retail = max(40, n_tx // 7)
        self.retail = []
        shared_nat = [self.ip("RESIDENTIAL") for _ in range(max(3, n_retail // 25))]
        for i in range(n_retail):
            ips = [r.choice(shared_nat)] if r.random() < 0.2 else None
            u = self.entity("USER", "NORMAL", None if ips else "RESIDENTIAL",
                            script=r.choice(["P2WPKH"] * 6 + ["P2PKH", "P2TR"]), tz=r.choice([5, 1, 0, -5, 8, 3]))
            if ips:
                u.ips = ips
            u.privacy = r.random() < 0.12
            u.buyer = r.random() < 0.08
            self.retail.append(u)

        # genesis: miners mine, fund exchanges; exchanges fund retail over day 1
        for m in self.miners:
            for k in range(6):
                self.tx(T0 + timedelta(minutes=k), m, [(self.new_addr(m), 50.0)], "normal", inputs=[])
        for i, ex in enumerate(self.exchanges):
            m = self.miners[i % 2]
            self.tx(T0 + timedelta(minutes=20 + i), m, [(ex.hot, 80.0)], "normal")
        self.retail_rate = (0.8 * n_tx) / (len(self.retail) * self.days * 24)  # events per user-hour
        for ex in self.exchanges:
            self.at(T0 + self.minutes(30, 90), self.exchange_payout, ex)
            self.at(T0 + timedelta(hours=r.uniform(8, 12)), self.exchange_sweep, ex)
        for m in self.miners:
            self.at(T0 + timedelta(hours=r.uniform(3, 6)), self.miner_cycle, m)
        for mc in self.merchants:
            self.at(T0 + timedelta(hours=r.uniform(18, 30)), self.merchant_sweep, mc)
        for u in self.retail:
            self.at(T0 + timedelta(hours=r.uniform(4, 30)), self.retail_event, u)
        self.at(T0 + timedelta(hours=6), self.coinjoin_round)

    def deposit_addr(self, ex: Entity) -> str:
        a = self.new_addr(ex)
        ex.deposit_utxo_addrs.add(a)
        return a

    def diurnal_ok(self, e: Entity, t: datetime) -> bool:
        h = (t.hour + e.tz) % 24
        return 7 <= h <= 23 or self.rng.random() < 0.15

    def exchange_payout(self, t, ex):
        r = self.rng
        users = r.sample(self.retail, min(len(self.retail), r.randint(10, 45)))
        outs = [(self.new_addr(u), round(r.uniform(0.01, 0.6), 5)) for u in users]
        spend = [u for u in ex.utxos if u[0] not in ex.deposit_utxo_addrs]
        if self.tx(t, ex, outs, "fan_out", inputs=self.select(ex, sum(v for _, v in outs) + 0.01, spend) or None) is None:
            self.refill(t, ex)
        self.at(t + timedelta(hours=r.uniform(2, 4)), self.exchange_payout, ex)

    def refill(self, t, ex):
        cold = [u for u in ex.utxos if u[0] == ex.cold]
        if cold:
            self.tx(t, ex, [(ex.hot, round(sum(u[1] for u in cold) * 0.6, 8))], "normal", inputs=cold)
        else:
            m = self.rng.choice(self.miners)
            self.tx(t, m, [(ex.hot, 40.0)], "normal")

    def exchange_sweep(self, t, ex):
        deps = [u for u in ex.utxos if u[0] in ex.deposit_utxo_addrs]
        for i in range(0, len(deps), 120):
            chunk = deps[i:i + 120]
            if len(chunk) >= 2:
                self.tx(t + timedelta(seconds=i), ex, [(ex.cold, round(sum(u[1] for u in chunk) - 0.001, 8))],
                        "fan_in", inputs=chunk)
        self.at(t + timedelta(hours=self.rng.uniform(8, 13)), self.exchange_sweep, ex)

    def miner_cycle(self, t, m):
        r = self.rng
        self.tx(t, m, [(self.new_addr(m), 25.0)], "normal", inputs=[])
        users = r.sample(self.retail, min(len(self.retail), r.randint(15, 40)))
        self.tx(t + self.minutes(20, 60), m, [(self.new_addr(u), round(r.uniform(0.005, 0.2), 6)) for u in users], "fan_out")
        self.at(t + timedelta(hours=r.uniform(5, 8)), self.miner_cycle, m)

    def merchant_sweep(self, t, mc):
        if len(mc.utxos) >= 2:
            ex = self.rng.choice(self.exchanges)
            self.tx(t, mc, [(self.deposit_addr(ex), round(mc.balance() * 0.98, 8))], "fan_in", inputs=list(mc.utxos))
        self.at(t + timedelta(hours=self.rng.uniform(20, 28)), self.merchant_sweep, mc)

    def retail_event(self, t, u):
        r = self.rng
        if self.diurnal_ok(u, t) and u.utxos:
            bal = u.balance()
            x = r.random()
            if u.privacy and x < 0.35 and bal > 0.02:
                best = max(u.utxos, key=lambda v: v[1])
                self.cj_queue.append((u, best, None))
            elif u.buyer and x < 0.3 and self.markets:
                mk = r.choice(self.markets)
                self.tx(t, u, [(self.new_addr(mk, "P2WSH"), round(min(bal * 0.5, r.uniform(0.005, 0.2)), 6))], "normal",
                        typology="DARKNET_MARKET", illicit=True)
            elif x < 0.5:
                self.tx(t, u, [(self.new_addr(r.choice(self.merchants)), round(bal * r.uniform(0.05, 0.4), 6))], "normal")
            elif x < 0.8:
                self.tx(t, u, [(self.new_addr(r.choice(self.retail)), round(bal * r.uniform(0.05, 0.5), 6))], "normal")
            else:
                ex = r.choice(self.exchanges)
                self.tx(t, u, [(self.deposit_addr(ex), round(bal * r.uniform(0.3, 0.9), 6))], "normal")
        self.at(t + timedelta(hours=r.expovariate(self.retail_rate)), self.retail_event, u)

    def coinjoin_round(self, t):
        r = self.rng
        queue, self.cj_queue = self.cj_queue, []
        extra = [u for u in r.sample(self.retail, min(len(self.retail), 30)) if u.privacy and u.utxos]
        parts = queue + [(u, max(u.utxos, key=lambda v: v[1]), None) for u in extra
                         if not any(p[0] is u for p in queue)]
        seen_coins, uniq = set(), []
        for p in parts:   # one coin per participant, no coin twice
            if p[1] in p[0].utxos and id(p[1]) not in seen_coins:
                seen_coins.add(id(p[1]))
                uniq.append(p)
        parts = uniq
        if len(parts) >= 5:
            for d in DENOMS:
                elig = [p for p in parts if p[1][1] >= d + 0.0005]
                if len(elig) >= 5:
                    break
            else:
                elig = []
            if len(elig) >= 5:
                coord = self.coordinator
                outs, cb = [], []
                for ent, utxo, fn in elig:
                    mixed = self.new_addr(ent)
                    outs.append((mixed, d))
                    change = round(utxo[1] - d - 0.0003, 8)
                    if change > 0.00002:
                        outs.append((self.new_addr(ent), change))
                    cb.append((fn, ent, mixed, d))
                r.shuffle(outs)
                first_ent, first_utxo, _ = elig[0]
                res = self.tx(t, first_ent, outs, "coinjoin", inputs=[first_utxo], typology="COINJOIN", illicit=False,
                              extra_inputs=[(e_, u_) for e_, u_, _ in elig[1:]], broadcaster=coord)
                if res:
                    for fn, ent, mixed, amt in cb:
                        if fn:
                            self.at(t + timedelta(hours=r.uniform(1, 8)), fn, ent, mixed, amt)
                    parts = [p for p in parts if p not in elig]
        self.cj_queue.extend(p for p in parts if p[2])  # illicit participants wait for the next round
        self.at(t + timedelta(hours=r.uniform(2.5, 4)), self.coinjoin_round)

    # ------------------------------------------------------------------ illicit behaviour
    def cash_out(self, t, e, addr, amount=None):
        """Deposit whatever sits on `addr` to an exchange."""
        utxos = [u for u in e.utxos if u[0] == addr]
        if utxos:
            ex = self.rng.choice(self.exchanges)
            fee = self.fee(len(utxos), 1)
            self.tx(t, e, [(self.deposit_addr(ex), round(sum(u[1] for u in utxos) - fee, 8))], "normal", inputs=utxos,
                    fee_override=fee)

    def peel(self, t, e, addr, hops_left, cls="peel"):
        utxos = [u for u in e.utxos if u[0] == addr]
        if not utxos:
            return
        amt = sum(u[1] for u in utxos)
        if hops_left <= 0 or amt < 0.01:
            return self.cash_out(t, e, addr)
        r = self.rng
        dest = self.deposit_addr(r.choice(self.exchanges)) if r.random() < 0.6 else self.new_addr(r.choice(self.merchants + self.retail))
        nxt = self.new_addr(e)
        peel_amt = round(amt * r.uniform(0.01, 0.06), 8)
        fee = self.fee(len(utxos), 2)
        out = self.tx(t, e, [(dest, peel_amt), (nxt, round(amt - peel_amt - fee, 8))], cls, inputs=utxos,
                      fee_override=fee)
        if out:
            self.at(t + self.minutes(3, 35), self.peel, e, nxt, hops_left - 1, cls)

    def fund(self, t, e, amount) -> Optional[str]:
        """Exchange withdrawal to a fresh address of `e` (how most actors acquire coins)."""
        ex = self.rng.choice(self.exchanges)
        a = self.new_addr(e)
        spend = [u for u in ex.utxos if u[0] not in ex.deposit_utxo_addrs]
        sel = self.select(ex, amount + 0.01, spend)
        if not sel:
            self.refill(t, ex)
            sel = self.select(ex, amount + 0.01, [u for u in ex.utxos if u[0] not in ex.deposit_utxo_addrs])
        return a if sel and self.tx(t, ex, [(a, amount)], "normal", inputs=sel) else None

    def build_illicit(self, n_tx: int) -> None:
        r = self.rng
        span = lambda lo=1.0, hi=None: T0 + timedelta(hours=r.uniform(lo * 24, (hi or self.days - 1.5) * 24))
        risky = lambda: r.choice(["VPN", "TOR_EXIT", "BULLETPROOF", "VPN"])
        self.coordinator = self.entity("CJCOORD", "NORMAL", "DATACENTER")
        self.markets = []
        for _ in range(max(1, n_tx // 4000)):
            mk = self.entity("MARKET", "DARKNET_MARKET", "TOR_EXIT", n_ips=4, script="P2WSH", hopping=True)
            mk.vendors = [self.entity("VENDOR", "DARKNET_MARKET", "TOR_EXIT", n_ips=2, hopping=True) for _ in range(r.randint(3, 6))]
            self.markets.append(mk)
            self.at(T0 + timedelta(hours=r.uniform(30, 40)), self.market_settle, mk)
        for _ in range(max(3, n_tx // 800)):
            op = self.entity("RANSOM", "RANSOMWARE", risky(), n_ips=5, hopping=True, tz=r.choice([3, 8, -5]))
            self.at(span(1.0, 4.0), self.ransom_campaign, op)
        for _ in range(max(3, n_tx // 600)):
            pc = self.entity("PEEL", "PEEL_CHAIN", risky(), n_ips=r.choice([1, 3]), hopping=r.random() < 0.5)
            self.at(span(), self.peel_start, pc)
        for _ in range(2 if n_tx < 4000 else 3):
            hk = self.entity("HACK", "HACK_LAUNDERING", "DATACENTER", n_ips=1)
            self.at(span(1.0, 3.0), self.hack, hk)
        for _ in range(max(2, n_tx // 1500)):
            sm = self.entity("SMURF", "FAN_OUT_SMURF", "DATACENTER", n_ips=4, hopping=True)
            self.at(span(), self.smurf, sm)
        for _ in range(max(3, n_tx // 1200)):
            rt = self.entity("ROUNDTRIP", "ROUND_TRIP", risky(), n_ips=2)
            self.at(span(), self.round_trip_start, rt)
        for _ in range(2):
            dz = self.entity("DUST", "DUSTING", "BULLETPROOF", n_ips=1)
            self.at(span(1.5), self.dusting, dz)

    def ransom_campaign(self, t, op):
        r = self.rng
        victims = r.sample(self.retail, r.randint(2, 5))
        for v in victims:
            ransom = round(r.uniform(0.3, 2.5), 4)
            vt = t + timedelta(hours=r.uniform(0, 30))
            self.at(vt, self.victim_pays, v, op, ransom)
        self.at(t + timedelta(hours=r.uniform(40, 60)), self.ransom_launder, op)

    def victim_pays(self, t, v, op, ransom):
        if v.balance() < ransom + 0.01:
            if self.fund(t, v, ransom + 0.05):
                self.at(t + self.minutes(30, 180), self.victim_pays, v, op, ransom)
            return
        self.tx(t, v, [(self.new_addr(op), ransom)], "normal", typology="RANSOMWARE", illicit=True)

    def ransom_launder(self, t, op):
        r = self.rng
        if not op.utxos:
            return
        pot = self.new_addr(op)
        if len(op.utxos) > 1:
            self.tx(t, op, [(pot, round(op.balance() - 0.001, 8))], "fan_in", inputs=list(op.utxos))
        else:
            pot = op.utxos[0][0]
        t2 = t + self.minutes(30, 180)
        amt = sum(u[1] for u in op.utxos if u[0] == pot)
        n = r.randint(5, 12)
        splits = [self.new_addr(op) for _ in range(n)]
        out = self.tx(t2, op, [(a, round(amt * 0.98 / n, 8)) for a in splits], "fan_out",
                      inputs=[u for u in op.utxos if u[0] == pot])
        if not out:
            return
        for a in splits:
            utxo = next((u for u in op.utxos if u[0] == a), None)
            if not utxo:
                continue
            if r.random() < 0.5:
                self.cj_queue.append((op, utxo, lambda tt, e, mixed, amt_: self.peel(tt, e, mixed, r.randint(1, 3))))
            else:
                self.at(t2 + self.minutes(20, 240), self.peel, op, a, r.randint(3, 6))

    def peel_start(self, t, pc):
        a = self.fund(t, pc, round(self.rng.uniform(3, 25), 3))
        if a:
            self.at(t + self.minutes(10, 90), self.peel, pc, a, self.rng.randint(5, 35))

    def hack(self, t, hk):
        r = self.rng
        hot_of = lambda x: [u for u in x.utxos if u[0] not in x.deposit_utxo_addrs]
        ex = max(self.exchanges, key=lambda x: sum(u[1] for u in hot_of(x)))   # attackers hit the fattest hot wallet
        hot = hot_of(ex)
        stolen_to = self.new_addr(hk)
        sel = self.select(ex, min(12.0, sum(u[1] for u in hot) * 0.8), hot)
        if not sel:
            return
        amt = round(min(sum(u[1] for u in sel) * 0.9, r.uniform(12, 40)), 6)
        if not self.tx(t, ex, [(stolen_to, amt)], "normal", inputs=sel, typology="HACK_LAUNDERING", illicit=True,
                       broadcaster=hk):
            return
        n = r.randint(8, 15)
        splits = [self.new_addr(hk) for _ in range(n)]
        t2 = t + self.minutes(5, 60)
        self.tx(t2, hk, [(a, round(amt * 0.97 / n, 8)) for a in splits], "fan_out",
                inputs=[u for u in hk.utxos if u[0] == stolen_to])
        hk.after_24h = t + timedelta(hours=24)
        for a in splits:
            self.at(t2 + timedelta(hours=r.uniform(0.5, 30)), self.peel, hk, a, r.randint(2, 4))

    def market_settle(self, t, mk):
        r = self.rng
        if len(mk.utxos) >= 2:
            escrow = self.new_addr(mk, "P2WSH")
            self.tx(t, mk, [(escrow, round(mk.balance() - 0.001, 8))], "fan_in", inputs=list(mk.utxos))
            amt = sum(u[1] for u in mk.utxos if u[0] == escrow)
            vend = r.sample(mk.vendors, r.randint(2, len(mk.vendors)))
            outs = [(self.new_addr(v), round(amt * 0.8 / len(vend), 8)) for v in vend]
            if self.tx(t + self.minutes(10, 120), mk, outs, "fan_out", inputs=[u for u in mk.utxos if u[0] == escrow]):
                for (a, _), v in zip(outs, vend):
                    self.at(t + timedelta(hours=r.uniform(4, 20)), self.cash_out, v, a)
        self.at(t + timedelta(hours=r.uniform(20, 28)), self.market_settle, mk)

    def smurf(self, t, sm):
        r = self.rng
        a = self.fund(t, sm, round(r.uniform(2, 6), 3))
        if not a:
            return
        amt = sum(u[1] for u in sm.utxos if u[0] == a)
        n = min(60, int(amt / 0.099))
        parts = [self.new_addr(sm) for _ in range(n)]
        t2 = t + self.minutes(20, 120)
        self.tx(t2, sm, [(p, round(r.uniform(0.0901, 0.0999), 6)) for p in parts], "fan_out",
                inputs=[u for u in sm.utxos if u[0] == a])
        for p in parts:
            self.at(t2 + timedelta(hours=r.uniform(0.5, 48)), self.cash_out, sm, p)

    def round_trip_start(self, t, rt):
        a = self.fund(t, rt, round(self.rng.uniform(0.5, 3), 3))
        if a:
            ring = [a, self.new_addr(rt), self.new_addr(rt)]
            self.at(t + self.minutes(20, 90), self.round_trip, rt, ring, 0, self.rng.randint(6, 15))

    def round_trip(self, t, rt, ring, i, left):
        src, dst = ring[i % 3], ring[(i + 1) % 3]
        utxos = [u for u in rt.utxos if u[0] == src]
        if not utxos:
            return
        if left <= 0:
            return self.cash_out(t, rt, src)
        amt = sum(u[1] for u in utxos)
        fee = self.fee(len(utxos), 1)
        if self.tx(t, rt, [(dst, round(amt - fee, 8))], "round_trip", inputs=utxos, fee_override=fee):
            self.at(t + self.minutes(15, 180), self.round_trip, rt, ring, i + 1, left - 1)

    def dusting(self, t, dz):
        r = self.rng
        a = self.fund(t, dz, 0.05)
        if not a:
            return
        for k in range(r.randint(2, 4)):
            victims = r.sample([u for u in self.retail if u.addresses], min(80, len(self.retail)))
            self.at(t + timedelta(hours=k * r.uniform(4, 12) + 0.5), self.dust_tx, dz, victims)

    def dust_tx(self, t, dz, victims):
        outs = [(self.rng.choice(v.addresses), DUST) for v in victims]
        self.tx(t, dz, outs, "fan_out")

    # ------------------------------------------------------------------ run + network layer
    def run(self, n_tx: int) -> None:
        self.build_legit(n_tx)
        self.build_illicit(n_tx)
        while self.events:
            t, _, fn, args = heapq.heappop(self.events)
            fn(t, *args)

    def broadcast_ip(self, e: Entity, t: datetime) -> str:
        if getattr(e, "after_24h", None) and t > e.after_24h:   # hacker switches to VPN hopping after a day
            return self.ip(self.rng.choice(["VPN", "TOR_EXIT"]))
        if e.hopping and e.ips:
            return self.rng.choice(e.ips)
        if not e.ips:
            e.ips = [self.ip("RESIDENTIAL")]
        return e.ips[0] if self.rng.random() < 0.9 else self.rng.choice(e.ips)

    def observations(self) -> List[dict]:
        """One row per (tx, relaying peer) as seen by our observer nodes."""
        r, rows = self.rng, []
        for tx in self.txs:
            e = self.entities[tx["entity"]]
            origin = self.broadcast_ip(e, tx["t"])
            missed = r.random() < (0.15 if e.illicit else 0.05)
            peers = [] if missed else [(origin, r.uniform(0.05, 0.8), e)]
            peers += [(r.choice(self.relays), r.uniform(0.9, 6.0), None) for _ in range(r.randint(1, 3))]
            for ip, delay, ent in peers:
                ephemeral = ent is not None and (not ent.typology in ("EXCHANGE", "MINER", "MERCHANT"))
                rows.append({**tx, "ts": tx["t"] + timedelta(seconds=delay), "src_ip": ip,
                             "src_port": r.randint(49152, 65535) if ephemeral else 8333,
                             "dst_ip": r.choice(self.observers), "dst_port": 8333})
        rows.sort(key=lambda x: x["ts"])
        return rows
