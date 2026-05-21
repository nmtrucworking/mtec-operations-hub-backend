from datetime import date as dt_date
from datetime import datetime as dt_datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class EvaluationCycleCreate(BaseModel):
    code: str
    name: str
    type: str
    startDate: dt_date
    endDate: dt_date
    description: str | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "EvaluationCycleCreate":
        if self.startDate > self.endDate:
            raise ValueError("startDate must be before or equal to endDate")
        return self


class EvaluationCycleUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    startDate: dt_date | None = None
    endDate: dt_date | None = None
    description: str | None = None
    status: str | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "EvaluationCycleUpdate":
        if self.startDate and self.endDate and self.startDate > self.endDate:
            raise ValueError("startDate must be before or equal to endDate")
        return self


class EvaluationCriteriaCreate(BaseModel):
    code: str
    name: str
    component: str
    unitScope: str = "ALL"
    unitCode: str | None = None
    maxScore: float = Field(gt=0)
    scoreMethod: str
    requiresEvidence: bool = True
    sortOrder: int = 0
    effectiveFrom: dt_date | None = None
    effectiveTo: dt_date | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class EvaluationCriteriaUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    component: str | None = None
    unitScope: str | None = None
    unitCode: str | None = None
    maxScore: float | None = Field(default=None, gt=0)
    scoreMethod: str | None = None
    requiresEvidence: bool | None = None
    isActive: bool | None = None
    sortOrder: int | None = None
    effectiveFrom: dt_date | None = None
    effectiveTo: dt_date | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class EvaluationCriteriaStatusUpdate(BaseModel):
    isActive: bool


class EvaluationCriteriaSeedRequest(BaseModel):
    version: str = "2026"
    overwrite: bool = False
    effectiveFrom: dt_date | None = None


class MemberCycleRoleCreate(BaseModel):
    memberId: str
    unitCode: str
    roleType: str
    roleTitle: str | None = None
    participationWeight: float = Field(ge=0, le=1)
    isPrimary: bool = False
    note: str | None = None
    metadata: dict[str, Any] | None = None


class MemberCycleRoleUpdate(BaseModel):
    unitCode: str | None = None
    roleType: str | None = None
    roleTitle: str | None = None
    participationWeight: float | None = Field(default=None, ge=0, le=1)
    isPrimary: bool | None = None
    note: str | None = None
    metadata: dict[str, Any] | None = None


class EvaluationScoreEventCreate(BaseModel):
    memberId: str
    criterionId: str | None = None
    criterionCode: str
    unitCode: str | None = None
    eventType: str
    sourceType: str | None = None
    sourceId: str | None = None
    rawValue: float | None = None
    scoreDelta: float
    weight: float | None = None
    note: str | None = None
    metadata: dict[str, Any] | None = None


class EvaluationScoreEventVoidRequest(BaseModel):
    reason: str | None = None


class EvaluationEvidenceCreate(BaseModel):
    memberId: str
    criterionId: str | None = None
    criterionCode: str | None = None
    scoreEventId: str | None = None
    evidenceType: str
    title: str
    url: str | None = None
    filePath: str | None = None
    description: str | None = None
    capturedAt: dt_datetime | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_content(self) -> "EvaluationEvidenceCreate":
        if not (self.url or self.filePath or self.description):
            raise ValueError("At least one of url, filePath, or description is required")
        return self


class EvaluationEvidenceReviewRequest(BaseModel):
    note: str | None = None


class EvaluationComputeRequest(BaseModel):
    strict: bool = True
    evidenceMode: str = "approval"
    recomputeExisting: bool = True


class EvaluationOpenReviewRequest(BaseModel):
    reviewDeadline: dt_datetime | None = None
    note: str | None = None


class EvaluationAppealCreate(BaseModel):
    memberId: str
    memberEvaluationId: str | None = None
    criterionId: str | None = None
    criterionCode: str | None = None
    appealType: str
    content: str = Field(min_length=1)
    requestedScore: float | None = None
    evidenceIds: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class EvaluationAppealEvidenceRequest(BaseModel):
    note: str = Field(min_length=1)


class EvaluationAppealResolveRequest(BaseModel):
    decision: str
    resolutionNote: str = Field(min_length=1)
    adjustedScoreDelta: float | None = None
    targetCriterionCode: str | None = None
    createAdjustmentEvent: bool = False
    evidenceIds: list[str] = Field(default_factory=list)
    recomputeMember: bool = True

    @model_validator(mode="after")
    def validate_adjustment(self) -> "EvaluationAppealResolveRequest":
        if self.createAdjustmentEvent and (
            self.adjustedScoreDelta is None or not self.targetCriterionCode
        ):
            raise ValueError(
                "targetCriterionCode and adjustedScoreDelta are required for adjustment"
            )
        return self


class EvaluationAppealCancelRequest(BaseModel):
    reason: str | None = None


class EvaluationApproveCycleRequest(BaseModel):
    approvalNote: str | None = None
    lockAfterApprove: bool = False


class EvaluationReopenCorrectionRequest(BaseModel):
    reason: str = Field(min_length=1)
