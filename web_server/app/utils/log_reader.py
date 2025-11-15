# @FEAT:log-reading-helpers @FEAT:timezone-kst-display @COMP:util @TYPE:core
"""
Log reading and parsing utilities.

This module provides reusable helpers for reading and parsing application logs
with UTF-8 safety, security validation, and structured parsing.

Used by:
  - admin.get_job_logs()
  - admin.get_errors_warnings_logs()

Key Features:
  - Path traversal protection (security-critical)
  - UTF-8 safe binary mode reading with fallback
  - Large file optimization (200KB tail reading)
  - Structured log parsing with regex pattern
  - Exception-based error handling
"""
import os
import re
from typing import Optional, List
from flask import Flask
from datetime import datetime, timezone, timedelta

# Shared log pattern constant
# Format: YYYY-MM-DD HH:MM:SS,milliseconds LEVEL: [TAG] message [in file.py:123]
# Example: 2025-11-13 14:08:29,055 INFO: [QUEUE_REBAL] Processing completed [in queue_rebalancer.py:123]
# Note: CRITICAL - Do NOT add re.VERBOSE flag!
#       re.VERBOSE causes literal spaces in pattern to be ignored, breaking the match.
LOG_PATTERN = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ '  # Group 1: timestamp
    r'(\w+): '                                      # Group 2: level
    r'(?:\[([A-Z_]+)\] )?'                         # Group 3: tag (optional)
    r'(.+?) '                                       # Group 4: message
    r'\[in (.+?):(\d+)\]'                          # Groups 5,6: file, line
)


def validate_log_file_path(log_path: str, app: Flask) -> str:
    """
    Validate log file path with security checks.

    This function ensures the log file path is valid, accessible, and doesn't
    escape the intended logs directory (path traversal prevention).

    Args:
        log_path: Path to log file (relative or absolute from Flask config)
        app: Flask application instance

    Returns:
        str: Validated absolute log file path

    Raises:
        ValueError: LOG_FILE configuration is missing or empty
        PermissionError: Path traversal attempt detected (security violation)
        FileNotFoundError: Log file does not exist

    Security:
        - Validates path is within allowed logs directory relative to app root
        - Prevents path traversal attacks (../ sequences)
        - Uses absolute path comparison
        - Logs security violations

    Example:
        >>> from flask import Flask
        >>> app = Flask(__name__)
        >>> log_path = validate_log_file_path('logs/app.log', app)
        >>> # Returns: '/path/to/project/logs/app.log'

        >>> try:
        ...     validate_log_file_path('../../../etc/passwd', app)
        ... except PermissionError:
        ...     print("Path traversal blocked")
    """
    # Configuration validation
    if not log_path:
        raise ValueError('LOG_FILE configuration is missing or empty')

    # Convert to absolute path
    log_path = os.path.abspath(log_path)

    # Define allowed log directory
    allowed_log_dir = os.path.abspath(os.path.join(app.root_path, '..', 'logs'))

    # Security check: Path traversal prevention
    if not log_path.startswith(allowed_log_dir):
        app.logger.error(f'Security: Unauthorized log path access attempt: {log_path}')
        raise PermissionError(
            f'Log path must be within {allowed_log_dir}, got {log_path}'
        )

    # File existence check
    if not os.path.exists(log_path):
        raise FileNotFoundError(f'Log file not found: {log_path}')

    return log_path


def read_log_tail_utf8_safe(
    log_path: str, read_size: int = 204800
) -> List[str]:
    """
    Read last N lines from log file with UTF-8 safety.

    This function implements a UTF-8 safe binary reading strategy with
    optimization for large files (200KB tail reading) and fallback to full
    file reading on parsing errors.

    UTF-8 Safety Algorithm:
        1. Open file in binary mode (prevents UnicodeDecodeError on corrupt data)
        2. Read last N bytes (optimization: 200KB for typical use case)
        3. Find line boundaries in binary data (handles incomplete lines)
        4. Decode with errors='replace' (safe substitution for invalid UTF-8)

    Args:
        log_path: Absolute path to log file (validated by validate_log_file_path)
        read_size: Chunk size to read from end in bytes (default: 200KB = 204800)

    Returns:
        List[str]: All log lines in order (oldest first to newest last)

    Raises:
        OSError: File read permission error, I/O error, or other OS-level issues

    Performance:
        - For files < 200KB: Reads entire file in one pass
        - For files > 200KB: Reads last 200KB chunk only (optimization)
        - Fallback: If chunk parsing fails (IOError/OSError), reads full file
        - Typical: 50-100 log lines per 10KB of log data

    Algorithm Details:
        Binary Mode Read:
            - Prevents Python from trying UTF-8 decoding mid-read
            - Allows safe error handling with errors='replace'

        Line Boundary Detection:
            - If starting mid-file, finds first newline (\\n in binary)
            - Skips incomplete first line to ensure valid log entries
            - Preserves line endings during split for reconstruction

        Fallback Strategy:
            - If chunk read fails (IOError/UnicodeDecodeError), restart from beginning
            - Ensures all logs are accessible even with partial file corruption

    Example:
        >>> lines = read_log_tail_utf8_safe('/path/to/app.log')
        >>> # Returns: ['2025-11-13 10:00:00,000 INFO: ...',
        ...            '2025-11-13 10:05:00,000 ERROR: ...']
        >>> # Note: Limit filtering is applied by caller (e.g., lines[-100:])

        >>> # Safe handling of corrupted UTF-8:
        >>> lines = read_log_tail_utf8_safe('/path/to/corrupted.log')
        >>> # Returns: [..., '2025-11-13 14:08:29,055 WARNING: ...']
        >>> # Invalid UTF-8 bytes replaced with U+FFFD (replacement character)
    """
    try:
        # Open in binary mode (UTF-8 safety)
        with open(log_path, 'rb') as f:
            try:
                # Move to end of file
                f.seek(0, 2)
                file_size = f.tell()

                # Optimize for large files: read last 200KB
                # Typical log line ~200 bytes, so 200KB = ~1000 lines
                read_size = min(file_size, read_size)
                start_pos = max(0, file_size - read_size)
                f.seek(start_pos)

                # Line boundary detection (multibyte-safe)
                if start_pos > 0:
                    # Reading from middle of file - find first complete line
                    # Read up to 1KB to find next newline
                    chunk = f.read(1024)
                    newline_pos = chunk.find(b'\n')

                    if newline_pos != -1:
                        # Found newline - move to start of next complete line
                        f.seek(start_pos + newline_pos + 1)
                    else:
                        # No newline found in chunk - fall back to start of file
                        f.seek(0)

                # Safe UTF-8 decoding
                raw_bytes = f.read()
                content = raw_bytes.decode('utf-8', errors='replace')
                lines = content.splitlines(keepends=True)

            except (IOError, OSError, UnicodeDecodeError) as e:
                # Fallback: Read entire file if chunk read fails
                # This ensures we can always get logs even with partial corruption
                f.seek(0)
                raw_bytes = f.read()
                content = raw_bytes.decode('utf-8', errors='replace')
                lines = content.splitlines(keepends=True)

    except OSError as e:
        raise OSError(f'Failed to read log file {log_path}: {str(e)}')

    return lines


def parse_log_line(line: str) -> Optional[dict]:
    """
    Parse structured log line into dictionary with timezone metadata.

    Extracts timestamp, level, tag, message, file, and line number from
    a log entry formatted according to the app's logging configuration.
    Enhanced for Phase 1 timezone awareness with backward compatibility.

    Expected log format (from app/__init__.py line 169):
        %(asctime)s %(levelname)s: [TAG] %(message)s [in %(pathname)s:%(lineno)d]

    Log Format Example:
        2025-11-13 14:08:29,055 INFO: [QUEUE_REBAL] Rebalancing completed [in queue_rebalancer.py:123]

    Args:
        line: Single log line to parse (typically from read_log_tail_utf8_safe output)

    Returns:
        dict | None: Parsed log entry or None if line doesn't match pattern

        Parsed dict structure (Phase 1 Enhanced):
        {
            'timestamp': str           # "2025-11-13T14:08:29Z" (ISO 8601 UTC format, without milliseconds)
            'timestamp_kst': str       # "2025-11-13T23:08:29+09:00" (ISO 8601 KST format)
            'level': str              # "INFO" | "ERROR" | "WARNING" | "DEBUG" | etc.
            'tag': str | None         # "QUEUE_REBAL" (None if no [TAG] in log)
            'message': str            # Log message content (stripped)
            'file': str               # Filename only, e.g., "queue_rebalancer.py"
            'line': int               # Line number where log was called
            'timezone': str           # "UTC" (timezone identifier for frontend conversion)
            'timezone_offset': str    # "+00:00" (UTC offset for display)
        }

        Backward Compatibility:
            - All existing fields preserved
            - New timezone fields added without breaking existing API consumers
            - ISO 8601 timestamp format maintained

    Behavior on Unmatched Lines:
        - Returns None (non-exceptional flow)
        - Calling code can decide whether to include/skip these lines
        - Useful for fallback handling of malformed logs

    Examples:
        >>> line1 = '2025-11-13 10:00:00,000 ERROR: [ORDER] Failed [in order.py:123]'
        >>> result1 = parse_log_line(line1)
        >>> result1
        {'timestamp': '2025-11-13T10:00:00Z', 'timestamp_kst': '2025-11-13T19:00:00+09:00',
         'level': 'ERROR', 'tag': 'ORDER', 'message': 'Failed', 'file': 'order.py', 'line': 123,
         'timezone': 'UTC', 'timezone_offset': '+00:00'}

        >>> line2 = '2025-11-13 10:05:00,100 INFO: Background task running [in app.py:456]'
        >>> result2 = parse_log_line(line2)
        >>> result2
        {'timestamp': '2025-11-13T10:05:00Z', 'timestamp_kst': '2025-11-13T19:05:00+09:00',
         'level': 'INFO', 'tag': None, 'message': 'Background task running', 'file': 'app.py', 'line': 456,
         'timezone': 'UTC', 'timezone_offset': '+00:00'}

        >>> invalid_line = 'This is not a log line'
        >>> result3 = parse_log_line(invalid_line)
        >>> result3  # Returns None - no exception raised
        None
    """
    match = LOG_PATTERN.match(line.strip())

    if not match:
        return None

    timestamp, log_level, tag, message, file_path, line_num = match.groups()

    # Extract filename from full path
    file_name = os.path.basename(file_path)

    try:
        # Parse timestamp using timezone-aware datetime objects
        # Input format: 'YYYY-MM-DD HH:MM:SS'
        utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )

        # Convert to KST (UTC+9)
        kst_timezone = timezone(timedelta(hours=9))
        kst_time = utc_time.astimezone(kst_timezone)

        # Format timestamps as ISO 8601
        timestamp_utc = utc_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Format KST timestamp with proper offset (e.g., "+09:00")
        kst_offset = kst_time.strftime("%z")
        kst_offset_formatted = f"{kst_offset[:3]}:{kst_offset[3:]}"
        timestamp_kst = kst_time.strftime("%Y-%m-%dT%H:%M:%S") + kst_offset_formatted

    except ValueError as e:
        # Fallback to string manipulation if datetime parsing fails
        # This maintains backward compatibility for malformed timestamps
        timestamp_utc = timestamp.replace(' ', 'T') + 'Z'
        timestamp_kst = timestamp_utc  # Fallback: same as UTC
        kst_offset_formatted = "+00:00"  # Fallback: UTC offset

    # Phase 1 Enhancement: Add timezone metadata for frontend conversion
    # Log timestamps are in UTC by default, enabling KST conversion in frontend
    return {
        'timestamp': timestamp_utc,
        'timestamp_kst': timestamp_kst,  # Phase 1: KST timestamp for direct display
        'level': log_level,
        'tag': tag,  # None if no [TAG] in log
        'message': message.strip(),
        'file': file_name,
        'line': int(line_num),
        'timezone': 'UTC',           # Timezone identifier for frontend timezone.js
        'timezone_offset': '+00:00'   # UTC offset for display (Phase 1: always UTC)
    }
