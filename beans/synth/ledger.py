import hashlib
import random
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class UTXO:
    txid: str
    vout: int
    address: str
    amount: float
    script_type: str
    block_height: int

def generate_bitcoin_address(prefix: str = "bc1q", seed_str: str = "") -> str:
    """Generates realistic looking Bitcoin address based on script type prefix"""
    h = hashlib.sha256(f"{seed_str}_{random.random()}".encode()).hexdigest()
    if prefix == "bc1q": # SegWit v0 P2WPKH
        return f"bc1q{h[:38]}"
    elif prefix == "bc1p": # Taproot P2TR
        return f"bc1p{h[:58]}"
    elif prefix == "3": # P2SH / Multisig
        return f"3{h[:33]}"
    elif prefix == "1": # Legacy P2PKH
        return f"1{h[:33]}"
    return f"bc1q{h[:38]}"

def generate_txid() -> str:
    return hashlib.sha256(f"{random.random()}_{random.randint(1, 10000000)}".encode()).hexdigest()

class UTXOPool:
    """
    Simulates a stateful UTXO set to ensure synthetic transactions consume real historical outputs.
    """

    def __init__(self):
        self.unspent: Dict[str, UTXO] = {} # "txid:vout" -> UTXO
        self.address_utxos: Dict[str, List[str]] = {} # address -> list of "txid:vout"

    def add_utxo(self, utxo: UTXO):
        key = f"{utxo.txid}:{utxo.vout}"
        self.unspent[key] = utxo
        self.address_utxos.setdefault(utxo.address, []).append(key)

    def spend_utxo(self, key: str) -> UTXO:
        utxo = self.unspent.pop(key)
        self.address_utxos[utxo.address].remove(key)
        return utxo

    def get_utxos_for_address(self, address: str) -> List[UTXO]:
        keys = self.address_utxos.get(address, [])
        return [self.unspent[k] for k in keys if k in self.unspent]
