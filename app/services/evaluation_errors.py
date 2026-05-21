class EvaluationError(Exception):
    code = "EVALUATION_ERROR"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)


class EvaluationCycleLockedError(EvaluationError):
    code = "EVALUATION_CYCLE_LOCKED"


class EvaluationNotFoundError(EvaluationError):
    code = "EVALUATION_NOT_FOUND"


class EvaluationMissingCriteriaError(EvaluationError):
    code = "EVALUATION_MISSING_CRITERIA"


class EvaluationEvidenceError(EvaluationError):
    code = "EVALUATION_EVIDENCE_ERROR"


class EvaluationWeightError(EvaluationError):
    code = "EVALUATION_WEIGHT_ERROR"
