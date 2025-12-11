#!/bin/bash

mkdir -p ./nessie_data
mkdir -p ./minio_data
mkdir -p ./jars
mkdir -p ./python-scripts

docker-compose up -d

echo -e " - Nessie  : http://localhost:19120"
echo -e " - MinIO   : http://localhost:9001 (ID: asd / PW: asdasdasd)"
echo -e " - Spark UI: http://localhost:4040 (작업 실행 시 활성화)"

docker-compose ps