"""schema sync for print agents, term packages and multi-asset allocations

Revision ID: b7c4d2a93f10
Revises: ade7d99e9212
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "b7c4d2a93f10"
down_revision = "ade7d99e9212"
branch_labels = None
depends_on = None


def _tables():
    return set(inspect(op.get_bind()).get_table_names())


def _columns(table):
    if table not in _tables():
        return set()
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    if table not in _tables():
        return set()
    return {idx["name"] for idx in inspect(op.get_bind()).get_indexes(table)}


def _check_constraints(table):
    if table not in _tables():
        return set()
    return {constraint["name"] for constraint in inspect(op.get_bind()).get_check_constraints(table)}


def _add_column_if_missing(table, column):
    if table in _tables() and column.name not in _columns(table):
        op.add_column(table, column)


def _create_index_if_missing(name, table, columns, unique=False, where=None):
    if table in _tables() and name not in _indexes(table):
        kwargs = {}
        if where is not None:
            dialect = op.get_bind().dialect.name
            if dialect == "postgresql":
                kwargs["postgresql_where"] = where
            elif dialect == "sqlite":
                kwargs["sqlite_where"] = where
        op.create_index(name, table, columns, unique=unique, **kwargs)


def _assert_no_duplicate_nonempty(table, column, label):
    if table not in _tables() or column not in _columns(table):
        return
    rows = op.get_bind().execute(text(f"""
        SELECT {column} AS value, COUNT(*) AS total
        FROM {table}
        WHERE {column} IS NOT NULL AND {column} <> ''
        GROUP BY {column}
        HAVING COUNT(*) > 1
        LIMIT 5
    """)).fetchall()
    if rows:
        examples = ", ".join(f"{row.value} ({row.total})" for row in rows)
        raise RuntimeError(
            f"Existem duplicidades em {label} antes da criação do índice único: {examples}. "
            "Corrija os registros duplicados e execute a migration novamente."
        )


def upgrade():
    bind = op.get_bind()
    tables = _tables()

    _add_column_if_missing("colaboradores", sa.Column("cpf", sa.String(length=20), nullable=True))
    _add_column_if_missing("devolucoes", sa.Column("cobranca_aplicada", sa.Boolean(), nullable=True))
    _add_column_if_missing("assets", sa.Column("public_token", sa.String(length=80), nullable=True))
    _add_column_if_missing("termos_avulsos", sa.Column("package_id", sa.String(length=16), nullable=True))
    _add_column_if_missing("termos_avulsos", sa.Column("package_token", sa.String(length=64), nullable=True))
    _add_column_if_missing("termos_avulsos", sa.Column("package_token_expiry", sa.DateTime(), nullable=True))

    if bind.dialect.name == "postgresql" and "termos_avulsos" in tables:
        bind.execute(text("""
            ALTER TABLE termos_avulsos
            ALTER COLUMN package_token_expiry TYPE TIMESTAMP WITHOUT TIME ZONE
            USING NULLIF(package_token_expiry::text, '')::timestamp
        """))

    _create_index_if_missing("ix_termos_avulsos_package_id", "termos_avulsos", ["package_id"])
    _create_index_if_missing("ix_termos_avulsos_package_token", "termos_avulsos", ["package_token"])
    _create_index_if_missing("ix_assets_public_token", "assets", ["public_token"], unique=True)
    _assert_no_duplicate_nonempty("assets", "patrimonio", "patrimônio")
    _create_index_if_missing(
        "ix_assets_patrimonio_unique_nonempty",
        "assets",
        ["patrimonio"],
        unique=True,
        where=text("patrimonio IS NOT NULL AND patrimonio <> ''"),
    )
    _assert_no_duplicate_nonempty("assets", "service_tag", "Service Tag")
    _create_index_if_missing(
        "ix_assets_service_tag_unique_nonempty",
        "assets",
        ["service_tag"],
        unique=True,
        where=text("service_tag IS NOT NULL AND service_tag <> ''"),
    )
    _assert_no_duplicate_nonempty("assets", "mac", "MAC")
    _create_index_if_missing(
        "ix_assets_mac_unique_nonempty",
        "assets",
        ["mac"],
        unique=True,
        where=text("mac IS NOT NULL AND mac <> ''"),
    )

    if (
        bind.dialect.name == "postgresql"
        and "supplies" in tables
        and "ck_supplies_estoque_nonnegative" not in _check_constraints("supplies")
    ):
        bind.execute(text("""
            ALTER TABLE supplies
            ADD CONSTRAINT ck_supplies_estoque_nonnegative CHECK (estoque >= 0) NOT VALID
        """))

    if "allocation_assets" not in tables:
        op.create_table(
            "allocation_assets",
            sa.Column("id", sa.String(length=20), nullable=False),
            sa.Column("allocation_id", sa.String(length=16), nullable=True),
            sa.Column("asset_id", sa.String(length=16), nullable=True),
            sa.Column("asset_nome", sa.String(length=200), nullable=True),
            sa.Column("categoria", sa.String(length=40), nullable=True),
            sa.Column("patrimonio", sa.String(length=40), nullable=True),
            sa.Column("service_tag", sa.String(length=40), nullable=True),
            sa.ForeignKeyConstraint(["allocation_id"], ["allocations.id"]),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        bind.execute(text("""
            INSERT INTO allocation_assets (id, allocation_id, asset_id, asset_nome, categoria, patrimonio, service_tag)
            SELECT 'AA' || substr(id, 3), id, ativo_id, ativo_nome, NULL, NULL, NULL
            FROM allocations
            WHERE ativo_id IS NOT NULL AND ativo_id <> ''
        """))
    _create_index_if_missing("ix_allocation_assets_allocation_id", "allocation_assets", ["allocation_id"])
    _create_index_if_missing("ix_allocation_assets_asset_id", "allocation_assets", ["asset_id"])

    if "print_printers" not in _tables():
        op.create_table(
            "print_printers",
            sa.Column("id", sa.String(length=60), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=True),
            sa.Column("location", sa.String(length=120), nullable=True),
            sa.Column("printer_type", sa.String(length=40), nullable=True),
            sa.Column("windows_name", sa.String(length=120), nullable=True),
            sa.Column("dpi", sa.Integer(), nullable=True),
            sa.Column("token_hash", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("last_seen", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _add_column_if_missing("print_printers", sa.Column("dpi", sa.Integer(), nullable=True))

    if "print_jobs" not in _tables():
        op.create_table(
            "print_jobs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("printer_id", sa.String(length=60), nullable=True),
            sa.Column("template", sa.String(length=80), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("copies", sa.Integer(), nullable=True),
            sa.Column("data", sa.JSON(), nullable=True),
            sa.Column("zpl", sa.Text(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("picked_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_print_jobs_printer_id", "print_jobs", ["printer_id"])
    _create_index_if_missing("ix_print_jobs_status", "print_jobs", ["status"])


def downgrade():
    for name, table in [
        ("ix_print_jobs_status", "print_jobs"),
        ("ix_print_jobs_printer_id", "print_jobs"),
        ("ix_allocation_assets_asset_id", "allocation_assets"),
        ("ix_allocation_assets_allocation_id", "allocation_assets"),
        ("ix_assets_mac_unique_nonempty", "assets"),
        ("ix_assets_service_tag_unique_nonempty", "assets"),
        ("ix_assets_patrimonio_unique_nonempty", "assets"),
        ("ix_assets_public_token", "assets"),
        ("ix_termos_avulsos_package_token", "termos_avulsos"),
        ("ix_termos_avulsos_package_id", "termos_avulsos"),
    ]:
        if table in _tables() and name in _indexes(table):
            op.drop_index(name, table_name=table)

    for table in ["print_jobs", "print_printers", "allocation_assets"]:
        if table in _tables():
            op.drop_table(table)

    if (
        op.get_bind().dialect.name == "postgresql"
        and "supplies" in _tables()
        and "ck_supplies_estoque_nonnegative" in _check_constraints("supplies")
    ):
        op.drop_constraint("ck_supplies_estoque_nonnegative", "supplies", type_="check")

    for table, column in [
        ("termos_avulsos", "package_token_expiry"),
        ("termos_avulsos", "package_token"),
        ("termos_avulsos", "package_id"),
        ("assets", "public_token"),
        ("devolucoes", "cobranca_aplicada"),
        ("colaboradores", "cpf"),
    ]:
        if table in _tables() and column in _columns(table):
            op.drop_column(table, column)
