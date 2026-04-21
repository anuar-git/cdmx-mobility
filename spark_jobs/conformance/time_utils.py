from pyspark.sql import Column
from pyspark.sql.functions import col, convert_timezone, lit, to_date
from pyspark.sql.types import TimestampType

UTC_TZ: str = "UTC"
CDMX_TZ: str = "America/Mexico_City"


def to_cdmx_timestamp(col_name: str) -> Column:
    """Convert a UTC TimestampType column to America/Mexico_City local time.

    All upstream sources mix UTC and local time. Call this once per column
    at the top of every Silver job rather than scattering timezone logic.
    """
    return convert_timezone(lit(UTC_TZ), lit(CDMX_TZ), col(col_name))


def epoch_ms_to_timestamp(col_name: str) -> Column:
    """Convert an integer epoch-milliseconds column to TimestampType (UTC).

    GTFS-RT FeedHeader.timestamp and EcoBici last_reported are epoch seconds;
    some internal fields use milliseconds. This handles the millisecond case.
    Divide by 1000 before casting — Spark's TimestampType interprets the cast
    value as epoch seconds, not milliseconds.
    """
    return (col(col_name) / 1000).cast(TimestampType())


def extract_service_date(ts_col: str) -> Column:
    """Extract the CDMX-local calendar date from a UTC timestamp column.

    Used as the Hive partition key for all Silver datasets. Deriving the date
    after timezone conversion ensures a vehicle position recorded at 23:45 UTC
    (which is 17:45 or 18:45 local, depending on DST) lands in the correct
    service-date partition rather than the next day.
    """
    return to_date(to_cdmx_timestamp(ts_col))
