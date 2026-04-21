from pyspark.sql import SparkSession


def get_spark_session(app_name: str, local: bool = False) -> SparkSession:
    """Create or retrieve a SparkSession for this job.

    Args:
        app_name: Shown in the Spark UI and Dataproc job history.
        local: True for unit tests and one-shot local smoke tests.
            False (default) when running on a Dataproc cluster.

    Local mode (local=True):
        - master("local[2]") — 2 executor threads, no cluster required.
        - shuffle partitions = 4. The Spark default is 200, which creates 200
          empty output files for tiny test DataFrames and slows down every
          aggregation. 4 is right-sized for fixtures with tens of rows.
        - GCS connector is NOT configured. Local smoke tests and unit tests
          read from local file paths, not gs:// URIs.

    Dataproc mode (local=False):
        - master() is omitted; YARN sets it when the job is submitted via the
          Dataproc workflow template.
        - shuffle partitions = 200 (matches default, appropriate for the
          cluster size: 3 x n1-standard-4 workers = 12 vCPUs).
        - The GCS connector JAR (gcs-connector-hadoop3-*.jar) is pre-installed
          on all Dataproc 2.2 images; no explicit configuration needed.
    """
    builder = SparkSession.builder.appName(app_name)

    if local:
        builder = builder.master("local[2]").config("spark.sql.shuffle.partitions", "4")
    else:
        builder = builder.config("spark.sql.shuffle.partitions", "200")

    return builder.getOrCreate()
