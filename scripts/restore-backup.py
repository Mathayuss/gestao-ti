#!/usr/bin/env python3
"""
restore-backup.py — Restauração de backup do TI Control via linha de comando.

Uso:
    python scripts/restore-backup.py backup.json
    python scripts/restore-backup.py --validate-only backup.json

Execute a partir da raiz do projeto. O script carrega a aplicação Flask para
acessar o banco configurado em DATABASE_URL (via .env ou variável de ambiente).
"""
import sys
import json
import hashlib
import os
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Restaura um backup JSON do TI Control.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("arquivo", help="Caminho para o arquivo de backup JSON")
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Apenas valida o arquivo, sem alterar o banco",
    )
    args = parser.parse_args()

    if not os.path.exists(args.arquivo):
        print(f"[ERRO] Arquivo não encontrado: {args.arquivo}")
        sys.exit(1)

    with open(args.arquivo, "rb") as fh:
        data = fh.read()

    sha256 = hashlib.sha256(data).hexdigest()

    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception as e:
        print(f"[ERRO] Arquivo não é um JSON válido: {e}")
        sys.exit(1)

    # Carrega app Flask — deve rodar a partir da raiz do projeto
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)

    # Carrega .env se existir
    env_path = os.path.join(root, ".env")
    if os.path.exists(env_path):
        with open(env_path) as ef:
            for line in ef:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

    from app import app, _validate_backup_payload, _restore_from_payload, db

    with app.app_context():
        result = _validate_backup_payload(payload)

        print(f"\n{'='*62}")
        print("  VALIDAÇÃO DO BACKUP")
        print(f"{'='*62}")
        print(f"  Arquivo   : {args.arquivo}")
        print(f"  SHA-256   : {sha256}")
        print(f"  Gerado em : {result.get('geradoEm', '?')}")
        print(f"  Gerado por: {result.get('geradoPor', '?')}")
        print(f"  Versão    : {result.get('versao', '?')}")
        print(f"  Status    : {'VÁLIDO' if result['valid'] else 'INVÁLIDO'}")

        if result.get("summary"):
            print("\n  Registros no backup:")
            for key, count in result["summary"].items():
                print(f"    {key:<25s}: {count}")

        if result["errors"]:
            print(f"\n  ERROS ({len(result['errors'])}):")
            for e in result["errors"]:
                print(f"    [ERRO] {e}")

        if result["warnings"]:
            print(f"\n  Avisos ({len(result['warnings'])}):")
            for w in result["warnings"]:
                print(f"    [AVISO] {w}")

        if not result["valid"]:
            print("\n[ERRO] Backup inválido. Restauração cancelada.")
            sys.exit(1)

        if args.validate_only:
            print("\n[OK] Arquivo válido. Execute sem --validate-only para restaurar.")
            sys.exit(0)

        print(f"\n{'='*62}")
        print("  ATENÇÃO")
        print("  Esta operação irá APAGAR todos os dados atuais e restaurar")
        print("  o banco a partir do backup selecionado.")
        print("  Um backup pré-restauração será gerado automaticamente.")
        print(f"{'='*62}")

        confirm = input("\n  Digite CONFIRMAR para prosseguir (qualquer outra coisa cancela): ").strip()
        if confirm != "CONFIRMAR":
            print("Restauração cancelada.")
            sys.exit(0)

        print("\nGerando backup de segurança e restaurando...")
        try:
            stats = _restore_from_payload(payload, restored_by="script_cli")
            db.session.commit()
            print("\n[OK] Restauração concluída com sucesso!")
            print("  Registros restaurados:")
            for key, count in stats.items():
                print(f"    {key:<25s}: {count}")
        except Exception as e:
            db.session.rollback()
            print(f"\n[ERRO] Falha na restauração: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
