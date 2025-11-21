# Debug Information

## Quick Reference Guide
**Skill**: `Skill("workflow-docs-updater")`
**Format**: Concise item-based information recording

## Database
[workflow-docs-updater skill auto-populates]

## Service Information
[workflow-docs-updater skill auto-populates]

## API Information
[workflow-docs-updater skill auto-populates]

## Problem Solutions
**Problem**: Log timestamps displayed in UTC instead of user's local timezone (KST)
**Root Cause**: Backend parse_log_line() returned timestamps without timezone information
**Solution**: Modified log_reader.py to return ISO 8601 format with 'Z' suffix
**Implementation**: timestamp.replace(' ', 'T') + 'Z' converts '2025-11-13 14:08:29' to '2025-11-13T14:08:29Z'
**File**: web_server/app/utils/log_reader.py
**Function**: parse_log_line() at line 264

---
*This file is managed via workflow-docs-updater skill*