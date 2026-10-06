"""Land closed-loop rollouts in Iceberg as eval.rollout, keyed by nvidia_gold.episode.

Input: /user_data/rollouts.parquet, written on the host by evaluation/rollouts.py (one row per
AlpaSim or HUGSIM rollout found on disk, each with the episode_id it ran). This job joins every
row to its episode for the scenario class and the recording condition, reports rows whose
episode is missing from nvidia_gold.episode (rebuild the episode table first: episodes.py ->
build_episode_tables.py), and replaces eval.rollout. The table is derived, so re-running after
new rollouts land is the update path.

    spark-submit nvidia_ingestion/build_rollout_table.py [--input /user_data/rollouts.parquet]
"""
import argparse

from pyspark.sql import functions as F

from nvidia_ingestion.config import NvidiaPipelineConfig, build_spark_session


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/user_data/rollouts.parquet")
    ap.add_argument("--namespace", default="eval")
    a = ap.parse_args()

    cfg = NvidiaPipelineConfig()
    spark = build_spark_session(cfg, app_name="build-rollout-table")
    cat = cfg.spark_catalog_name
    ep = spark.table(f"{cat}.{cfg.nvidia.namespace_gold}.episode").select("episode_id", "scenario_id", "condition", "kind")
    ro = spark.read.parquet(a.input)
    df = ro.join(ep, "episode_id", "left")
    missing = df.filter(F.col("scenario_id").isNull())
    n_missing = missing.count()
    print(f"[rollouts] {ro.count()} rollouts; {n_missing} without a matching episode")
    if n_missing:
        missing.select("simulator", "run", "episode_id").show(20, truncate=False)

    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {cat}.{a.namespace}")
    df.writeTo(f"{cat}.{a.namespace}.rollout").using("iceberg") \
        .tableProperty("format-version", "2").createOrReplace()
    print(f"[rollouts] wrote {cat}.{a.namespace}.rollout")
    (spark.table(f"{cat}.{a.namespace}.rollout")
        .groupBy("simulator", "serving_mode", "policy", "condition")
        .agg(F.count("*").alias("rollouts"), F.countDistinct("clip_id").alias("clips"),
             F.round(F.avg(F.col("failed").cast("double")), 3).alias("failed"))
        .orderBy("simulator", "serving_mode", "policy", "condition").show(60, truncate=False))


if __name__ == "__main__":
    main()
