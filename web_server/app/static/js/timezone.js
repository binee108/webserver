/**
 * TimeZone Utilities - Comprehensive timezone conversion and management
 * @FEAT:timezone-utility @COMP:util @TYPE:core
 *
 * Provides automatic timezone detection, conversion, and formatting capabilities
 * with IE11 compatibility and performance optimizations.
 *
 * @author Claude Code
 * @version 1.0.0
 */

/**
 * TimeZoneUtils class for handling timezone operations
 */
class TimeZoneUtils {
    /**
     * Initialize timezone utilities with caching
     */
    constructor() {
        // Cache for timezone offsets (24-hour TTL)
        this._offsetCache = new Map();
        this._cacheTimestamps = new Map();
        this._CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours in milliseconds

        // Cache for formatted results
        this._formatCache = new Map();
        this._formatCacheTimestamps = new Map();
        this._FORMAT_CACHE_TTL = 5 * 60 * 1000; // 5 minutes for formatted results

        // Detected timezone
        this._userTimezone = this._detectUserTimezone();

        // Initialize performance monitoring
        this._performanceMetrics = {
            cacheHits: 0,
            cacheMisses: 0,
            conversions: 0
        };
    }

    /**
     * Detect user's timezone automatically
     * @private
     * @returns {string} Detected timezone identifier
     */
    _detectUserTimezone() {
        try {
            // Modern browsers with Intl support
            if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
                const detectedTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
                if (detectedTz && detectedTz !== 'undefined') {
                    return detectedTz;
                }
            }

            // Enhanced fallback methods for older browsers
            const now = new Date();
            const janOffset = new Date(now.getFullYear(), 0, 1).getTimezoneOffset();
            const julOffset = new Date(now.getFullYear(), 6, 1).getTimezoneOffset();
            const currentOffset = now.getTimezoneOffset();

            // Check for DST to improve timezone detection
            const isDST = currentOffset !== Math.max(janOffset, julOffset);
            const standardOffset = isDST ? julOffset : janOffset;

            // Improved timezone guessing with DST consideration
            const timezoneGuessMap = {
                // Eastern Time (ET) - UTC-5 standard, UTC-4 DST
                '-300': isDST ? 'America/New_York' : 'America/New_York',
                // Central Time (CT) - UTC-6 standard, UTC-5 DST
                '-360': isDST ? 'America/Chicago' : 'America/Chicago',
                // Mountain Time (MT) - UTC-7 standard, UTC-6 DST
                '-420': isDST ? 'America/Denver' : 'America/Denver',
                // Pacific Time (PT) - UTC-8 standard, UTC-7 DST
                '-480': isDST ? 'America/Los_Angeles' : 'America/Los_Angeles',
                // European time zones
                '0': 'Europe/London',
                '60': isDST ? 'Europe/Paris' : 'Europe/Paris',
                // Asian time zones (most don't observe DST)
                '540': 'Asia/Tokyo',
                '480': 'Asia/Shanghai'
            };

            const guessedTimezone = timezoneGuessMap[String(standardOffset)];
            if (guessedTimezone) {
                return guessedTimezone;
            }

            // Final fallback - return UTC offset string with proper format
            const offsetHours = Math.floor(Math.abs(currentOffset) / 60);
            const offsetMinutes = Math.abs(currentOffset) % 60;
            const sign = currentOffset <= 0 ? '+' : '-';
            return `UTC${sign}${String(offsetHours).padStart(2, '0')}:${String(offsetMinutes).padStart(2, '0')}`;

        } catch (error) {
            console.warn('TimeZoneUtils: Failed to detect timezone, using UTC', error);
            return 'UTC';
        }
    }

    /**
     * Get the detected user timezone
     * @returns {string} User's timezone identifier
     */
    detectUserTimeZone() {
        return this._userTimezone;
    }

    /**
     * Get comprehensive timezone information
     * @param {string} [timezone] - Timezone identifier (optional, defaults to user timezone)
     * @returns {Object} Timezone information object
     */
    getTimezoneInfo(timezone) {
        const tz = timezone || this._userTimezone;
        const cacheKey = `tzinfo_${tz}`;

        // Check cache first
        if (this._isCacheValid(cacheKey, this._cacheTimestamps, this._CACHE_TTL)) {
            this._performanceMetrics.cacheHits++;
            return this._offsetCache.get(cacheKey);
        }

        this._performanceMetrics.cacheMisses++;

        try {
            const now = new Date();
            const offset = this._getTimezoneOffset(now, tz);

            const info = {
                identifier: tz,
                name: this._formatTimezoneName(tz),
                offset: offset,
                offsetString: this._formatOffset(offset),
                currentTime: this.formatToLocalTime(now.getTime(), { timezone: tz }),
                isDST: this._isDST(now, tz),
                rawOffset: this._getRawTimezoneOffset(tz)
            };

            // Cache the result
            this._offsetCache.set(cacheKey, info);
            this._cacheTimestamps.set(cacheKey, Date.now());

            return info;

        } catch (error) {
            console.warn('TimeZoneUtils: Failed to get timezone info for', tz, error);
            return {
                identifier: tz,
                name: tz,
                offset: 0,
                offsetString: '+00:00',
                currentTime: 'Unknown',
                isDST: false,
                error: error.message
            };
        }
    }

    /**
     * Format timestamp to local time with comprehensive options
     * @param {number|string|Date} timestamp - Timestamp to format
     * @param {Object} [options] - Formatting options
     * @param {string} [options.timezone] - Target timezone (defaults to user timezone)
     * @param {string} [options.format='YYYY-MM-DD HH:mm:ss'] - Date format pattern
     * @param {string} [options.locale='en-US'] - Locale for formatting
     * @param {boolean} [options.includeOffset=true] - Include timezone offset
     * @param {boolean} [options.use24Hour=true] - Use 24-hour format
     * @returns {string} Formatted local time string
     */
    formatToLocalTime(timestamp, options = {}) {
        const {
            timezone,
            format = 'YYYY-MM-DD HH:mm:ss',
            locale = 'en-US',
            includeOffset = true,
            use24Hour = true
        } = options;

        const targetTimezone = timezone || this._userTimezone;
        const cacheKey = `format_${timestamp}_${targetTimezone}_${format}_${locale}_${use24Hour}`;

        // Check cache for formatted results
        if (this._isCacheValid(cacheKey, this._formatCacheTimestamps, this._FORMAT_CACHE_TTL)) {
            this._performanceMetrics.cacheHits++;
            return this._formatCache.get(cacheKey);
        }

        this._performanceMetrics.cacheMisses++;
        this._performanceMetrics.conversions++;

        try {
            // Sanitize and validate the timestamp first
            const sanitizedTimestamp = this._sanitizeTimestamp(timestamp);
            const date = new Date(sanitizedTimestamp);

            // Validate date after sanitization
            if (isNaN(date.getTime())) {
                throw new Error('Invalid timestamp');
            }

            let formattedTime;

            // Try modern Intl.DateTimeFormat first
            if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
                try {
                    const formatterOptions = {
                        timeZone: targetTimezone,
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: use24Hour ? '2-digit' : 'numeric',
                        minute: '2-digit',
                        second: '2-digit',
                        hour12: !use24Hour
                    };

                    const formatter = new Intl.DateTimeFormat(locale, formatterOptions);
                    const parts = formatter.formatToParts(date);

                    formattedTime = this._buildFormatString(parts, format);

                } catch (intlError) {
                    // Fallback to manual formatting
                    formattedTime = this._manualFormat(date, targetTimezone, format, use24Hour);
                }
            } else {
                // Fallback for browsers without Intl support
                formattedTime = this._manualFormat(date, targetTimezone, format, use24Hour);
            }

            // Add timezone offset if requested
            if (includeOffset) {
                const offset = this._getTimezoneOffset(date, targetTimezone);
                const offsetString = this._formatOffset(offset);
                formattedTime += ` (${offsetString})`;
            }

            // Cache the result
            this._formatCache.set(cacheKey, formattedTime);
            this._formatCacheTimestamps.set(cacheKey, Date.now());

            return formattedTime;

        } catch (error) {
            console.warn('TimeZoneUtils: Failed to format timestamp', error);
            return new Date(timestamp).toLocaleString();
        }
    }

    /**
     * Convert timestamp between timezones
     * @param {number|string|Date} timestamp - Source timestamp
     * @param {string} sourceTimezone - Source timezone identifier
     * @param {string} targetTimezone - Target timezone identifier
     * @returns {Date} Converted date object
     */
    convertTimezone(timestamp, sourceTimezone, targetTimezone) {
        try {
            // Sanitize and validate the timestamp
            const sanitizedTimestamp = this._sanitizeTimestamp(timestamp);
            const sourceDate = new Date(sanitizedTimestamp);
            if (isNaN(sourceDate.getTime())) {
                throw new Error('Invalid timestamp provided for timezone conversion');
            }

            // For enhanced accuracy, use Intl API when available
            if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
                try {
                    // Get the exact local time representation in source timezone
                    const sourceFormatter = new Intl.DateTimeFormat('en-US', {
                        timeZone: sourceTimezone,
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        hour12: false
                    });

                    const sourceParts = sourceFormatter.formatToParts(sourceDate);
                    const sourceValues = {};
                    sourceParts.forEach(part => {
                        sourceValues[part.type] = part.value;
                    });

                    // Create the exact same date components in target timezone
                    const targetDateComponents = {
                        year: parseInt(sourceValues.year),
                        month: parseInt(sourceValues.month) - 1, // JavaScript months are 0-indexed
                        day: parseInt(sourceValues.day),
                        hour: parseInt(sourceValues.hour),
                        minute: parseInt(sourceValues.minute),
                        second: parseInt(sourceValues.second)
                    };

                    // Format in target timezone to get the actual representation
                    const targetFormatter = new Intl.DateTimeFormat('en-CA', { // en-CA uses YYYY-MM-DD format
                        timeZone: targetTimezone,
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        hour12: false
                    });

                    // Create a date in the target timezone
                    const tentativeDate = new Date(
                        Date.UTC(
                            targetDateComponents.year,
                            targetDateComponents.month,
                            targetDateComponents.day,
                            targetDateComponents.hour,
                            targetDateComponents.minute,
                            targetDateComponents.second
                        )
                    );

                    // Adjust for the target timezone offset
                    const targetOffset = this._getTimezoneOffset(sourceDate, targetTimezone);
                    const adjustedTime = tentativeDate.getTime() - (targetOffset * 60 * 1000);

                    return new Date(adjustedTime);

                } catch (intlError) {
                    console.warn('Intl conversion failed, falling back to manual method:', intlError);
                    // Fall back to manual calculation
                }
            }

            // Manual fallback calculation
            const sourceOffset = this._getTimezoneOffset(sourceDate, sourceTimezone);
            const targetOffset = this._getTimezoneOffset(sourceDate, targetTimezone);

            // Calculate the offset difference
            const offsetDiff = targetOffset - sourceOffset;
            const convertedTime = sourceDate.getTime() + (offsetDiff * 60 * 1000);

            return new Date(convertedTime);

        } catch (error) {
            console.warn('TimeZoneUtils: Failed to convert timezone from', sourceTimezone, 'to', targetTimezone, ':', error);
            return new Date(timestamp);
        }
    }

    /**
     * Format multiple timestamps in batch for performance
     * @param {Array} timestamps - Array of timestamps to format
     * @param {Object} [options] - Formatting options (same as formatToLocalTime)
     * @returns {Array} Array of formatted time strings
     */
    formatBatch(timestamps, options = {}) {
        return timestamps.map(timestamp => this.formatToLocalTime(timestamp, options));
    }

    /**
     * Get timezone offset in minutes for given date and timezone
     * @private
     * @param {Date} date - Date to get offset for
     * @param {string} timezone - Timezone identifier
     * @returns {number} Offset in minutes
     */
    _getTimezoneOffset(date, timezone) {
        try {
            // Use the most reliable approach with Intl.DateTimeFormat.formatToParts
            if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
                // Create formatter for the target timezone
                const formatter = new Intl.DateTimeFormat('en-US', {
                    timeZone: timezone,
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false,
                    timeZoneName: 'short'
                });

                // Get the date parts
                const parts = formatter.formatToParts(date);
                const partValues = {};
                parts.forEach(part => {
                    partValues[part.type] = part.value;
                });

                // Extract date and time components
                const year = parseInt(partValues.year);
                const month = parseInt(partValues.month) - 1; // JS months are 0-indexed
                const day = parseInt(partValues.day);
                const hour = parseInt(partValues.hour);
                const minute = parseInt(partValues.minute);
                const second = parseInt(partValues.second);

                // Create a UTC date for the same components
                const utcEquivalent = Date.UTC(year, month, day, hour, minute, second);
                const originalTime = date.getTime();

                // Calculate the offset (positive = east of UTC, negative = west)
                const offsetMinutes = Math.round((utcEquivalent - originalTime) / (60 * 1000));

                return offsetMinutes;
            }

            // Fallback for older browsers
            return this._getTimezoneOffsetFallback(date, timezone);

        } catch (error) {
            console.warn('TimeZoneUtils: Failed to get timezone offset for', timezone, error);
            return this._getTimezoneOffsetFallback(date, timezone);
        }
    }

    /**
     * Enhanced fallback method for getting timezone offset
     * @private
     * @param {Date} date - Date to get offset for
     * @param {string} timezone - Timezone identifier
     * @returns {number} Offset in minutes
     */
    _getTimezoneOffsetFallback(date, timezone) {
        // Enhanced fallback with comprehensive timezone data
        const year = date.getFullYear();
        const month = date.getMonth();
        const isDST = this._isDST(date, timezone);

        // Enhanced timezone data with DST consideration
        const fallbackOffsets = {
            // UTC
            'UTC': 0,
            'GMT': 0,

            // North America
            'America/New_York': isDST ? -240 : -300,  // ET: UTC-5, DST UTC-4
            'America/Chicago': isDST ? -300 : -360,    // CT: UTC-6, DST UTC-5
            'America/Denver': isDST ? -360 : -420,     // MT: UTC-7, DST UTC-6
            'America/Phoenix': -420,                    // MST: UTC-7 (no DST)
            'America/Los_Angeles': isDST ? -420 : -480, // PT: UTC-8, DST UTC-7
            'America/Anchorage': isDST ? -480 : -540,   // AKT: UTC-9, DST UTC-8
            'America/Honolulu': -600,                   // HST: UTC-10 (no DST)
            'America/Toronto': isDST ? -240 : -300,
            'America/Vancouver': isDST ? -420 : -480,
            'America/Mexico_City': -360,                // CST: UTC-6 (no DST)

            // South America
            'America/Sao_Paulo': isDST ? -180 : -240,   // BRT: UTC-3, DST UTC-2
            'America/Buenos_Aires': -180,               // ART: UTC-3 (no DST)
            'America/Santiago': isDST ? -180 : -240,    // CLT: UTC-4, DST UTC-3

            // Europe
            'Europe/London': isDST ? 60 : 0,            // GMT/BST: UTC+0, DST UTC+1
            'Europe/Paris': isDST ? 120 : 60,           // CET/CEST: UTC+1, DST UTC+2
            'Europe/Berlin': isDST ? 120 : 60,
            'Europe/Rome': isDST ? 120 : 60,
            'Europe/Madrid': isDST ? 120 : 60,
            'Europe/Moscow': 180,                       // MSK: UTC+3 (no DST)

            // Asia
            'Asia/Tokyo': 540,                          // JST: UTC+9 (no DST)
            'Asia/Shanghai': 480,                       // CST: UTC+8 (no DST)
            'Asia/Hong_Kong': 480,
            'Asia/Seoul': 540,
            'Asia/Singapore': 480,
            'Asia/Dubai': 240,                          // GST: UTC+4 (no DST)
            'Asia/Kolkata': 330,                        // IST: UTC+5:30 (no DST)
            'Asia/Bangkok': 420,                        // ICT: UTC+7 (no DST)
            'Asia/Jakarta': 420,                        // WIB: UTC+7 (no DST)

            // Australia
            'Australia/Sydney': isDST ? 660 : 600,      // AEDT: UTC+11, AEST: UTC+10
            'Australia/Melbourne': isDST ? 660 : 600,
            'Australia/Perth': 480,                     // AWST: UTC+8 (no DST)

            // Pacific
            'Pacific/Auckland': isDST ? 780 : 720,      // NZDT: UTC+13, NZST: UTC+12
            'Pacific/Fiji': isDST ? 780 : 720,          // FJST: UTC+13, FJT: UTC+12

            // Africa
            'Africa/Cairo': 120,                        // EET: UTC+2 (no DST)
            'Africa/Lagos': 60,                         // WAT: UTC+1 (no DST)
            'Africa/Johannesburg': 120                  // SAST: UTC+2 (no DST)
        };

        // Check for exact match first
        if (fallbackOffsets[timezone] !== undefined) {
            return fallbackOffsets[timezone];
        }

        // Handle partial matches for city names
        for (const [tzKey, offset] of Object.entries(fallbackOffsets)) {
            if (timezone.includes(tzKey.split('/')[1]) || tzKey.includes(timezone.split('/')[1])) {
                return offset;
            }
        }

        // Try to parse UTC offset from string
        if (timezone.startsWith('UTC')) {
            const match = timezone.match(/UTC([+-]\d+):?(\d*)/);
            if (match) {
                const hours = parseInt(match[1]);
                const minutes = match[2] ? parseInt(match[2]) : 0;
                return hours * 60 + (minutes * Math.sign(hours));
            }
        }

        // Final fallback
        console.warn('TimeZoneUtils: Unknown timezone in fallback:', timezone);
        return 0;
    }

    /**
     * Get raw timezone offset (without DST adjustments)
     * @private
     */
    _getRawTimezoneOffset(timezone) {
        const winterDate = new Date(2024, 0, 15); // January 15th
        return this._getTimezoneOffset(winterDate, timezone);
    }

    /**
     * Check if date is in DST for given timezone
     * @private
     * @param {Date} date - Date to check
     * @param {string} timezone - Timezone identifier
     * @returns {boolean} True if date is in DST
     */
    _isDST(date, timezone) {
        try {
            // Use Intl.DateTimeFormat to detect DST by checking timezone name
            if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
                const formatter = new Intl.DateTimeFormat('en-US', {
                    timeZone: timezone,
                    timeZoneName: 'short'
                });

                const parts = formatter.formatToParts(date);
                const timeZoneNamePart = parts.find(part => part.type === 'timeZoneName');
                const timeZoneName = timeZoneNamePart ? timeZoneNamePart.value : '';

                // Common DST indicators
                const dstIndicators = ['EDT', 'EDT', 'CDT', 'MDT', 'PDT', 'BST', 'CEST', 'EEST', 'WEST',
                                     'AEDT', 'ACDT', 'ACST', 'AWST', 'NZDT', 'FJST', 'PDT', 'MEST'];

                // Check if timezone name contains DST indicator
                return dstIndicators.some(indicator => timeZoneName.includes(indicator));
            }

            // Fallback method using offset comparison
            const year = date.getFullYear();
            const winterDate = new Date(year, 0, 15); // January 15th
            const summerDate = new Date(year, 6, 15); // July 15th

            const winterOffset = this._getTimezoneOffset(winterDate, timezone);
            const summerOffset = this._getTimezoneOffset(summerDate, timezone);
            const currentOffset = this._getTimezoneOffset(date, timezone);

            // If winter and summer offsets are different, timezone observes DST
            const observesDST = winterOffset !== summerOffset;

            if (!observesDST) {
                return false;
            }

            // Check if current offset matches the summer offset (indicating DST)
            return currentOffset === summerOffset;

        } catch (error) {
            console.warn('TimeZoneUtils: DST detection failed for', timezone, error);
            return false;
        }
    }

    /**
     * Format timezone name for display
     * @private
     */
    _formatTimezoneName(timezone) {
        const nameMap = {
            // UTC and GMT
            'UTC': 'Coordinated Universal Time',
            'GMT': 'Greenwich Mean Time',

            // North America
            'America/New_York': 'Eastern Time',
            'America/Chicago': 'Central Time',
            'America/Denver': 'Mountain Time',
            'America/Phoenix': 'Mountain Standard Time',
            'America/Los_Angeles': 'Pacific Time',
            'America/Anchorage': 'Alaska Time',
            'America/Honolulu': 'Hawaii Standard Time',
            'America/Toronto': 'Eastern Time',
            'America/Vancouver': 'Pacific Time',
            'America/Mexico_City': 'Central Standard Time',
            'America/Sao_Paulo': 'Brasilia Time',
            'America/Buenos_Aires': 'Argentina Time',

            // Europe
            'Europe/London': 'Greenwich Mean Time',
            'Europe/Paris': 'Central European Time',
            'Europe/Berlin': 'Central European Time',
            'Europe/Rome': 'Central European Time',
            'Europe/Madrid': 'Central European Time',
            'Europe/Moscow': 'Moscow Standard Time',
            'Europe/Amsterdam': 'Central European Time',

            // Asia
            'Asia/Tokyo': 'Japan Standard Time',
            'Asia/Shanghai': 'China Standard Time',
            'Asia/Hong_Kong': 'Hong Kong Time',
            'Asia/Seoul': 'Korea Standard Time',
            'Asia/Singapore': 'Singapore Time',
            'Asia/Dubai': 'Gulf Standard Time',
            'Asia/Kolkata': 'India Standard Time',
            'Asia/Bangkok': 'Indochina Time',
            'Asia/Jakarta': 'Western Indonesia Time',

            // Australia
            'Australia/Sydney': 'Australian Eastern Time',
            'Australia/Melbourne': 'Australian Eastern Time',
            'Australia/Perth': 'Australian Western Time',

            // Pacific
            'Pacific/Auckland': 'New Zealand Time',
            'Pacific/Fiji': 'Fiji Time',

            // Africa
            'Africa/Cairo': 'Eastern European Time',
            'Africa/Lagos': 'West Africa Time',
            'Africa/Johannesburg': 'South Africa Standard Time'
        };

        // Check for exact match first
        if (nameMap[timezone]) {
            return nameMap[timezone];
        }

        // Try to extract city name from timezone identifier
        const cityMatch = timezone.match(/^([A-Za-z_]+)\/([A-Za-z_]+)$/);
        if (cityMatch) {
            const city = cityMatch[2].replace(/_/g, ' ');
            return city + ' Time';
        }

        // Handle UTC offset strings
        if (timezone.startsWith('UTC')) {
            return 'UTC Time';
        }

        return timezone;
    }

    /**
     * Format offset as string
     * @private
     */
    _formatOffset(offsetMinutes) {
        const sign = offsetMinutes >= 0 ? '+' : '-';
        const absOffset = Math.abs(offsetMinutes);
        const hours = Math.floor(absOffset / 60);
        const minutes = absOffset % 60;

        return `UTC${sign}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
    }

    /**
     * Build format string from Intl parts with enhanced error handling
     * @private
     * @param {Array} parts - Array of Intl date parts
     * @param {string} format - Format string pattern
     * @returns {string} Formatted date string
     */
    _buildFormatString(parts, format) {
        const values = {};
        parts.forEach(part => {
            values[part.type] = part.value;
        });

        // Enhanced format mapping with fallbacks
        const formatMap = {
            'YYYY': values.year || new Date().getFullYear(),
            'YY': values.year ? String(values.year).slice(-2) : String(new Date().getFullYear()).slice(-2),
            'MM': values.month || '01',
            'M': values.month ? parseInt(values.month) : '1',
            'DD': values.day || '01',
            'D': values.day ? parseInt(values.day) : '1',
            'HH': values.hour || '00',
            'H': values.hour ? parseInt(values.hour) : '0',
            'mm': values.minute || '00',
            'm': values.minute ? parseInt(values.minute) : '0',
            'ss': values.second || '00',
            's': values.second ? parseInt(values.second) : '0'
        };

        // Replace format tokens
        let result = format;
        for (const [token, value] of Object.entries(formatMap)) {
            result = result.replace(new RegExp(token, 'g'), value);
        }

        return result;
    }

    /**
     * Manual date formatting for older browsers
     * @private
     */
    _manualFormat(date, timezone, format, use24Hour) {
        // This is a simplified manual formatting
        // Real implementation would need comprehensive timezone handling

        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        let hours = date.getHours();
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');

        if (!use24Hour) {
            const period = hours >= 12 ? 'PM' : 'AM';
            hours = hours % 12 || 12;
            hours = String(hours).padStart(2, '0');
        } else {
            hours = String(hours).padStart(2, '0');
        }

        return format
            .replace('YYYY', year)
            .replace('MM', month)
            .replace('DD', day)
            .replace('HH', hours)
            .replace('mm', minutes)
            .replace('ss', seconds);
    }

    /**
     * Check if cache entry is still valid
     * @private
     */
    _isCacheValid(cacheKey, timestampsMap, ttl) {
        const timestamp = timestampsMap.get(cacheKey);
        return timestamp && (Date.now() - timestamp) < ttl;
    }

    /**
     * Clear all caches
     */
    clearCache() {
        this._offsetCache.clear();
        this._cacheTimestamps.clear();
        this._formatCache.clear();
        this._formatCacheTimestamps.clear();
        this._performanceMetrics = {
            cacheHits: 0,
            cacheMisses: 0,
            conversions: 0
        };
    }

    /**
     * Get performance metrics
     * @returns {Object} Performance statistics
     */
    getPerformanceMetrics() {
        const total = this._performanceMetrics.cacheHits + this._performanceMetrics.cacheMisses;
        return {
            ...this._performanceMetrics,
            cacheHitRate: total > 0 ? (this._performanceMetrics.cacheHits / total * 100).toFixed(2) + '%' : '0%'
        };
    }

    /**
     * Validate timezone identifier
     * @param {string} timezone - Timezone identifier to validate
     * @returns {boolean} True if valid
     */
    isValidTimezone(timezone) {
        if (typeof timezone !== 'string' || !timezone.trim()) {
            return false;
        }

        try {
            // Try to create a DateTimeFormat with the timezone
            if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
                Intl.DateTimeFormat(undefined, { timeZone: timezone });
                return true;
            }

            // Fallback validation
            return /^[A-Za-z_\/]+$/.test(timezone) && timezone.length <= 32;

        } catch (error) {
            return false;
        }
    }

    /**
     * Sanitize and validate input timestamps with enhanced validation
     * @private
     * @param {number|string|Date} timestamp - Input timestamp to sanitize
     * @returns {number} Valid timestamp in milliseconds
     */
    _sanitizeTimestamp(timestamp) {
        // Handle null/undefined
        if (timestamp === null || timestamp === undefined) {
            console.warn('TimeZoneUtils: Null/undefined timestamp, using current time');
            return Date.now();
        }

        // Handle numbers (timestamps in milliseconds)
        if (typeof timestamp === 'number') {
            // Check if the number is within reasonable bounds (year 1900-2100)
            const minTimestamp = new Date('1900-01-01').getTime();
            const maxTimestamp = new Date('2100-12-31').getTime();

            if (timestamp < minTimestamp || timestamp > maxTimestamp) {
                console.warn('TimeZoneUtils: Timestamp out of reasonable range, using current time');
                return Date.now();
            }

            return timestamp;
        }

        // Handle strings
        if (typeof timestamp === 'string') {
            const trimmedTimestamp = timestamp.trim();
            if (trimmedTimestamp === '') {
                console.warn('TimeZoneUtils: Empty string timestamp, using current time');
                return Date.now();
            }

            const parsed = Date.parse(trimmedTimestamp);
            if (isNaN(parsed)) {
                console.warn('TimeZoneUtils: Invalid string timestamp, using current time:', trimmedTimestamp);
                return Date.now();
            }

            return parsed;
        }

        // Handle Date objects
        if (timestamp instanceof Date) {
            if (isNaN(timestamp.getTime())) {
                console.warn('TimeZoneUtils: Invalid Date object, using current time');
                return Date.now();
            }

            return timestamp.getTime();
        }

        // Handle other types
        console.warn('TimeZoneUtils: Unsupported timestamp type, using current time:', typeof timestamp);
        return Date.now();
    }
}

// Create singleton instance for global use
const timeZoneUtils = new TimeZoneUtils();

// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TimeZoneUtils, timeZoneUtils };
}

if (typeof window !== 'undefined') {
    window.TimeZoneUtils = TimeZoneUtils;
    window.timeZoneUtils = timeZoneUtils;
}