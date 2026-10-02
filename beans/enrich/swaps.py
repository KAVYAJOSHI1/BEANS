"""Swap memos: a THORChain-style swap names its destination in an OP_RETURN output of the Bitcoin transaction.

    =:ASSET:DESTINATION[:LIMIT[:AFFILIATE[:FEE]]]        (`SWAP:` and `s:` are older spellings of `=:`)

Unlike a swap service's deposit address, which needs an attribution list, the memo is on the chain: it states the chain
and asset the money is going to and the address that receives it. Maya Protocol uses the same grammar, so a match
says "a swap in this style", not which network. Whether the swap was ever completed is not visible from Bitcoin.

Nothing is guessed: a memo that does not fit the grammar returns None. Asset abbreviations are expanded only for the
short forms below; any other asset is returned as written.
"""
import re
from typing import Optional

SWAP_VERBS = {"=", "swap", "s"}
ABBREV = {"b": "BTC.BTC", "e": "ETH.ETH", "l": "LTC.LTC", "d": "DOGE.DOGE", "c": "BCH.BCH", "g": "GAIA.ATOM",
          "a": "AVAX.AVAX", "r": "THOR.RUNE"}
_PRINTABLE = re.compile(r"^[\x20-\x7e]{1,160}$")


def decode_memo(data: bytes) -> Optional[str]:
    """The text of an OP_RETURN payload when it is printable ASCII (memos are); None for binary payloads."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return None
    return text if _PRINTABLE.match(text) else None


def parse_memo(memo: Optional[str]) -> Optional[dict]:
    if not memo:
        return None
    parts = memo.strip().split(":")
    if len(parts) < 3 or parts[0].strip().lower() not in SWAP_VERBS:
        return None
    asset, dest = parts[1].strip(), parts[2].strip()
    if not asset or not dest or " " in dest:
        return None
    full = ABBREV.get(asset.lower(), asset) if len(asset) == 1 else asset
    chain = full.split(".")[0].upper() if "." in full else None
    return {"style": "THORChain-style swap memo", "asset": full, "destination_chain": chain, "destination_address": dest,
            "limit": parts[3] if len(parts) > 3 and parts[3] else None, "memo": memo.strip()[:160]}
