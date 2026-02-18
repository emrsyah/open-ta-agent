"""Initial migration - Create catalog table

Revision ID: 001_initial
Revises: 
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create catalog_type enum
    catalog_type_enum = postgresql.ENUM(
        'Artikel - Restricted Use',
        'Bahan Ajar',
        'Buku - Circulation (BI Corner)',
        'Buku - Circulation (Dapat Dipinjam)',
        'Buku - Elektronik (E-Book)',
        'Buku - Elektronik (E-Book) Kindle',
        'Buku - Elektronik (E-Book) Restricted',
        'Buku - Elektronik (E-Book) Tel-U Press',
        'Buku - LAC',
        'Buku - Reference (Hanya Baca di Tempat)',
        'Buku Rekreatif - Circulation',
        'Buku Softskill - Circulation',
        'Case Studies',
        'Disertasi - Reference',
        'E-Article',
        'Institutional Content',
        'Jurnal Internasional - Reference',
        'Jurnal Nasional - Reference',
        'Jurnal Terakreditasi DIKTI - Reference',
        'Karya Ilmiah - Disertasi (S3) - Reference',
        'Karya Ilmiah - Skripsi (S1) - Reference',
        'Karya Ilmiah - TA (D3) - Reference',
        'Karya Ilmiah - Thesis (S2) - Reference',
        'Majalah - Reference',
        'Majalah Bundling',
        'Majalah Ilmiah - Reference',
        'Majalah Populer - Reference',
        'Modul Praktikum ( Electronic )',
        'Proceeding ( Electronic )',
        'e - Article Journal',
        'ePoster',
        'skripsi',
        name='catalog_type'
    )
    catalog_type_enum.create(op.get_bind())
    
    # Create catalog table
    op.create_table(
        'catalog',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('catalog_number', sa.String(length=100), nullable=True),
        sa.Column('catalog_type', sa.Enum(name='catalog_type'), nullable=True),
        sa.Column('classification_number', sa.String(length=100), nullable=True),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('author', sa.Text(), nullable=True),
        sa.Column('editor', sa.Text(), nullable=True),
        sa.Column('publisher', sa.Text(), nullable=True),
        sa.Column('shelf_number', sa.String(length=100), nullable=True),
        sa.Column('library_location', sa.Text(), nullable=True),
        sa.Column('publication_year', sa.SmallInteger(), nullable=True),
        sa.Column('total_copies', sa.Integer(), server_default='0', nullable=False),
        sa.Column('access_link', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        comment='Telkom University library catalog for research papers'
    )
    
    # Create indexes
    op.create_index(
        'catalog_publication_year_idx',
        'catalog',
        ['publication_year'],
        unique=False,
        postgresql_using='btree'
    )
    op.create_index(
        'catalog_type_idx',
        'catalog',
        ['catalog_type'],
        unique=False,
        postgresql_using='btree'
    )
    op.create_index(
        'catalog_title_idx',
        'catalog',
        ['title'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'title': 'gin_trgm_ops'}
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('catalog_title_idx', table_name='catalog')
    op.drop_index('catalog_type_idx', table_name='catalog')
    op.drop_index('catalog_publication_year_idx', table_name='catalog')
    
    # Drop table
    op.drop_table('catalog')
    
    # Drop enum
    op.execute('DROP TYPE catalog_type')
