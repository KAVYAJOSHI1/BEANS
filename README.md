# BEANS: Bitcoin Encryption, Analysis & Network Security

Offline, Linux-native AI system for monitoring and analysing Bitcoin transaction traffic (SIH PS **26146**, NTRO).
It ingests bulk CSV/JSON/XML transaction and network metadata, correlates IP/port/timing with wallets and TXIDs, and applies ML:
entity clustering, anomaly detection, peel-chain/mixing detection, and risk propagation from seed wallets.
The output is a ranked, explainable alert list with a link-analysis dashboard.

- Vision & architecture: [`MASTER_ROADMAP.md`](MASTER_ROADMAP.md) ([PDF](MASTER_ROADMAP.pdf))
- Team plan & branches: [`TEAM_PLAN.md`](TEAM_PLAN.md)
- Interfaces: [`docs/CONTRACTS.md`](docs/CONTRACTS.md)

## Quickstart
```bash
make install          # .venv + dependencies
make pipeline-tiny    # synthetic data → ingest → graph → ML → alerts
make serve            # http://127.0.0.1:8000
```

IP geolocation by [DB-IP](https://db-ip.com) (CC BY 4.0).
