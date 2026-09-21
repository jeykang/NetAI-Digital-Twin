#!/usr/bin/env python3
"""Run kubectl on the DataX control plane over SSH.

There is no local kubeconfig; the cluster is reached by SSHing to the control
plane (10.38.36.8) where netai-sys holds a cluster-admin kubeconfig. Credentials
live in .secrets/datax-controlplane.env (gitignored), same shape as the A100
helper in cosmos_augmentation/cluster.py.

    python deploy/k8s/kctl.py get nodes
    python deploy/k8s/kctl.py apply -f - < manifest.yaml     # stdin is forwarded
    python deploy/k8s/kctl.py -- logs -n netai-l40-test job/x --tail=50

    from kctl import kubectl                                  # programmatic
    rc, out, err = kubectl("get pods -n netai-l40-test")
"""
from __future__ import annotations

import os
import sys

import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
ICEBERG_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
ENV_FILE = os.path.join(ICEBERG_ROOT, ".secrets", "datax-controlplane.env")
HOST, PORT = "10.38.36.8", 22


def _env() -> dict[str, str]:
    if not os.path.exists(ENV_FILE):
        raise SystemExit(f"missing {ENV_FILE} (needs DATAX_ID / DATAX_PW)")
    env = {}
    for line in open(ENV_FILE):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("DATAX_ID", "DATAX_PW"):
        if k not in env:
            raise SystemExit(f"{ENV_FILE} missing {k}")
    return env


def _client() -> paramiko.SSHClient:
    e = _env()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=e["DATAX_ID"], password=e["DATAX_PW"],
              timeout=25, banner_timeout=25, auth_timeout=25)
    return c


def kubectl(args: str, stdin: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    """Run `kubectl <args>`; returns (exit_status, stdout, stderr)."""
    c = _client()
    try:
        chan_in, chan_out, chan_err = c.exec_command(f"kubectl {args}", timeout=timeout)
        if stdin is not None:
            chan_in.write(stdin)
            chan_in.channel.shutdown_write()
        out = chan_out.read().decode()
        err = chan_err.read().decode()
        rc = chan_out.channel.recv_exit_status()
        return rc, out, err
    finally:
        c.close()


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        raise SystemExit(__doc__)
    data = None if sys.stdin.isatty() else sys.stdin.read()
    rc, out, err = kubectl(" ".join(args), stdin=data)
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return rc


if __name__ == "__main__":
    sys.exit(main())
