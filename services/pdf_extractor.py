"""
PDF extraction service.
Extracts text, tables, and images from PDF documents using PyMuPDF and pdfplumber.
"""

import asyncio
import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import io
import hashlib

from models.document_models import (
    DocumentElement, PageContent, ElementType, 
    BoundingBox, TableData, ProcessingStatus
)
from utils.logging_utils import get_logger, timer


logger = get_logger(__name__)


class PDFExtractor:
    """
    Extract content from PDF files.
    
    Handles text extraction, table detection, and image extraction
    with position information for later reconstruction.
    """
    
    def __init__(self, dpi: int = 300):
        """
        Initialize the PDF extractor.
        
        Args:
            dpi: DPI for image rendering
        """
        self.dpi = dpi
        self.logger = logger
    
    @timer(logger, "PDF extraction")
    async def extract_all(self, pdf_path: str) -> List[PageContent]:
        """
        Extract all content from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
        
        Returns:
            List of PageContent objects for each page
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        pages = []
        
        # Use fitz for main extraction (faster)
        doc = fitz.open(pdf_path)
        self.logger.info(f"Opened PDF: {pdf_path.name}, {len(doc)} pages")
        
        for page_num in range(len(doc)):
            page_content = await self._extract_page(doc, page_num)
            pages.append(page_content)
        
        doc.close()
        
        self.logger.info(f"Extracted {len(pages)} pages")
        return pages
    
    async def _extract_page(
        self, 
        doc: fitz.Document, 
        page_num: int
    ) -> PageContent:
        """Extract content from a single page."""
        page = doc[page_num]
        page_content = PageContent(page_number=page_num + 1)
        
        # Extract text blocks with positions
        text_elements = self._extract_text_blocks(page, page_num)
        for elem in text_elements:
            page_content.add_element(elem)
        
        # Extract tables using pdfplumber for better accuracy
        table_elements = await self._extract_tables(doc, page_num)
        for elem in table_elements:
            page_content.add_element(elem)
        
        # Extract images
        image_elements = self._extract_images(page, page_num)
        for elem in image_elements:
            page_content.add_element(elem)
        
        # Get raw text for fallback
        page_content.raw_text = page.get_text()
        
        # Determine if OCR is needed
        # OCR needed if: very little text extracted or many images
        text_density = len(page_content.raw_text.strip()) / (page.rect.width * page.rect.height)
        page_content.ocr_required = (
            text_density < 0.001 or 
            (page_content.has_images and text_density < 0.01)
        )
        
        # Log table count
        table_count = len([e for e in page_content.elements if e.element_type == ElementType.TABLE])
        if table_count > 0:
            self.logger.info(f"Page {page_num + 1}: Found {table_count} table(s)")
        
        if page_content.ocr_required:
            self.logger.debug(
                f"Page {page_num + 1} marked for OCR "
                f"(text_density={text_density:.4f}, has_images={page_content.has_images})"
            )
        
        return page_content
    
    def _extract_text_blocks(
        self, 
        page: fitz.Page, 
        page_num: int
    ) -> List[DocumentElement]:
        """Extract text blocks with structure information."""
        elements = []
        
        # Get text as dict with spans - use rawdict for better character handling
        blocks = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        
        position = 0
        for block in blocks:
            if block["type"] == 0:  # Text block
                block_text = ""
                min_y = float('inf')
                max_y = 0
                min_x = float('inf')
                max_x = 0
                font_size = 12  # default
                
                for line in block.get("lines", []):
                    line_text = ""
                    for span in line.get("spans", []):
                        # Try to get text from chars if span text is missing/garbled
                        span_text = span.get("text", "")
                        if not span_text or all(c == '·' for c in span_text):
                            # Fallback: reconstruct from chars
                            chars = span.get("chars", [])
                            span_text = "".join(c.get("c", "") for c in chars)
                        
                        line_text += span_text
                        if span.get("size"):
                            font_size = span["size"]
                    
                    bbox = line.get("bbox", [])
                    if bbox:
                        min_y = min(min_y, bbox[1])
                        max_y = max(max_y, bbox[3])
                        min_x = min(min_x, bbox[0])
                        max_x = max(max_x, bbox[2])
                    
                    block_text += line_text + "\n"
                
                block_text = block_text.strip()
                if not block_text:
                    continue
                
                # Determine element type based on font size and position
                element_type = ElementType.PARAGRAPH
                
                # Check if it might be a header (larger font, top of page)
                if font_size > 16 and min_y < page.rect.height * 0.1:
                    element_type = ElementType.HEADER
                elif font_size > 14:
                    element_type = ElementType.HEADER
                
                bbox = BoundingBox(
                    x0=min_x if min_x != float('inf') else 0,
                    y0=min_y if min_y != float('inf') else 0,
                    x1=max_x if max_x != float('inf') else 0,
                    y1=max_y if max_y != float('inf') else 0
                )
                
                element = DocumentElement(
                    id=self._generate_id(block_text, page_num, position),
                    element_type=element_type,
                    content=block_text,
                    page_number=page_num + 1,
                    position=position,
                    bounding_box=bbox,
                    metadata={"font_size": font_size}
                )
                elements.append(element)
                position += 1
        
        return elements
    
    async def _extract_tables(
        self,
        doc: fitz.Document,
        page_num: int
    ) -> List[DocumentElement]:
        """Extract tables using pdfplumber for better accuracy."""
        elements = []
        
        # pdfplumber needs to be opened separately
        with pdfplumber.open(doc.name) as pdf:
            if page_num >= len(pdf.pages):
                return elements
            
            pdf_page = pdf.pages[page_num]
            tables = pdf_page.extract_tables()
            
            for table_idx, table_data in enumerate(tables):
                if not table_data:
                    continue
                
                # Clean table data
                cleaned_rows = []
                for row in table_data:
                    cleaned_row = [str(cell) if cell is not None else "" for cell in row]
                    cleaned_rows.append(cleaned_row)
                
                if not cleaned_rows:
                    continue
                
                # Try to detect headers (first row often has different style)
                headers = None
                if len(cleaned_rows) > 1:
                    # Heuristic: if first row has fewer empty cells, it's likely a header
                    first_row_empty = sum(1 for c in cleaned_rows[0] if not c.strip())
                    if first_row_empty < len(cleaned_rows[0]) * 0.5:
                        headers = cleaned_rows[0]
                        data_rows = cleaned_rows[1:]
                    else:
                        data_rows = cleaned_rows
                else:
                    data_rows = cleaned_rows
                
                table = TableData(
                    rows=data_rows,
                    headers=headers,
                    caption=f"Table {table_idx + 1}"
                )
                
                element = DocumentElement(
                    id=f"table_p{page_num + 1}_t{table_idx}",
                    element_type=ElementType.TABLE,
                    content=table.to_markdown(),
                    page_number=page_num + 1,
                    position=len(elements),
                    table_data=table,
                    metadata={"row_count": len(data_rows), "col_count": len(data_rows[0]) if data_rows else 0}
                )
                elements.append(element)
        
        return elements
    
    def _extract_images(
        self,
        page: fitz.Page,
        page_num: int
    ) -> List[DocumentElement]:
        """Extract images from the page."""
        elements = []
        image_list = page.get_images(full=True)
        
        for img_idx, img_info in enumerate(image_list):
            try:
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)
                
                if not base_image:
                    continue
                
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Save image temporarily for OCR processing
                img_hash = hashlib.md5(image_bytes).hexdigest()[:8]
                image_filename = f"img_p{page_num + 1}_{img_idx}_{img_hash}.{image_ext}"
                
                # Get image dimensions and position
                img_rect = None
                for rect in page.get_image_rects(xref):
                    img_rect = rect
                    break
                
                bbox = None
                if img_rect:
                    bbox = BoundingBox(
                        x0=img_rect.x0,
                        y0=img_rect.y0,
                        x1=img_rect.x1,
                        y1=img_rect.y1
                    )
                
                element = DocumentElement(
                    id=f"image_p{page_num + 1}_{img_idx}",
                    element_type=ElementType.IMAGE,
                    content=f"[Image {img_idx + 1}]",
                    page_number=page_num + 1,
                    position=img_idx,
                    bounding_box=bbox,
                    is_ocr=False,
                    image_path=image_filename,
                    metadata={
                        "width": base_image.get("width"),
                        "height": base_image.get("height"),
                        "ext": image_ext
                    }
                )
                elements.append(element)
                
            except Exception as e:
                self.logger.warning(f"Failed to extract image {img_idx} from page {page_num + 1}: {e}")
        
        return elements
    
    def _generate_id(
        self, 
        content: str, 
        page_num: int, 
        position: int
    ) -> str:
        """Generate a unique ID for an element."""
        content_hash = hashlib.md5(content[:100].encode()).hexdigest()[:8]
        return f"text_p{page_num + 1}_{position}_{content_hash}"
    
    async def save_images(
        self, 
        pages: List[PageContent], 
        output_dir: Path
    ) -> Dict[str, str]:
        """
        Save extracted images to disk.
        
        Args:
            pages: List of page contents
            output_dir: Directory to save images
        
        Returns:
            Mapping of image filenames to full paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        image_paths = {}
        
        for page in pages:
            for elem in page.elements:
                if elem.element_type == ElementType.IMAGE and elem.image_path:
                    # Need to re-extract image - this is a simplification
                    # In practice, you'd store the image bytes in the element
                    pass
        
        return image_paths
