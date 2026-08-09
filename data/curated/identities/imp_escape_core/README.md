# IMP escape-core identity registry

This manually adjudicated registry keeps allele accessions, captured sequence payloads, and
scientific relationships separate. CAB94707.1/AJ243491 is the selected IMP-2 reference because
this partial pack links the original allele record with the curated protein payload.

IMP-2 to IMP-19 is independently reproduced as R21A in full-length precursor coordinates. This
does not contradict the paper-reported Arg38Ala, which is retained separately as a BBL label.
No general BBL mapping is inferred from that relationship.

WP_094009805.1 was manually captured directly from the NCBI protein record. Only whitespace and
header formatting were normalized; the sequence was not reconstructed from IMP-4. Direct sequence
comparison produced exactly N185Y. The paper's Asn233Tyr label remains a separate BBL coordinate,
and this single relationship does not define a universal coordinate offset. No signal-peptide
coordinates or mature sequences were generated.

`sources_imp2_imp19.csv` is a partial provenance pack covering only IMP-2 and IMP-19. The
`sources_imp59.csv` is a partial provenance pack for IMP-59; registry provenance remains incomplete
for the other escape-core variants. The authorised full-length precursor comparisons are
IMP-1/IMP-6, IMP-1/IMP-10, IMP-4/IMP-26, IMP-2/IMP-19, and IMP-4/IMP-59. No general BBL mapping is
inferred from these relationships.
