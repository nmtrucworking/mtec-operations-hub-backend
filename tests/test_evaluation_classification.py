from app.core.evaluation_constants import (
    BLOCKER_ATTENDANCE_UNDER_80,
    BLOCKER_INTERNAL_WARNING,
    BLOCKER_SEVERE_VIOLATION,
    BLOCKER_UNEXCUSED_ABSENCE,
    CLASSIFICATION_EXCELLENT,
    CLASSIFICATION_FAILED,
    CLASSIFICATION_GOOD,
    CLASSIFICATION_NEEDS_IMPROVEMENT,
    CLASSIFICATION_PASSED,
)
from app.services.evaluation_classification import ClassificationPolicyService


def test_preliminary_classification_thresholds():
    service = ClassificationPolicyService()

    assert service.classify_preliminary(90) == CLASSIFICATION_EXCELLENT
    assert service.classify_preliminary(89.99) == CLASSIFICATION_GOOD
    assert service.classify_preliminary(80) == CLASSIFICATION_GOOD
    assert service.classify_preliminary(79.99) == CLASSIFICATION_PASSED
    assert service.classify_preliminary(65) == CLASSIFICATION_PASSED
    assert service.classify_preliminary(64.99) == CLASSIFICATION_NEEDS_IMPROVEMENT
    assert service.classify_preliminary(50) == CLASSIFICATION_NEEDS_IMPROVEMENT
    assert service.classify_preliminary(49.99) == CLASSIFICATION_FAILED


def test_unexcused_absence_blocks_excellent():
    service = ClassificationPolicyService()

    final = service.apply_blockers(
        CLASSIFICATION_EXCELLENT, [{"code": BLOCKER_UNEXCUSED_ABSENCE}]
    )

    assert final == CLASSIFICATION_GOOD


def test_attendance_under_80_blocks_good_or_above():
    service = ClassificationPolicyService()
    blockers = service.collect_blockers(
        cycle_id="cycle-1", member_id="member-1", attendance_rate=0.79
    )

    final = service.apply_blockers(CLASSIFICATION_EXCELLENT, blockers)

    assert blockers[0]["code"] == BLOCKER_ATTENDANCE_UNDER_80
    assert final == CLASSIFICATION_PASSED


def test_internal_warning_blocks_to_needs_improvement():
    service = ClassificationPolicyService()

    final = service.apply_blockers(
        CLASSIFICATION_EXCELLENT, [{"code": BLOCKER_INTERNAL_WARNING}]
    )

    assert final == CLASSIFICATION_NEEDS_IMPROVEMENT


def test_severe_violation_blocks_to_failed():
    service = ClassificationPolicyService()

    final = service.apply_blockers(
        CLASSIFICATION_GOOD, [{"code": BLOCKER_SEVERE_VIOLATION}]
    )

    assert final == CLASSIFICATION_FAILED


def test_multiple_blockers_apply_lowest_cap():
    service = ClassificationPolicyService()

    final = service.apply_blockers(
        CLASSIFICATION_EXCELLENT,
        [
            {"code": BLOCKER_UNEXCUSED_ABSENCE},
            {"code": BLOCKER_SEVERE_VIOLATION},
        ],
    )

    assert final == CLASSIFICATION_FAILED
