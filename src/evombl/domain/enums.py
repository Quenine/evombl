from enum import StrEnum


class MBLFamily(StrEnum):
    IMP = "IMP"
    NDM = "NDM"
    VIM = "VIM"
    OTHER = "OTHER"


class AssayCategory(StrEnum):
    BIOCHEMICAL = "BIOCHEMICAL"
    MICROBIOLOGICAL = "MICROBIOLOGICAL"
    CELLULAR = "CELLULAR"
    ADME = "ADME"
    TOXICITY = "TOXICITY"
    SELECTIVITY = "SELECTIVITY"
    STRUCTURAL = "STRUCTURAL"


class EndpointType(StrEnum):
    IC50 = "IC50"
    KI = "Ki"
    KD = "Kd"
    PERCENT_INHIBITION = "percent inhibition"
    RESIDUAL_ACTIVITY = "residual enzyme activity"
    MIC = "MIC"
    MIC_FOLD_CHANGE = "MIC fold change"
    FIC = "fractional inhibitory concentration"
    TIME_KILL = "time-kill endpoint"
    CYTOTOXICITY = "cytotoxicity"
    SOLUBILITY = "solubility"
    PERMEABILITY = "permeability"
    METABOLIC_STABILITY = "metabolic stability"
    HUMAN_OFF_TARGET = "human off-target inhibition"


class MeasurementRelation(StrEnum):
    EQ = "="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    APPROX = "~"


class ExtractionMethod(StrEnum):
    MANUAL = "manual"
    TABLE = "table_extraction"
    FIGURE = "figure_digitisation"
    DATABASE = "database_import"
    COLLABORATOR = "collaborator_submission"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    IDENTITY_PENDING = "identity_pending_verification"
    SINGLE_CURATOR = "single_curator"
    DUAL_CURATOR = "dual_curator"
    SOURCE_VERIFIED = "source_verified"


class ExclusionStatus(StrEnum):
    INCLUDED = "included"
    FLAGGED = "flagged"
    EXCLUDED = "excluded"


class StereoStatus(StrEnum):
    UNSPECIFIED = "unspecified"
    PARTIAL = "partial"
    SPECIFIED = "specified"
    NOT_APPLICABLE = "not_applicable"


class CensoringStatus(StrEnum):
    NONE = "none"
    LEFT = "left"
    RIGHT = "right"
    INTERVAL = "interval"


class SourceType(StrEnum):
    LITERATURE = "literature"
    PATENT = "patent"
    DATABASE = "database"
    SUPPLEMENT = "supplement"
    COLLABORATOR = "collaborator"
    OTHER = "other"
