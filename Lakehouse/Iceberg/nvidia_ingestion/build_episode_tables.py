"""Land the scenario x episode space in Iceberg: nvidia_gold.episode and nvidia_gold.scenario.

Input: the parquet files evaluation/episodes.py writes under user_data/ (the
spark-iceberg container sees that directory at /user_data). Every file carries the
same explicit schema; this job unions them, de-duplicates on episode_id, writes the
episode table, and derives the scenario table from it (one row per distinct
condition x augmentation x validator mode, with counts) so there is a single source
of truth.

The episode table keeps the canonical Episode columns (episode_id, from_clip_id,
to_clip_id, frame_id_list) and adds the validator-facing ones; it lives in the Gold
namespace because episodes are curation products, not recorded data.

    spark-submit nvidia_ingestion/build_episode_tables.py [--inputs "/user_data/episodes_*.parquet"]
"""
import argparse
import glob
import sys

from pyspark.sql import functions as F

from nvidia_ingestion.config import NvidiaPipelineConfig, build_spark_session, create_namespaces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default="/user_data/episodes_*.parquet")
    ap.add_argument("--table-prefix", default="", help="e.g. 'test_' to write test_episode/test_scenario")
    a = ap.parse_args()

    files = sorted(glob.glob(a.inputs))
    if not files:
        sys.exit(f"no inputs match {a.inputs}")
    cfg = NvidiaPipelineConfig()
    spark = build_spark_session(cfg, app_name="build-episode-tables")
    create_namespaces(spark, cfg)
    ns = f"{cfg.spark_catalog_name}.{cfg.nvidia.namespace_gold}"

    ep = spark.read.parquet(*files).dropDuplicates(["episode_id"])
    print(f"[episodes] {ep.count()} episodes from {len(files)} file(s)")
    ep.writeTo(f"{ns}.{a.table_prefix}episode").using("iceberg") \
        .tableProperty("format-version", "2").createOrReplace()

    scen = (ep.groupBy("scenario_id", "condition", "augmentation", "validator_mode")
              .agg(F.count("*").alias("n_episodes"),
                   F.countDistinct("clip_id").alias("n_clips"),
                   F.sum(F.when(F.col("kind") == "decision_window", 1).otherwise(0)).alias("n_decision_windows"),
                   F.sum(F.when(F.col("kind") == "aug_window", 1).otherwise(0)).alias("n_aug_windows"),
                   F.sum(F.when(F.col("kind") == "nurec_scene", 1).otherwise(0)).alias("n_nurec_scenes"),
                   F.avg("n_agents").alias("mean_agents_at_t0"))
              .withColumn("description",
                          F.concat_ws(" ", F.lit("recorded"), F.col("condition"), F.lit("clips,"),
                                      F.when(F.col("augmentation") == "none", F.lit("no augmentation"))
                                       .otherwise(F.concat(F.lit("augmented by "), F.col("augmentation"))),
                                      F.lit(", validated"), F.col("validator_mode")))
              .orderBy(F.desc("n_episodes")))
    scen.writeTo(f"{ns}.{a.table_prefix}scenario").using("iceberg") \
        .tableProperty("format-version", "2").createOrReplace()
    print(f"[scenarios] {scen.count()} scenarios")
    scen.show(40, truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
