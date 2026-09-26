"""RFC 3161 timestamp tokens from a local, offline Time-Stamping Authority (OpenSSL `ts`).

The first call creates `data/tsa/`: a local root CA and a TSA certificate signed by it (extendedKeyUsage =
timeStamping, critical). Each evidence digest is then stamped into a DER TimeStampResp that anyone can check
with `openssl ts -verify -digest <sha256> -in token.tsr -CAfile tsa_ca.pem -untrusted tsa.pem`.

A self-run TSA proves "this exact content existed no later than this time, according to this machine's
clock and key". It carries less weight than a public, accredited TSA. Keep the key off shared drives and
record the CA certificate fingerprint in the case diary.
"""
import base64
import hashlib
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from beans.config import settings

_lock = threading.Lock()

_CNF = """\
[ req ]
distinguished_name = dn
prompt = no
[ dn ]
CN = {cn}
O = BEANS offline forensic workstation
[ v3_ca ]
basicConstraints = critical, CA:true
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
[ v3_tsa ]
basicConstraints = critical, CA:false
keyUsage = critical, digitalSignature, nonRepudiation
extendedKeyUsage = critical, timeStamping
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
[ tsa ]
default_tsa = tsa_config
[ tsa_config ]
dir = {dir}
serial = $dir/serial
crypto_device = builtin
signer_cert = $dir/tsa.pem
certs = $dir/tsa_ca.pem
signer_key = $dir/tsa.key
signer_digest = sha256
default_policy = 1.3.6.1.4.1.99999.1.1
digests = sha256, sha384, sha512
accuracy = secs:1
ordering = yes
tsa_name = yes
ess_cert_id_chain = yes
ess_cert_id_alg = sha256
"""


def tsa_dir() -> Path:
    return settings.DATA_DIR / "tsa"


def _run(args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, timeout=30, **kw)


def _ensure_tsa() -> Path:
    d = tsa_dir()
    if (d / "tsa.pem").exists() and (d / "tsa.key").exists():
        return d
    d.mkdir(parents=True, exist_ok=True)
    (d / "openssl.cnf").write_text(_CNF.format(dir=d, cn="BEANS Local TSA"))
    ca_cnf = d / "ca.cnf"
    ca_cnf.write_text(_CNF.format(dir=d, cn="BEANS Local Evidence Root CA"))
    _run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "3650", "-keyout", str(d / "tsa_ca.key"),
          "-out", str(d / "tsa_ca.pem"), "-config", str(ca_cnf), "-extensions", "v3_ca"])
    _run(["openssl", "req", "-new", "-newkey", "rsa:3072", "-nodes", "-keyout", str(d / "tsa.key"),
          "-out", str(d / "tsa.csr"), "-config", str(d / "openssl.cnf")])
    _run(["openssl", "x509", "-req", "-in", str(d / "tsa.csr"), "-CA", str(d / "tsa_ca.pem"), "-CAkey",
          str(d / "tsa_ca.key"), "-CAcreateserial", "-days", "1825", "-out", str(d / "tsa.pem"),
          "-extfile", str(d / "openssl.cnf"), "-extensions", "v3_tsa"])
    (d / "serial").write_text("01\n")
    for k in ("tsa.key", "tsa_ca.key"):
        (d / k).chmod(0o600)
    return d


def available() -> bool:
    return shutil.which("openssl") is not None


def ca_fingerprint() -> Optional[str]:
    try:
        out = _run(["openssl", "x509", "-in", str(tsa_dir() / "tsa_ca.pem"), "-noout", "-fingerprint", "-sha256"]).stdout.decode()
        return out.strip().split("=", 1)[1]
    except Exception:
        return None


def stamp(sha256_hex: str) -> Dict[str, Any]:
    """Timestamp a SHA-256 digest. Never raises: returns {"status": "unavailable", ...} when OpenSSL is missing."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha256_hex or ""):
        raise ValueError("stamp() expects a lowercase hex SHA-256 digest")
    if not available():
        return {"status": "unavailable", "reason": "openssl binary not found; evidence is hashed but not timestamped"}
    try:
        with _lock:
            d = _ensure_tsa()
            with tempfile.TemporaryDirectory() as tmp:
                q, r = Path(tmp) / "req.tsq", Path(tmp) / "resp.tsr"
                _run(["openssl", "ts", "-query", "-digest", sha256_hex, "-sha256", "-cert", "-out", str(q)])
                _run(["openssl", "ts", "-reply", "-config", str(d / "openssl.cnf"), "-queryfile", str(q), "-out", str(r)])
                token = r.read_bytes()
                text = _run(["openssl", "ts", "-reply", "-in", str(r), "-text"]).stdout.decode()
    except (subprocess.SubprocessError, OSError) as e:
        err = getattr(e, "stderr", b"") or b""
        return {"status": "error", "reason": f"{e} {err.decode(errors='ignore')[:300]}".strip()}
    field = lambda name: (re.search(rf"{name}:\s*(.+)", text) or [None, None])[1]
    return {
        "status": "stamped", "standard": "RFC 3161", "hash_algorithm": "sha256", "message_imprint": sha256_hex,
        "gen_time": field("Time stamp"), "serial": field("Serial number"), "policy_oid": field("Policy OID"),
        "tsa": "BEANS Local TSA (self-run, offline)", "tsa_ca_sha256_fingerprint": ca_fingerprint(),
        "token_sha256": hashlib.sha256(token).hexdigest(), "token_der_b64": base64.b64encode(token).decode(),
        "verify": f"openssl ts -verify -digest {sha256_hex} -in token.tsr -CAfile tsa_ca.pem -untrusted tsa.pem",
    }


def verify(sha256_hex: str, token_der_b64: str) -> bool:
    d = tsa_dir()
    with tempfile.TemporaryDirectory() as tmp:
        r = Path(tmp) / "token.tsr"
        r.write_bytes(base64.b64decode(token_der_b64))
        try:
            _run(["openssl", "ts", "-verify", "-digest", sha256_hex, "-in", str(r), "-CAfile", str(d / "tsa_ca.pem"),
                  "-untrusted", str(d / "tsa.pem")])
            return True
        except subprocess.CalledProcessError:
            return False
