import pytest
from pyspark.sql import SparkSession

from spark_jobs.conformance.spark_session import get_spark_session


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    """Shared SparkSession for all Spark unit tests.

    module scope amortises the ~5s JVM startup across all tests in a file.
    local[2] master + 4 shuffle partitions avoids the 200-empty-file problem
    on tiny test DataFrames.
    """
    session = get_spark_session("test-cdmx-spark", local=True)
    yield session
    session.stop()
