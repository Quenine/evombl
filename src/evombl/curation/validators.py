from evombl.domain.assays import AssayRecord
from evombl.domain.measurements import MeasurementRecord


def validate_endpoint_alignment(assay: AssayRecord, measurement: MeasurementRecord) -> None:
    if assay.endpoint_type != measurement.endpoint_type:
        raise ValueError("measurement endpoint must match its assay endpoint")
