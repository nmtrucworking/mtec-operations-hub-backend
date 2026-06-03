class EvaluationError(Exception):
    code = "EVALUATION_ERROR"

    def __init__(self, message: str | None = None, *, details: dict | None = None):
        super().__init__(message or self.code)
        self.details = details


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


class EvaluationInvalidStatusTransitionError(EvaluationError):
    code = "EVALUATION_INVALID_STATUS_TRANSITION"


class EvaluationReviewWindowClosedError(EvaluationError):
    code = "EVALUATION_REVIEW_WINDOW_CLOSED"


class EvaluationAppealNotFoundError(EvaluationError):
    code = "EVALUATION_APPEAL_NOT_FOUND"


class EvaluationAppealAlreadyResolvedError(EvaluationError):
    code = "EVALUATION_APPEAL_ALREADY_RESOLVED"


class EvaluationNotReadyForApprovalError(EvaluationError):
    code = "EVALUATION_NOT_READY_FOR_APPROVAL"


class EvaluationOpenAppealsExistError(EvaluationError):
    code = "EVALUATION_OPEN_APPEALS_EXIST"


class EvaluationCycleAlreadyApprovedError(EvaluationError):
    code = "EVALUATION_CYCLE_ALREADY_APPROVED"


class EvaluationCorrectionNotAllowedError(EvaluationError):
    code = "EVALUATION_CORRECTION_NOT_ALLOWED"


class EvaluationAppealPermissionDeniedError(EvaluationError):
    code = "EVALUATION_APPEAL_PERMISSION_DENIED"


class EvaluationValidationError(EvaluationError):
    code = "EVALUATION_VALIDATION_ERROR"

