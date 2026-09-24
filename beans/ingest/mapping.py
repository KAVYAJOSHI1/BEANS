import yaml
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_COLUMN_MAPPING = {
    "timestamp": ["timestamp", "time", "observed_at", "date", "ts"],
    "src_ip": ["src_ip", "source_ip", "ip_src", "client_ip", "relaying_ip"],
    "src_port": ["src_port", "source_port", "port_src", "sport"],
    "dst_ip": ["dst_ip", "destination_ip", "ip_dst", "server_ip", "peer_ip"],
    "dst_port": ["dst_port", "destination_port", "port_dst", "dport"],
    "txid": ["txid", "tx_hash", "hash", "transaction_id", "tx_id"],
    "input_addresses": ["input_addresses", "inputs", "vin_addresses", "in_addrs", "inputs_list"],
    "input_amounts": ["input_amounts", "vin_amounts", "in_amts", "in_amounts", "inputs_value"],
    "output_addresses": ["output_addresses", "outputs", "vout_addresses", "out_addrs", "outputs_list"],
    "output_amounts": ["output_amounts", "vout_amounts", "out_amts", "out_amounts", "outputs_value"],
    "fee": ["fee", "tx_fee", "miner_fee", "fees"],
    "script_type": ["script_type", "type", "script", "tx_type"]
}

class ColumnMapper:
    """
    Normalizes arbitrary input column names to CanonicalRecord field names.
    Supports custom mapping YAML files for unseen judge datasets.
    """

    def __init__(self, mapping_file: Optional[Path] = None):
        self.mapping = DEFAULT_COLUMN_MAPPING.copy()
        if mapping_file and Path(mapping_file).exists():
            with open(mapping_file, "r", encoding="utf-8") as f:
                user_map = yaml.safe_load(f)
                if isinstance(user_map, dict):
                    self.mapping.update(user_map)

    def normalize_row(self, raw_row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {}
        raw_keys_lower = {k.strip().lower(): v for k, v in raw_row.items()}

        for canonical_field, alias_list in self.mapping.items():
            for alias in alias_list:
                if alias.lower() in raw_keys_lower:
                    normalized[canonical_field] = raw_keys_lower[alias.lower()]
                    break
        return normalized
