# IMP escape-core identity registry

This manually adjudicated registry separates three claims that must not be conflated:
an allele or protein accession, a captured sequence payload, and a scientific relationship
between named variants.

Seven preferred versioned protein-accession payloads are stored verbatim in `sequences.fasta`.
IMP-59 remains accession-only because its authoritative payload was not supplied; it was not
reconstructed by editing IMP-4. Such reconstruction would fabricate sequence evidence.

The only authorised comparisons are full-length precursor IMP-1 versus IMP-6, IMP-1 versus
IMP-10, and IMP-4 versus IMP-26. Their one-based precursor coordinates remain separate from
paper-reported BBL labels. BBL numbering must not be interpreted as precursor numbering.

No signal-peptide coordinates were adjudicated, so no cleavage site or mature sequence is
generated. IMP-14 numbering, IMP-19 versus IMP-2, IMP-59 versus IMP-4, secondary accessions,
and all other comparisons remain outside this batch.
