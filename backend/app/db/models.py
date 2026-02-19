"""
SQLAlchemy models for Telkom University library catalog.
Matches the Drizzle ORM schema from the frontend.
"""

from sqlalchemy import (
    Column, Integer, String, Text, SmallInteger, Index, Enum as SQLEnum
)
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.database import Base
import enum


class CatalogType(str, enum.Enum):
    """
    Catalog type enum matching Drizzle schema.
    All 33 catalog types from the library system.
    """
    ARTICLE_RESTRICTED = "Artikel - Restricted Use"
    BAHAN_AJAR = "Bahan Ajar"
    BUKU_CIRCULATION_BI = "Buku - Circulation (BI Corner)"
    BUKU_CIRCULATION_DIPINJAM = "Buku - Circulation (Dapat Dipinjam)"
    BUKU_ELEKTRONIK = "Buku - Elektronik (E-Book)"
    BUKU_ELEKTRONIK_KINDLE = "Buku - Elektronik (E-Book) Kindle"
    BUKU_ELEKTRONIK_RESTRICTED = "Buku - Elektronik (E-Book) Restricted"
    BUKU_ELEKTRONIK_TELU_PRESS = "Buku - Elektronik (E-Book) Tel-U Press"
    BUKU_LAC = "Buku - LAC"
    BUKU_REFERENCE = "Buku - Reference (Hanya Baca di Tempat)"
    BUKU_REKREATIF = "Buku Rekreatif - Circulation"
    BUKU_SOFTSKILL = "Buku Softskill - Circulation"
    CASE_STUDIES = "Case Studies"
    DISERTASI_REFERENCE = "Disertasi - Reference"
    E_ARTICLE = "E-Article"
    INSTITUTIONAL_CONTENT = "Institutional Content"
    JURNAL_INTERNASIONAL = "Jurnal Internasional - Reference"
    JURNAL_NASIONAL = "Jurnal Nasional - Reference"
    JURNAL_TERAKREDITASI = "Jurnal Terakreditasi DIKTI - Reference"
    KARYA_ILMIAH_DISERTASI = "Karya Ilmiah - Disertasi (S3) - Reference"
    KARYA_ILMIAH_SKRIPSI = "Karya Ilmiah - Skripsi (S1) - Reference"
    KARYA_ILMIAH_TA = "Karya Ilmiah - TA (D3) - Reference"
    KARYA_ILMIAH_THESIS = "Karya Ilmiah - Thesis (S2) - Reference"
    MAJALAH_REFERENCE = "Majalah - Reference"
    MAJALAH_BUNDLING = "Majalah Bundling"
    MAJALAH_ILMIAH = "Majalah Ilmiah - Reference"
    MAJALAH_POPULER = "Majalah Populer - Reference"
    MODUL_PRAKTIKUM = "Modul Praktikum ( Electronic )"
    PROCEEDING = "Proceeding ( Electronic )"
    E_ARTICLE_JOURNAL = "e - Article Journal"
    E_POSTER = "ePoster"
    SKRIPSI = "skripsi"


class Catalog(Base):
    """
    Library catalog model matching Drizzle schema.
    
    Table: catalog
    Primary use: Research paper search and retrieval
    """
    __tablename__ = "catalog"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Required fields
    title: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Optional fields matching Drizzle schema
    catalog_number: Mapped[str | None] = mapped_column(
        String(100), 
        nullable=True,
        comment="Catalog number in library system"
    )
    
    catalog_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Type of catalog item (Mapped to public.catalog_type enum in DB)"
    )
    
    classification_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="DDC or other classification number"
    )
    
    subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Subject keywords"
    )
    
    author: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Author(s) of the work"
    )
    
    editor: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Editor(s) of the work"
    )
    
    publisher: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Publisher information"
    )
    
    shelf_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Physical shelf location"
    )
    
    library_location: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Which library/building"
    )
    
    publication_year: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Year of publication",
        index=True  # btree index as in Drizzle
    )
    
    total_copies: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of copies available"
    )
    
    access_link: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="URL for electronic access"
    )
    
    abstract: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Paper abstract or summary"
    )
    
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1024),
        nullable=True,
        comment="Vector embedding of title and abstract"
    )
    
    # Table configuration
    __table_args__ = (
        Index(
            'catalog_publication_year_idx',
            'publication_year',
            postgresql_using='btree',
        ),
        {'comment': 'Telkom University library catalog for research papers'}
    )
    
    def __repr__(self) -> str:
        return f"<Catalog(id={self.id}, title='{self.title[:50]}...')>"
    
    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "title": self.title,
            "catalogNumber": self.catalog_number,
            "catalogType": self.catalog_type,
            "classificationNumber": self.classification_number,
            "subject": self.subject,
            "author": self.author,
            "editor": self.editor,
            "publisher": self.publisher,
            "shelfNumber": self.shelf_number,
            "libraryLocation": self.library_location,
            "publicationYear": self.publication_year,
            "totalCopies": self.total_copies,
            "accessLink": self.access_link,
            "abstract": self.abstract,
        }
