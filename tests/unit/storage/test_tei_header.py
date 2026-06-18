from __future__ import annotations

from paperos.storage.document.tei_header import parse_tei_header_metadata


def test_parse_tei_header_metadata_reads_authors_year_doi_and_venue():
    tei = """\
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <author>Fallback Author</author>
      </titleStmt>
      <sourceDesc>
        <biblStruct>
          <analytic>
            <author><persName><forename>Ada</forename><surname>Lovelace</surname></persName></author>
            <author><persName><forename>Alan</forename><surname>Turing</surname></persName></author>
          </analytic>
          <monogr>
            <title>Conference on Machines</title>
            <imprint><date when="2024-05-01"/></imprint>
          </monogr>
          <idno type="DOI">10.1234/example</idno>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
</TEI>
"""

    header = parse_tei_header_metadata(tei)

    assert header.authors == ["Ada Lovelace", "Alan Turing", "Fallback Author"]
    assert header.year == 2024
    assert header.doi == "10.1234/example"
    assert header.venue == "Conference on Machines"
