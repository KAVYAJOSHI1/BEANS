"""Column mapping + tolerant record building for input files we have never seen before.

A mapping YAML can use either form (or both):

    # their column → our field
    tx_hash: txid
    observed: timestamp
    peer_address: src_ip
    # or: our field → list of aliases
    output_addresses: [receivers, vout_addr]
    # options
    amount_unit: sat          # amounts given in satoshis (default: btc)

Accepted value shapes (so real exports work without pre-processing):
  * arrays as JSON lists, "a;b;c" or "a,b,c" strings
  * inputs/outputs as a list of objects: [{"address": "...", "value"|"amount": 0.1}, ...]
  * timestamps as ISO-8601 or Unix epoch seconds / milliseconds
Rows missing a required field (timestamp, txid, src_ip, outputs) are quarantined, never filled with fake values.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from beans.schema import CanonicalRecord

DEFAULT_COLUMN_MAPPING = {
    "timestamp": ["timestamp", "time", "observed_at", "date", "ts", "datetime", "seen_at", "first_seen"],
    "src_ip": ["src_ip", "source_ip", "ip_src", "client_ip", "relaying_ip", "peer_ip", "src", "ip"],
    "src_port": ["src_port", "source_port", "port_src", "sport"],
    "dst_ip": ["dst_ip", "destination_ip", "ip_dst", "server_ip", "observer_ip", "dst"],
    "dst_port": ["dst_port", "destination_port", "port_dst", "dport"],
    "txid": ["txid", "tx_hash", "hash", "transaction_id", "tx_id", "transaction_hash"],
    "input_addresses": ["input_addresses", "inputs", "vin_addresses", "in_addrs", "inputs_list", "senders", "from"],
    "input_amounts": ["input_amounts", "vin_amounts", "in_amts", "in_amounts", "inputs_value", "input_values"],
    "output_addresses": ["output_addresses", "outputs", "vout_addresses", "out_addrs", "outputs_list", "receivers", "to"],
    "output_amounts": ["output_amounts", "vout_amounts", "out_amts", "out_amounts", "outputs_value", "output_values"],
    "fee": ["fee", "tx_fee", "miner_fee", "fees"],
    "script_type": ["script_type", "type", "script", "tx_type", "address_type"],
}
SCRIPT_TYPES = {"P2PKH", "P2SH", "P2WPKH", "P2WSH", "P2TR"}
OPTION_KEYS = {"amount_unit"}


class ColumnMapper:
    def __init__(self, mapping_file: Optional[Path] = None):
        self.mapping = {k: list(v) for k, v in DEFAULT_COLUMN_MAPPING.items()}
        self.options: Dict[str, Any] = {"amount_unit": "btc"}
        if mapping_file and Path(mapping_file).exists():
            user = yaml.safe_load(Path(mapping_file).read_text()) or {}
            for k, v in user.items():
                if k in OPTION_KEYS:
                    self.options[k] = str(v).lower()
                elif isinstance(v, list):                        # our_field: [aliases]
                    self.mapping.setdefault(k, [])[:0] = [str(a) for a in v]
                elif isinstance(v, str) and v in self.mapping:  # their_column: our_field
                    self.mapping[v].insert(0, str(k))

    def normalize_row(self, raw_row: Dict[str, Any]) -> Dict[str, Any]:
        lower = {str(k).strip().lower(): v for k, v in raw_row.items()}
        out = {}
        for field, aliases in self.mapping.items():
            for alias in aliases:
                if alias.lower() in lower and lower[alias.lower()] not in (None, ""):
                    out[field] = lower[alias.lower()]
                    break
        return out

    # ------------------------------------------------------------------ value coercion
    def _scale(self, v: float) -> float:
        return v / 1e8 if self.options.get("amount_unit") in ("sat", "sats", "satoshi", "satoshis") else v

    @staticmethod
    def _list(val) -> list:
        if val is None or val == "":
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            s = val.strip()
            if s.startswith("["):
                try:
                    return json.loads(s)
                except ValueError:
                    pass
            return [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
        return [val]

    def _side(self, norm: dict, addr_key: str, amt_key: str) -> tuple[List[str], List[float]]:
        items = self._list(norm.get(addr_key))
        if items and all(isinstance(i, dict) for i in items):     # [{"address": ..., "value": ...}]
            addrs = [str(i.get("address") or i.get("addr") or i.get("wallet") or "") for i in items]
            amts = [float(i.get("value", i.get("amount", i.get("btc", 0.0)))) for i in items]
        else:
            addrs = [str(a) for a in items]
            amts = [float(a) for a in self._list(norm.get(amt_key))]
        return addrs, [self._scale(a) for a in amts]

    @staticmethod
    def _timestamp(v) -> datetime:
        if isinstance(v, datetime):
            return v
        s = str(v).strip()
        if s.replace(".", "", 1).isdigit():                         # epoch seconds or milliseconds
            x = float(s)
            return datetime.fromtimestamp(x / 1000 if x > 1e11 else x, tz=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    def build_record(self, raw_row: Dict[str, Any]) -> CanonicalRecord:
        """Raises ValueError with a clear reason when a required field is missing or malformed."""
        n = self.normalize_row(raw_row)
        missing = [f for f in ("timestamp", "txid", "src_ip", "output_addresses") if f not in n]
        if missing:
            raise ValueError(f"missing required field(s): {', '.join(missing)}")
        ins, in_amts = self._side(n, "input_addresses", "input_amounts")
        outs, out_amts = self._side(n, "output_addresses", "output_amounts")
        fee = n.get("fee")
        fee = self._scale(float(fee)) if fee not in (None, "") else max(0.0, round(sum(in_amts) - sum(out_amts), 8))
        script = str(n.get("script_type", "UNKNOWN")).upper()
        return CanonicalRecord(
            timestamp=self._timestamp(n["timestamp"]), txid=str(n["txid"]).strip(),
            src_ip=str(n["src_ip"]).strip(), src_port=int(float(n.get("src_port", 8333))),
            dst_ip=str(n["dst_ip"]).strip() if n.get("dst_ip") else None, dst_port=int(float(n.get("dst_port", 8333))),
            input_addresses=ins, input_amounts=in_amts, output_addresses=outs, output_amounts=out_amts,
            fee=fee, script_type=script if script in SCRIPT_TYPES else "UNKNOWN",
        )
