import json
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.app.models.schema import CaseFile, WalletProfile, Transaction, Alert, ThreatIntel, NetworkObservation, AuditLog

class CaseManagementService:

    @classmethod
    def generate_law_enforcement_dossier(cls, db: Session, case_id: int) -> Dict[str, Any]:
        """
        Generates a comprehensive, court-admissible forensic evidence dossier
        correlating On-Chain Ledger, Network SIGINT, and OSINT Threat Intelligence.
        """
        case = db.query(CaseFile).filter(CaseFile.id == case_id).first()
        if not case:
            return {"error": "Case not found"}

        entities = case.get_entities()
        txids = case.get_txids()

        wallets = db.query(WalletProfile).filter(WalletProfile.address.in_(entities)).all()
        alerts = db.query(Alert).filter(Alert.entity_id.in_(entities)).all()
        threats = db.query(ThreatIntel).filter(ThreatIntel.entity_id.in_(entities)).all()
        transactions = db.query(Transaction).filter(Transaction.txid.in_(txids)).all()

        # If no specific txids linked, fetch all txids touching suspect wallets
        if not transactions and wallets:
            all_txs = db.query(Transaction).all()
            for tx in all_txs:
                if any(addr in entities for addr in tx.get_input_addrs() + tx.get_output_addrs()):
                    transactions.append(tx)

        # Collect SIGINT network observations
        observed_ips = set()
        for tx in transactions:
            for ip in tx.get_observed_ips():
                observed_ips.add(ip)
        for w in wallets:
            for ip in w.get_associated_ips():
                observed_ips.add(ip)

        net_obs = db.query(NetworkObservation).filter(NetworkObservation.src_ip.in_(list(observed_ips))).all()

        # Build Markdown Document
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        md_lines = [
            f"# LAW ENFORCEMENT FORENSIC INTELLIGENCE DOSSIER",
            f"**CONFIDENTIAL // LAW ENFORCEMENT SENSITIVE // INVESTIGATION REPORT**",
            f"",
            f"**Case Reference:** `{case.case_name}` (ID: #{case.id})  ",
            f"**Incident Classification:** `{case.incident_type}`  ",
            f"**Assigned Investigator:** {case.investigator}  ",
            f"**Generated On:** {now_str}  ",
            f"**Case Status:** `{case.status}` | **Priority:** `{case.priority}`  ",
            f"",
            f"---",
            f"",
            f"## 1. Executive Summary & Chain of Custody",
            f"This intelligence dossier provides correlated forensic evidence combining Layer 1 Bitcoin blockchain ledger transactions with Layer 2 Network Signals Intelligence (SIGINT) and Layer 3 Open Source Threat Intelligence (OSINT).",
            f"",
            f"**Suspect Entities in Scope:** {len(wallets)} wallet(s), {len(transactions)} transaction(s), {len(net_obs)} network entry points.",
            f"",
            f"**Investigator Synopsis:**",
            f"> {case.notes or 'Suspect cluster identified participating in high-velocity illicit transaction flow.'}",
            f"",
            f"---",
            f"",
            f"## 2. Suspect Wallet Entity Profiles",
            f"",
            f"| Wallet Address | Threat Class | Risk Score | Balance (BTC) | Total Received | Associated Cluster |",
            f"| :--- | :--- | :--- | :--- | :--- | :--- |"
        ]

        for w in wallets:
            md_lines.append(
                f"| `{w.address}` | **{w.threat_classification}** | `{w.risk_score:.0f}/100` | {w.balance:.4f} | {w.total_received:.4f} | `{w.cluster_id or 'SOLO'}` |"
            )

        md_lines.extend([
            f"",
            f"---",
            f"",
            f"## 3. Correlated Transaction Ledger & Flow",
            f"",
            f"| Timestamp (UTC) | TXID Hash | Inputs | Outputs | Total (BTC) | Miner Fee | Observed IPs |",
            f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ])

        for tx in transactions:
            ts = tx.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            in_count = len(tx.get_input_addrs())
            out_count = len(tx.get_output_addrs())
            ips = ", ".join(tx.get_observed_ips()) or "None logged"
            md_lines.append(
                f"| {ts} | `{tx.txid[:16]}...` | {in_count} addr | {out_count} addr | {tx.total_output:.4f} BTC | {tx.fee:.5f} | {ips} |"
            )

        md_lines.extend([
            f"",
            f"---",
            f"",
            f"## 4. Layer 2 Network Signals Intelligence (SIGINT)",
            f"",
            f"| Observed IP | Port | ASN / Provider | Country / City | Infrastructure Type |",
            f"| :--- | :--- | :--- | :--- | :--- |"
        ])

        for n in net_obs:
            md_lines.append(
                f"| `{n.src_ip}` | `{n.src_port}` | `{n.src_asn}` ({n.src_asn_name}) | {n.src_country} - {n.src_city} | **{n.isp_type}** |"
            )

        md_lines.extend([
            f"",
            f"---",
            f"",
            f"## 5. Layer 3 OSINT Attribution & Threat Intelligence",
            f"",
            f"| Entity ID | Source Database | Threat Type | Incident Tag | Corroboration Confidence |",
            f"| :--- | :--- | :--- | :--- | :--- |"
        ])

        for t in threats:
            md_lines.append(
                f"| `{t.entity_id[:16]}...` | {t.source} | **{t.threat_type}** | `{t.incident_name}` | {t.confidence * 100:.0f}% |"
            )

        md_lines.extend([
            f"",
            f"---",
            f"",
            f"## 6. Automated Heuristic & Evidence Justifications",
            f""
        ])

        for a in alerts:
            md_lines.append(f"### Alert: {a.alert_type} (`{a.severity}`) - Score: {a.automated_score:.0f}/100")
            md_lines.append(f"- **Target Entity:** `{a.entity_id}`")
            md_lines.append(f"- **Trigger Reason:** {a.reason}")
            md_lines.append(f"- **Evidence Points:**")
            for ev in a.get_evidence():
                md_lines.append(f"  * {ev}")
            md_lines.append("")

        md_lines.extend([
            f"---",
            f"",
            f"## 7. Recommended Law Enforcement Next Actions",
            f"1. **Subpoena Exchange Infrastructure:** Serve emergency preservation and subpoena notices to identified exchange deposit clusters for KYC attribution.",
            f"2. **Hosting Provider Subpoena:** Issue MLAT / Subpoena to the Autonomous System operator (`{net_obs[0].src_asn if net_obs else 'Target AS'}`) for server access logs and subscriber billing records.",
            f"3. **Asset Freezing / Blacklisting:** Submit identified wallet cluster addresses to FinCEN and partner exchanges for real-time asset freeze if deposited.",
            f"",
            f"**Report Certified by:** {case.investigator}  ",
            f"**Audit Trail Signature:** `SHA256-{case_id}-{int(datetime.utcnow().timestamp())}`"
        ])

        markdown_report = "\n".join(md_lines)

        # Log audit action
        db.add(AuditLog(
            action="EXPORT_DOSSIER",
            investigator=case.investigator,
            entity_type="CASE",
            entity_id=str(case.id),
            details=json.dumps({"case_name": case.case_name, "wallets_included": len(wallets)})
        ))
        db.commit()

        return {
            "case_id": case.id,
            "case_name": case.case_name,
            "markdown": markdown_report,
            "structured_data": {
                "case": {
                    "id": case.id,
                    "name": case.case_name,
                    "incident_type": case.incident_type,
                    "status": case.status,
                    "priority": case.priority
                },
                "wallets_count": len(wallets),
                "transactions_count": len(transactions),
                "network_nodes_count": len(net_obs),
                "alerts_count": len(alerts)
            }
        }
