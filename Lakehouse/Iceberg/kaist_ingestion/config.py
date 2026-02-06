"""
Configuration module for KAIST ingestion pipeline.

Handles environment variables, Spark session configuration, and storage backend settings.
Supports both MinIO (development) and Ceph (production) S3-compatible backends.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from pyspark.sql import SparkSession


def _env(name: str, default: Optional[str] = None) -> str:
    """Get environment variable or raise if missing and no default."""
    value = os.environ.get(name)
    if value is None or value == "":
        if default is None:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return default
    return value


@dataclass
class StorageConfig:
    """S3-compatible storage configuration."""
    
    endpoint: str = field(default_factory=lambda: _env("AWS_S3_ENDPOINT", "http://minio:9000"))
    access_key: str = field(default_factory=lambda: _env("AWS_ACCESS_KEY_ID", "minioadmin"))
    secret_key: str = field(default_factory=lambda: _env("AWS_SECRET_ACCESS_KEY", "minioadmin"))
    region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))
    bucket: str = field(default_factory=lambda: _env("S3_BUCKET", "spark1"))
    path_style_access: bool = True  # Required for MinIO and Ceph RGW


@dataclass
class CatalogConfig:
    """Iceberg REST Catalog (Polaris) configuration."""
    
    uri: str = field(default_factory=lambda: _env("POLARIS_URI", "http://polaris:8181/api/catalog"))
    warehouse: str = field(default_factory=lambda: _env("POLARIS_CATALOG_NAME", "lakehouse_catalog"))
    credential: str = field(default_factory=lambda: _env("POLARIS_CREDENTIAL", "root:s3cr3t"))
    scope: str = field(default_factory=lambda: _env("POLARIS_SCOPE", "PRINCIPAL_ROLE:ALL"))
    
    @property
    def oauth2_server_uri(self) -> str:
        return os.environ.get("POLARIS_OAUTH2_SERVER_URI", f"{self.uri}/v1/oauth/tokens")


@dataclass
class KAISTConfig:
    """KAIST dataset-specific configuration."""
    
    # Source data location (mounted volume or S3 path)
    source_path: str = field(default_factory=lambda: _env("KAIST_SOURCE_PATH", "/user_data/kaist"))
    
    # Iceberg namespace names
    namespace_bronze: str = "kaist_bronze"
    namespace_silver: str = "kaist_silver"
    namespace_gold: str = "kaist_gold"
    
    # Performance tuning
    target_file_size_bytes: int = 134_217_728  # 128 MB
    shuffle_partitions: int = 200
    
    # Ingestion behavior
    overwrite_existing: bool = True
    validate_on_ingest: bool = True


@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""
    
    storage: StorageConfig = field(default_factory=StorageConfig)
    catalog: CatalogConfig = field(default_factory=CatalogConfig)
    kaist: KAISTConfig = field(default_factory=KAISTConfig)
    
    # Spark catalog alias (used in SQL queries)
    spark_catalog_name: str = "iceberg"


def build_spark_session(config: PipelineConfig, app_name: str = "kaist-ingestion") -> SparkSession:
    """
    Build a SparkSession configured for Iceberg with Polaris catalog and S3 storage.
    
    This follows the pattern established in ingest_nuscenes_mini.py but is
    parameterized for flexibility.
    
    Args:
        config: Pipeline configuration
        app_name: Spark application name
        
    Returns:
        Configured SparkSession
    """
    catalog = config.spark_catalog_name
    storage = config.storage
    cat_cfg = config.catalog
    
    builder = (
        SparkSession.builder.appName(app_name)
        # Set default catalog
        .config("spark.sql.defaultCatalog", catalog)
        
        # Iceberg Spark catalog configuration
        .config(f"spark.sql.catalog.{catalog}", "org.apache.iceberg.spark.SparkCatalog")
        .config(f"spark.sql.catalog.{catalog}.catalog-impl", "org.apache.iceberg.rest.RESTCatalog")
        .config(f"spark.sql.catalog.{catalog}.uri", cat_cfg.uri)
        .config(f"spark.sql.catalog.{catalog}.warehouse", cat_cfg.warehouse)
        
        # S3 FileIO configuration
        .config(f"spark.sql.catalog.{catalog}.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config(f"spark.sql.catalog.{catalog}.s3.endpoint", storage.endpoint)
        .config(f"spark.sql.catalog.{catalog}.s3.path-style-access", str(storage.path_style_access).lower())
        .config(f"spark.sql.catalog.{catalog}.s3.access-key-id", storage.access_key)
        .config(f"spark.sql.catalog.{catalog}.s3.secret-access-key", storage.secret_key)
        
        # OAuth2 for Polaris authentication
        .config(f"spark.sql.catalog.{catalog}.oauth2-server-uri", cat_cfg.oauth2_server_uri)
        .config(f"spark.sql.catalog.{catalog}.credential", cat_cfg.credential)
        .config(f"spark.sql.catalog.{catalog}.scope", cat_cfg.scope)
        
        # Alternate OAuth2 key spellings for version compatibility
        .config(f"spark.sql.catalog.{catalog}.oauth2.server-uri", cat_cfg.oauth2_server_uri)
        .config(f"spark.sql.catalog.{catalog}.oauth2.credential", cat_cfg.credential)
        .config(f"spark.sql.catalog.{catalog}.oauth2.scope", cat_cfg.scope)
        
        # Hadoop S3A configuration (for reading source files from S3 if needed)
        .config("spark.hadoop.fs.s3a.endpoint", storage.endpoint)
        .config("spark.hadoop.fs.s3a.access.key", storage.access_key)
        .config("spark.hadoop.fs.s3a.secret.key", storage.secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", str(storage.path_style_access).lower())
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.aws.credentials.provider", 
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
        .config("spark.hadoop.fs.s3a.region", storage.region)
        
        # Performance tuning
        .config("spark.sql.shuffle.partitions", str(config.kaist.shuffle_partitions))
        .config("spark.sql.iceberg.write.target-file-size-bytes", 
                str(config.kaist.target_file_size_bytes))
        
        # Iceberg extensions
        .config("spark.sql.extensions", 
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    )
    
    return builder.getOrCreate()


def create_namespaces(spark: SparkSession, config: PipelineConfig) -> None:
    """Create the bronze, silver, and gold namespaces if they don't exist."""
    catalog = config.spark_catalog_name
    
    for namespace in [
        config.kaist.namespace_bronze,
        config.kaist.namespace_silver,
        config.kaist.namespace_gold,
    ]:
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {catalog}.{namespace}")
        print(f"Ensured namespace exists: {catalog}.{namespace}")
