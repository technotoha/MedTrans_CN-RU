"""
Data models for the PDF translation pipeline.
Defines structured representations for document elements, translations, and processing results.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum


class ElementType(str, Enum):
    """Types of document elements."""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    HEADER = "header"
    FOOTER = "footer"
    CAPTION = "caption"
    LIST_ITEM = "list_item"
    PARAGRAPH = "paragraph"


class ProcessingStatus(str, Enum):
    """Status of processing tasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BoundingBox(BaseModel):
    """Bounding box coordinates for element positioning."""
    x0: float
    y0: float
    x1: float
    y1: float
    
    @property
    def width(self) -> float:
        return self.x1 - self.x0
    
    @property
    def height(self) -> float:
        return self.y1 - self.y0


class TableData(BaseModel):
    """Structured table data."""
    rows: List[List[str]]
    headers: Optional[List[str]] = None
    caption: Optional[str] = None
    bounding_box: Optional[BoundingBox] = None
    
    def to_markdown(self) -> str:
        """Convert table to markdown format."""
        if not self.rows:
            return ""
        
        lines = []
        max_cols = max(len(row) for row in self.rows)
        
        # Header row
        header = self.headers or self.rows[0]
        header_line = "| " + " | ".join(str(cell) for cell in header[:max_cols]) + " |"
        lines.append(header_line)
        
        # Separator
        separator = "| " + " | ".join(["---"] * max_cols) + " |"
        lines.append(separator)
        
        # Data rows
        start_idx = 1 if self.headers else 1
        for row in self.rows[start_idx:]:
            row_line = "| " + " | ".join(str(cell) for cell in row[:max_cols]) + " |"
            lines.append(row_line)
        
        return "\n".join(lines)


class DocumentElement(BaseModel):
    """Represents a single element from the PDF."""
    id: str
    element_type: ElementType
    content: str
    page_number: int
    position: int  # Order on page
    bounding_box: Optional[BoundingBox] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # OCR-specific fields
    is_ocr: bool = False
    image_path: Optional[str] = None
    
    # Table-specific fields
    table_data: Optional[TableData] = None
    
    # Translation fields
    translated_content: Optional[str] = None
    translation_status: ProcessingStatus = ProcessingStatus.PENDING
    translation_notes: Optional[str] = None


class PageContent(BaseModel):
    """Represents all content from a single PDF page."""
    page_number: int
    elements: List[DocumentElement] = Field(default_factory=list)
    raw_text: str = ""
    has_images: bool = False
    has_tables: bool = False
    ocr_required: bool = False
    
    def add_element(self, element: DocumentElement):
        """Add an element to the page."""
        self.elements.append(element)
        if element.element_type == ElementType.TABLE:
            self.has_tables = True
        if element.element_type == ElementType.IMAGE or element.is_ocr:
            self.has_images = True
    
    def get_elements_by_type(self, element_type: ElementType) -> List[DocumentElement]:
        """Get all elements of a specific type."""
        return [e for e in self.elements if e.element_type == element_type]


class TranslationChunk(BaseModel):
    """A chunk of text for translation."""
    chunk_id: str
    elements: List[DocumentElement]
    source_text: str
    translated_text: Optional[str] = None
    status: ProcessingStatus = ProcessingStatus.PENDING
    retry_count: int = 0
    translation_notes: Optional[str] = None


class TranslationResult(BaseModel):
    """Result of translating a chunk or document."""
    chunk_id: Optional[str] = None
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    confidence_score: Optional[float] = None
    processing_time_ms: int
    model_used: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class DocumentMetadata(BaseModel):
    """Metadata about the processed document."""
    filename: str
    total_pages: int
    file_size_bytes: int
    created_at: datetime = Field(default_factory=datetime.now)
    processed_at: Optional[datetime] = None
    source_language: str = "zh"
    target_language: str = "ru"
    has_ocr: bool = False
    table_count: int = 0
    image_count: int = 0


class ProcessingReport(BaseModel):
    """Comprehensive report of the processing pipeline."""
    document: DocumentMetadata
    pages_processed: int
    elements_translated: int
    tables_extracted: int
    images_ocr_processed: int
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    processing_time_seconds: float
    status: ProcessingStatus
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
