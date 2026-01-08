FROM apache/superset:latest

USER root

# Install DB drivers into Superset's runtime venv (/app/.venv)
# Use `uv` because that is what the upstream image uses for dependency management.
RUN set -eux; \
		export VIRTUAL_ENV=/app/.venv; \
		export PATH="/app/.venv/bin:${PATH}"; \
		command -v uv; \
		uv pip install --no-cache-dir \
			trino \
			psycopg2-binary; \
		/app/.venv/bin/python -c "import psycopg2; import trino; print('drivers-ok')"

USER superset
