
> [!NOTE]
> Replace `localhost` with your machine's IP address if necessary.

0. **Clone the repository**
    ```bash
    git clone <REPO>
    cd <REPO>
    ```

1.  **Create a `.env` file**
    ```bash
    cp example.env .env
    ```
      - Refer to the `example.env` file for configuration.
    > [!NOTE]
    > The `MINIO_ROOT_USER` and `AWS_ACCESS_KEY_ID`, as well as the `MINIO_ROOT_PASSWORD` and `AWS_SECRET_ACCESS_KEY` in the `.env` file, must match each other. 
    >
    > The USER must be at least 5 characters long, and the PASSWORD must be at least 8 characters long.

2.  **Grant execution permissions and run `start.sh`**

    ```bash
    chmod +x start.sh
    ./start.sh
    ```

3.  **Create a `spark1` bucket in MinIO** (Required for the Spark test script)

      - Access: http://localhost:9001
      - Login with the credentials defined in your `.env` file.

4.  **Access the `spark-iceberg` container**

    ```bash
    docker exec -it spark-iceberg bash
    ```

5.  **Run the environment setup test**

    ```bash
    spark-submit python-scripts/spark-iceberg-nessie_test.py
    ```

6.  **Monitor Spark Jobs**

      - While the Python code is running, check the Spark Web UI.
      - Access: http://localhost:4040 (or 4041)

7.  **Verify data in MinIO Console**

      - Access: http://localhost:9001
      - Check the `spark1` bucket to see if data has been created.

8.  **Verify results in Nessie Web UI**

      - Access: http://localhost:19120
      - Check if the `db` namespace/folder has been created.

> [!NOTE]
> The MinIO and Nessie data are stored in the `minio_data` and `nessie_data` folders within the directory where the Docker Compose command is executed, so the data is preserved even if the containers are removed and restarted.