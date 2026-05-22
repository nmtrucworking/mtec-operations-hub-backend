@echo off
chcp 65001 >nul

REM ============================================================
REM MTEC Operations Hub Backend - Docs Scaffold Generator
REM Run this file inside: mtec-operations-hub-backend\docs
REM ============================================================

echo Creating backend documentation structure...

REM 00 - Handover
mkdir 00-handover 2>nul
type nul > 00-handover\handover-checklist.md
type nul > 00-handover\backend-project-overview.md
type nul > 00-handover\current-backend-status.md
type nul > 00-handover\known-issues.md
type nul > 00-handover\backend-roadmap.md

REM 01 - BA
mkdir 01-ba 2>nul
type nul > 01-ba\business-overview.md
type nul > 01-ba\stakeholder-and-roles.md
type nul > 01-ba\system-scope.md
type nul > 01-ba\business-rules.md
type nul > 01-ba\permission-matrix.md
type nul > 01-ba\use-cases.md
type nul > 01-ba\acceptance-criteria.md
type nul > 01-ba\uat-test-scenarios.md

REM 02 - Technical
mkdir 02-technical 2>nul
type nul > 02-technical\backend-setup.md
type nul > 02-technical\backend-architecture.md
type nul > 02-technical\environment-variables.md
type nul > 02-technical\authentication-authorization.md
type nul > 02-technical\rbac-policy.md
type nul > 02-technical\database-design.md
type nul > 02-technical\migration-guide.md
type nul > 02-technical\seed-data-guide.md
type nul > 02-technical\error-handling.md
type nul > 02-technical\logging-audit.md
type nul > 02-technical\testing-guide.md
type nul > 02-technical\deployment-guide.md
type nul > 02-technical\maintenance-guide.md

REM 03 - API
mkdir 03-api 2>nul
type nul > 03-api\api-overview.md
type nul > 03-api\auth-api.md
type nul > 03-api\dashboard-api.md
type nul > 03-api\members-api.md
type nul > 03-api\requests-api.md
type nul > 03-api\finance-api.md
type nul > 03-api\discipline-api.md
type nul > 03-api\meetings-attendance-api.md
type nul > 03-api\logistics-assets-api.md
type nul > 03-api\ai-generator-api.md
type nul > 03-api\settings-api.md
type nul > 03-api\logs-api.md
type nul > 03-api\evaluations-v2-api.md

REM 04 - Modules
mkdir 04-modules 2>nul
type nul > 04-modules\01-dashboard.md
type nul > 04-modules\02-members.md
type nul > 04-modules\03-requests.md
type nul > 04-modules\04-finance.md
type nul > 04-modules\05-discipline.md
type nul > 04-modules\06-meetings-attendance.md
type nul > 04-modules\07-logistics-assets.md
type nul > 04-modules\08-generator-ai.md
type nul > 04-modules\09-settings.md
type nul > 04-modules\10-logs-audit.md
type nul > 04-modules\11-evaluations-v2.md

REM 05 - Database
mkdir 05-database 2>nul
type nul > 05-database\database-overview.md
type nul > 05-database\table-dictionary.md
type nul > 05-database\entity-relationship.md
type nul > 05-database\data-flow.md
type nul > 05-database\soft-delete-policy.md

REM 06 - Operations
mkdir 06-operations 2>nul
type nul > 06-operations\runbook.md
type nul > 06-operations\backup-restore.md
type nul > 06-operations\monitoring.md
type nul > 06-operations\security-checklist.md
type nul > 06-operations\release-checklist.md

REM Templates
mkdir templates 2>nul
type nul > templates\module-template.md
type nul > templates\api-template.md
type nul > templates\test-case-template.md
type nul > templates\change-request-template.md

REM Root index
(
echo # MTEC Operations Hub Backend Documentation
echo.
echo ## 1. Handover
echo - 00-handover/handover-checklist.md
echo - 00-handover/backend-project-overview.md
echo - 00-handover/current-backend-status.md
echo - 00-handover/known-issues.md
echo - 00-handover/backend-roadmap.md
echo.
echo ## 2. Business Analysis
echo - 01-ba/business-overview.md
echo - 01-ba/stakeholder-and-roles.md
echo - 01-ba/system-scope.md
echo - 01-ba/business-rules.md
echo - 01-ba/permission-matrix.md
echo - 01-ba/use-cases.md
echo - 01-ba/acceptance-criteria.md
echo - 01-ba/uat-test-scenarios.md
echo.
echo ## 3. Technical Documents
echo - 02-technical/backend-setup.md
echo - 02-technical/backend-architecture.md
echo - 02-technical/environment-variables.md
echo - 02-technical/authentication-authorization.md
echo - 02-technical/rbac-policy.md
echo - 02-technical/database-design.md
echo - 02-technical/migration-guide.md
echo - 02-technical/seed-data-guide.md
echo - 02-technical/error-handling.md
echo - 02-technical/logging-audit.md
echo - 02-technical/testing-guide.md
echo - 02-technical/deployment-guide.md
echo - 02-technical/maintenance-guide.md
echo.
echo ## 4. API Documents
echo - 03-api/api-overview.md
echo - 03-api/auth-api.md
echo - 03-api/dashboard-api.md
echo - 03-api/members-api.md
echo - 03-api/requests-api.md
echo - 03-api/finance-api.md
echo - 03-api/discipline-api.md
echo - 03-api/meetings-attendance-api.md
echo - 03-api/logistics-assets-api.md
echo - 03-api/ai-generator-api.md
echo - 03-api/settings-api.md
echo - 03-api/logs-api.md
echo - 03-api/evaluations-v2-api.md
echo.
echo ## 5. Module Documents
echo - 04-modules/01-dashboard.md
echo - 04-modules/02-members.md
echo - 04-modules/03-requests.md
echo - 04-modules/04-finance.md
echo - 04-modules/05-discipline.md
echo - 04-modules/06-meetings-attendance.md
echo - 04-modules/07-logistics-assets.md
echo - 04-modules/08-generator-ai.md
echo - 04-modules/09-settings.md
echo - 04-modules/10-logs-audit.md
echo - 04-modules/11-evaluations-v2.md
echo.
echo ## 6. Database Documents
echo - 05-database/database-overview.md
echo - 05-database/table-dictionary.md
echo - 05-database/entity-relationship.md
echo - 05-database/data-flow.md
echo - 05-database/soft-delete-policy.md
echo.
echo ## 7. Operations
echo - 06-operations/runbook.md
echo - 06-operations/backup-restore.md
echo - 06-operations/monitoring.md
echo - 06-operations/security-checklist.md
echo - 06-operations/release-checklist.md
) > README.md

echo.
echo Done. Backend docs scaffold created successfully.
pause