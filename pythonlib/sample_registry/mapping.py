"""Parse, create, and validate QIIME-style mapping files."""

import io
import string

NAs = set([
    "", "0000-00-00", "null", "Null", "NA", "na", "none", "None",
    ])


ALLOWED_CHARS = {
    "sample_name": set("._-" + string.ascii_letters + string.digits),
    "barcode_sequence": set("AGCT"),
    "primer_sequence": set("AGCTRYMKSWHBVDN"),
    }


SAMPLE_FIELDS = (
    "sample_name", "barcode_sequence")


QIIME_FIELDS = (
    ("SampleID", "sample_name"),
    ("BarcodeSequence", "barcode_sequence"),
    )


def create(f, samples):
    samples = list(samples)

    column_names = ["sample_name", "barcode_sequence"]
    for s in samples:
        for key in sorted(s.keys()):
            if key not in column_names:
                column_names.append(key)
    line = u"\t".join(column_names)
    f.write(line)
    f.write(u"\n")

    for s in samples:
        row = ["NA" for c in column_names]
        for key, val in s.items():
            idx = column_names.index(key)
            row[idx] = val
        f.write(u"\t".join(row))
        f.write(u"\n")


def create_qiime(run, samples, annotations):
    """Create a QIIME mapping file."""
    buff = io.StringIO()

    qiime_fields = [x for x, _ in QIIME_FIELDS]
    annotation_fields, annotation_rows = _cast(samples, annotations)

    # Header line
    fields = qiime_fields + annotation_fields + ["Description"]
    buff.write(u"#")
    buff.write(u"\t".join(fields))
    buff.write(u"\n")

    # Comments
    buff.write(u"#%s\n" % run.comment)
    buff.write(u"#Sequencing date: %s\n" % run.date)
    buff.write(u"#Region: %s\n" % run.region)
    buff.write(u"#Platform: %s\n" % run.platform)
    buff.write(u"#Bushman lab run accession: %s\n" % run.formatted_accession)

    # Values
    for s, annotation_row in zip(samples, annotation_rows):
        sample_row = [s.name, s.barcode, s.primer]
        vals = sample_row + annotation_row + [s.formatted_accession]
        buff.write(u"\t".join(vals))
        buff.write(u"\n")

    return buff.getvalue()


def _cast(samples, annotations):
    """Cast EAV tuples into rows of a QIIME mapping file.

    Annotations are matched to samples by accession number.  Annotations
    provided for a sample not in the samples list are ignored.  A value
    of NA is used when an annotation is not found for a sample.
    Annotations with a key of 'description' are ignored
    (case-insensitive match).
    """
    fields = []
    accessions = [s.accession for s in samples]
    rows = [[] for a in accessions]
    for sample_acc, field, val in annotations:
        # Ignore annotations not in samples list
        if sample_acc not in accessions:
            continue
        sample_idx = accessions.index(sample_acc)
        # Ignore description field (case-insensitive)
        if field.lower() in ["description"]:
            continue
        # Match to existing fields (case-sensitive)
        if field not in fields:
            fields.append(field)
            # Fill with NA when adding new fields
            for r in rows:
                r.append("NA")
        field_idx = fields.index(field)
        rows[sample_idx][field_idx] = val
    return fields, rows


def parse(f):
    """Parse mapping file, return each record as a dict."""
    header = next(f).lstrip("#")
    keys = _tokenize(header)
    assert(all(keys)) # No blank fields
    for line in f:
        if line.startswith("#"):
            continue
        if not line.strip():
            continue
        vals = _tokenize(line)
        yield dict([(k, v) for k, v in zip(keys, vals) if v not in NAs])


def _tokenize(line):
    """Tokenize a single line"""
    line = line.rstrip("\n\r")
    toks = line.split("\t")
    return [t.strip() for t in toks]


def convert_from_qiime(recs):
    """Convert records from a QIIME mapping file to registry format."""
    for r in recs:

        # Description column is often filled in with junk, and we
        # fill it in with new values when exporting.  Remove it if
        # present.
        if "Description" in r:
            del r["Description"]

        for qiime_field, core_field in QIIME_FIELDS:
            if core_field in r:
                raise ValueError(
                    "Trying to convert from QIIME format mapping, but core "
                    "field %s is already present and filled in.")
            qiime_val = r.pop(qiime_field, None)
            if qiime_val is not None:
                r[core_field] = qiime_val
        yield r


def validate(recs):
    """Ensure records are valid.

    Does not return a value, but raises an exception on an invalid record.
    """
    sample_names = set()
    barcodes = set()

    for r in recs:
        for key, char_set in ALLOWED_CHARS.items():
            if key in r:
                val = r[key]
                if not all(char in char_set for char in val):
                    raise ValueError("Illegal characters in %s: %s" % (key, r))

        name = r.get("sample_name")
        if name is None:
            raise ValueError("No sample_name: %s" % r)
        if name in sample_names:
            raise ValueError("Duplicate sample_name: %s" % r)
        sample_names.add(name)

        barcode = r.get("barcode_sequence", "")
        if barcode in barcodes:
            raise ValueError("Duplicate barcode: %s" % r)
        barcodes.add(barcode)


def split_annotations(recs):
    """Extract core sample info from records.

    Yields a tuple for each record.  First element contains core
    sample fields: (name, barcode).  Second element is a list
    of annotation key, value pairs: [(annot_key, annot_val), ...]
    """
    for r in recs:
        sample = tuple(r.get(f, "") for f in SAMPLE_FIELDS)
        annotation_keys = set(r.keys()) - set(SAMPLE_FIELDS)
        annotations = [(k, r[k]) for k in annotation_keys]
        yield sample, annotations
