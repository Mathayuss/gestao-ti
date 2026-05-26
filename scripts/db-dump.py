#!/usr/bin/env python3
"""
Gera dump real do PostgreSQL do TI Control usando o container `postgres`.

Exemplos:
    python scripts/db-dump.py
    python scripts/db-dump.py --format sql
    python scripts/db-dump.py --output-dir C:\\backups\\ticontrol
"""
import argparse
import datetime as _dt
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Gera dump PostgreSQL via docker compose.")
    parser.add_argument("--output-dir", default="db_dumps", help="Diretório onde o dump será salvo.")
    parser.add_argument("--format", choices=("custom", "sql"), default="custom", help="Formato do pg_dump.")
    parser.add_argument("--service", default="postgres", help="Serviço PostgreSQL no docker-compose.")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "dump" if args.format == "custom" else "sql"
    output_path = os.path.abspath(os.path.join(args.output_dir, f"ticontrol_{timestamp}.{ext}"))

    if args.format == "custom":
        dump_command = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges'
    else:
        dump_command = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges'

    cmd = ["docker", "compose", "exec", "-T", args.service, "sh", "-c", dump_command]
    print("Gerando dump do PostgreSQL...")
    print("Destino:", output_path)
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError:
        print("[ERRO] Docker não encontrado no PATH.", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print("[ERRO] pg_dump falhou:", file=sys.stderr)
        print(result.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        return result.returncode

    with open(output_path, "wb") as fh:
        fh.write(result.stdout)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[OK] Dump gerado: {output_path} ({size_mb:.2f} MB)")
    if args.format == "custom":
        print("Restauração sugerida:")
        print(f"  docker compose exec -T {args.service} pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists < {output_path}")
    else:
        print("Restauração sugerida:")
        print(f"  docker compose exec -T {args.service} psql -U $POSTGRES_USER -d $POSTGRES_DB < {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
