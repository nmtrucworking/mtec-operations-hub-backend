from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    User,
    UserUnitPermission,
    MemberCycleRole,
    EvaluationEvidence,
    EvaluationAppeal,
    Member,
)


class EvaluationPermissionService:
    def __init__(self, db: Session):
        self.db = db

    def is_self_member(self, user: User, member: Member) -> bool:
        if not user or not member:
            return False
        # best-effort: match by username==mssv or email
        if user.has_role("member"):
            if getattr(member, "mssv", None) and user.username == member.mssv:
                return True
            if getattr(member, "email", None) and user.email and user.email == member.email:
                return True
        return False

    def _active_permissions_for_user(self, user: User) -> list[UserUnitPermission]:
        rows = self.db.scalars(
            select(UserUnitPermission).where(UserUnitPermission.user_id == user.id, UserUnitPermission.is_active == True)
        ).all()
        return rows

    def has_unit_permission(self, *, user: User, unit_code: str, permission_field: str) -> bool:
        if user is None:
            return False
        perms = self._active_permissions_for_user(user)
        for p in perms:
            if p.unit_code == unit_code and getattr(p, permission_field, False):
                now = datetime.utcnow()
                if (p.starts_at is None or p.starts_at <= now) and (p.ends_at is None or p.ends_at >= now):
                    return True
        return False

    def member_has_unit_role(self, *, cycle_id: str, member_id: str, unit_code: str) -> bool:
        row = self.db.scalar(
            select(MemberCycleRole).where(
                MemberCycleRole.cycle_id == cycle_id,
                MemberCycleRole.member_id == member_id,
                MemberCycleRole.unit_code == unit_code,
            )
        )
        return row is not None

    def can_read_member(self, *, user: User, cycle_id: str, member: Member, unit_code: Optional[str] = None) -> bool:
        # System-wide roles
        if user.has_any_roles(["bcn", "bvh_discipline", "bvh_hr", "bvh_operator"]):
            return True

        # member can read self
        if self.is_self_member(user, member):
            return True

        # bcm: restrict to unit permissions
        if user.has_role("bcm"):
            # collect member's units
            member_units = [r.unit_code for r in self.db.scalars(select(MemberCycleRole).where(MemberCycleRole.cycle_id == cycle_id, MemberCycleRole.member_id == member.id)).all()]
            target_units = [unit_code] if unit_code else member_units
            for u in target_units:
                if u and self.has_unit_permission(user=user, unit_code=u, permission_field="can_view_unit_results") and self.member_has_unit_role(cycle_id=cycle_id, member_id=member.id, unit_code=u):
                    return True
            return False

        return False

    def can_write_score_event(self, *, user: User, cycle_id: str, member_id: str, component: str, unit_code: Optional[str]) -> bool:
        # Component I: only bcn and bvh_discipline
        if component == "I":
            return user.has_any_roles(["bcn", "bvh_discipline"])

        # Component II
        if component == "II":
            if user.has_any_roles(["bcn", "bvh_discipline", "bvh_hr", "bvh_operator"]):
                return True
            if user.has_role("bcm") and unit_code:
                return self.has_unit_permission(user=user, unit_code=unit_code, permission_field="can_score_component_ii") and self.member_has_unit_role(cycle_id=cycle_id, member_id=member_id, unit_code=unit_code)
            return False

        # Component III_A
        if component == "III_A":
            if user.has_any_roles(["bcn", "bvh_operator"]):
                return True
            if user.has_role("bcm") and unit_code:
                return self.has_unit_permission(user=user, unit_code=unit_code, permission_field="can_score_component_iii_a") and self.member_has_unit_role(cycle_id=cycle_id, member_id=member_id, unit_code=unit_code)
            return False

        # Component III_B
        if component == "III_B":
            if user.has_any_roles(["bcn", "bvh_operator"]):
                return True
            if user.has_role("bcm") and unit_code:
                return (
                    self.has_unit_permission(user=user, unit_code=unit_code, permission_field="can_score_component_iii_b")
                    and self.member_has_unit_role(cycle_id=cycle_id, member_id=member_id, unit_code=unit_code)
                )
            return False

        # Fallback: deny
        return False

    def can_verify_evidence(self, *, user: User, evidence: EvaluationEvidence) -> bool:
        # submitter cannot verify own evidence
        if evidence.submitted_by_user_id and evidence.submitted_by_user_id == user.id:
            return False

        # BCH/ BVH roles can verify broadly
        if user.has_any_roles(["bcn", "bvh_discipline", "bvh_hr", "bvh_operator"]):
            return True

        # unit leads with permission
        if user.has_role("bcm") and evidence.cycle_id and evidence.member_id and evidence.criterion_id is not None:
            # determine member's unit(s) for this criterion/event - best-effort: check member cycle roles
            rows = self.db.scalars(select(MemberCycleRole).where(MemberCycleRole.cycle_id == evidence.cycle_id, MemberCycleRole.member_id == evidence.member_id)).all()
            for r in rows:
                if r.unit_code and self.has_unit_permission(user=user, unit_code=r.unit_code, permission_field="can_verify_evidence"):
                    return True
        return False

    def can_resolve_appeal(self, *, user: User, appeal: EvaluationAppeal) -> bool:
        # BCN and BVH roles handle appeals broadly
        if user.has_any_roles(["bcn", "bvh_discipline", "bvh_hr", "bvh_operator"]):
            return True

        # unit leads with review permission can participate in review (but may not be final resolver)
        if user.has_role("bcm") and appeal.cycle_id and appeal.member_id:
            rows = self.db.scalars(select(MemberCycleRole).where(MemberCycleRole.cycle_id == appeal.cycle_id, MemberCycleRole.member_id == appeal.member_id)).all()
            for r in rows:
                if r.unit_code and self.has_unit_permission(user=user, unit_code=r.unit_code, permission_field="can_review_appeal"):
                    return True
        return False
