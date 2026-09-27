"""OFAC SDN import: Bitcoin addresses from the official XML become citable seeds."""
import duckdb

from beans.enrich import ofac

SDN = """<?xml version="1.0" standalone="yes"?>
<sdnList xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML">
  <publshInformation><Publish_Date>09/23/2026</Publish_Date><Record_Count>3</Record_Count></publshInformation>
  <sdnEntry><uid>1</uid><lastName>SHIPPING CO</lastName><sdnType>Entity</sdnType>
    <programList><program>IRAN</program></programList>
    <idList><id><uid>9</uid><idType>IMO Number</idType><idNumber>1234567</idNumber></id></idList></sdnEntry>
  <sdnEntry><uid>2</uid><firstName>Jane</firstName><lastName>DOE</lastName><sdnType>Individual</sdnType>
    <programList><program>CYBER2</program><program>DPRK3</program></programList>
    <idList>
      <id><uid>10</uid><idType>Digital Currency Address - XBT</idType><idNumber>bc1qsanctioned0000000000000000000000000000</idNumber></id>
      <id><uid>11</uid><idType>Digital Currency Address - ETH</idType><idNumber>0xabc</idNumber></id>
      <id><uid>12</uid><idType>Digital Currency Address - XBT</idType><idNumber>1Sanctioned111111111111111111111</idNumber></id>
    </idList></sdnEntry>
  <sdnEntry><uid>3</uid><lastName>EXCHANGE LLC</lastName><sdnType>Entity</sdnType>
    <programList><program>CYBER2</program></programList>
    <idList><id><uid>13</uid><idType>Digital Currency Address - XBT</idType><idNumber>1Sanctioned111111111111111111111</idNumber></id></idList></sdnEntry>
</sdnList>"""


def test_parse_and_load(tmp_path):
    f = tmp_path / "sdn.xml"
    f.write_text(SDN)
    p = ofac.parse(f)
    assert p["publish_date"] == "09/23/2026" and len(p["sha256"]) == 64
    assert [e["address"] for e in p["entries"]] == ["bc1qsanctioned0000000000000000000000000000",
                                                    "1Sanctioned111111111111111111111", "1Sanctioned111111111111111111111"]
    assert p["entries"][0]["name"] == "Jane DOE" and p["entries"][0]["programs"] == ["CYBER2", "DPRK3"]
    conn = duckdb.connect()
    conn.execute("CREATE TABLE seeds (address VARCHAR PRIMARY KEY, threat_type VARCHAR, incident_name VARCHAR, "
                 "confidence DOUBLE, source VARCHAR)")
    assert ofac.load_seeds(conn, p) == 2                     # the doubly listed address is one seed
    rows = conn.execute("SELECT address, threat_type, incident_name, source FROM seeds ORDER BY address").fetchall()
    assert rows[0][1] == "SANCTIONED" and "OFAC SDN #2: Jane DOE [CYBER2, DPRK3]" == rows[0][2]
    assert rows[0][3].startswith("OFAC SDN list 09/23/2026 (sha256 " + p["sha256"][:16])
