import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Generator, Tuple, Optional
from datetime import datetime
from beans.schema import CanonicalRecord
from beans.ingest.mapping import fingerprint, SCRIPT_TYPES, ColumnMapper
from beans.ingest.quarantine import QuarantineLogger

class StreamingXMLParser:
    """
    Memory-efficient XML streaming parser using iterparse for <tx> or <transaction> nodes.
    """

    def parse(self, file_path: Path) -> Generator[CanonicalRecord, None, Tuple[int, int]]:
        total = 0
        valid = 0
        self.total = self.valid = 0

        try:
            context = ET.iterparse(file_path, events=("end",))
            for event, elem in context:
                tag = elem.tag.lower()
                if tag in ["tx", "transaction", "record"]:
                    total += 1
                    self.total = total
                    try:
                        record = self._elem_to_record(elem)
                        if record:
                            valid += 1
                            self.valid = valid
                            yield record
                    except Exception as e:
                        QuarantineLogger.log_bad_row(ET.tostring(elem, encoding="unicode"), f"XML Parse Error: {str(e)}", str(file_path))
                    finally:
                        elem.clear() # Free memory
        except Exception as e:
            QuarantineLogger.log_bad_row(f"XML file format fatal error: {str(e)}", "INVALID_XML_STRUCTURE", str(file_path))

        return total, valid

    def _elem_to_record(self, elem: ET.Element) -> Optional[CanonicalRecord]:
        # Attributes or child elements
        txid = elem.attrib.get("txid") or (elem.findtext("txid") or "").strip()
        ts_str = elem.attrib.get("timestamp") or elem.findtext("timestamp") or ""
        if not txid or not ts_str:
            raise ValueError("missing txid or timestamp")
        ts = ColumnMapper._timestamp(ts_str)
        
        fee_str = elem.attrib.get("fee") or elem.findtext("fee") or "0.0"
        fee = float(fee_str)
        script_type = elem.attrib.get("script_type") or elem.findtext("script_type") or "P2WPKH"

        # Network info
        net_elem = elem.find("net")
        if net_elem is not None:
            src_ip = net_elem.attrib.get("src_ip")
            src_port = int(net_elem.attrib.get("src_port", 8333))
            dst_ip = net_elem.attrib.get("dst_ip")
            dst_port = int(net_elem.attrib.get("dst_port", 8333))
        else:
            src_ip = elem.findtext("src_ip")
            src_port = int(elem.findtext("src_port") or 8333)
            dst_ip = elem.findtext("dst_ip")
            dst_port = int(elem.findtext("dst_port") or 8333)

        # Inputs
        in_addrs = []
        in_amts = []
        inputs_parent = elem.find("inputs")
        if inputs_parent is not None:
            for in_node in inputs_parent.findall("in"):
                in_addrs.append(in_node.attrib.get("address", ""))
                in_amts.append(float(in_node.attrib.get("amount", 0.0)))
        else:
            for in_node in elem.findall("input"):
                in_addrs.append(in_node.findtext("address") or in_node.attrib.get("address", ""))
                in_amts.append(float(in_node.findtext("amount") or in_node.attrib.get("amount", 0.0)))

        # Outputs
        out_addrs = []
        out_amts = []
        outputs_parent = elem.find("outputs")
        if outputs_parent is not None:
            for out_node in outputs_parent.findall("out"):
                out_addrs.append(out_node.attrib.get("address", ""))
                out_amts.append(float(out_node.attrib.get("amount", 0.0)))
        else:
            for out_node in elem.findall("output"):
                out_addrs.append(out_node.findtext("address") or out_node.attrib.get("address", ""))
                out_amts.append(float(out_node.findtext("amount") or out_node.attrib.get("amount", 0.0)))

        if not src_ip:
            raise ValueError("missing src_ip")
        if script_type.upper() not in SCRIPT_TYPES:
            script_type = "UNKNOWN"
        return CanonicalRecord(
            timestamp=ts,
            src_ip=src_ip,
            src_port=src_port,
            dst_ip=dst_ip,
            dst_port=dst_port,
            txid=txid,
            input_addresses=in_addrs,
            input_amounts=in_amts,
            output_addresses=out_addrs,
            output_amounts=out_amts,
            fee=fee,
            script_type=script_type,
            **fingerprint({k: elem.attrib.get(k) or elem.findtext(k) for k in ("tx_version", "locktime", "rbf")}),
        )
