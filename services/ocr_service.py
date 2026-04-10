"""
OCR service for processing scanned documents and images.
Uses Tesseract OCR with preprocessing for improved accuracy.
"""

import asyncio
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import io
import numpy as np
import cv2

from models.document_models import (
    DocumentElement, PageContent, ElementType,
    BoundingBox, TableData, ProcessingStatus
)
from config.settings import settings
from utils.logging_utils import get_logger, timer
from utils.image_utils import preprocess_image, cv2_to_pil


logger = get_logger(__name__)


class OCRService:
    """
    Optical Character Recognition service.
    
    Processes PDF pages and images to extract text using Tesseract OCR
    with advanced preprocessing for Chinese and Russian text.
    """
    
    def __init__(self):
        """Initialize the OCR service."""
        self.config = settings.ocr
        self.logger = logger
        
        # Configure Tesseract if path is specified
        # tesseract_cmd can be set via environment or config
        if hasattr(self.config, 'tesseract_path') and self.config.tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = self.config.tesseract_path
    
    @timer(logger, "OCR processing")
    async def process_pages(
        self,
        pages: List[PageContent],
        pdf_path: str,
        temp_dir: Path
    ) -> List[PageContent]:
        """
        Process pages that require OCR.
        
        Args:
            pages: List of page contents
            pdf_path: Path to source PDF
            temp_dir: Directory for temporary files
        
        Returns:
            Updated list of PageContent with OCR results
        """
        temp_dir = Path(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        ocr_count = 0
        for page in pages:
            if page.ocr_required:
                self.logger.info(f"Processing page {page.page_number} with OCR")
                await self._process_page_ocr(page, pdf_path, temp_dir)
                ocr_count += 1
        
        self.logger.info(f"OCR processed {ocr_count} pages")
        return pages
    
    async def _process_page_ocr(
        self,
        page: PageContent,
        pdf_path: str,
        temp_dir: Path
    ) -> None:
        """Process a single page with OCR."""
        # Render page to image
        doc = fitz.open(pdf_path)
        pdf_page = doc[page.page_number - 1]
        
        # High-resolution rendering for better OCR
        zoom = self.config.dpi / 72  # Convert DPI to zoom factor
        matrix = fitz.Matrix(zoom, zoom)
        pix = pdf_page.get_pixmap(matrix=matrix)
        
        # Save to temp file
        img_path = temp_dir / f"page_{page.page_number}.png"
        pix.save(str(img_path))
        
        doc.close()
        
        # Preprocess image
        if self.config.preprocess:
            try:
                processed_img, meta = preprocess_image(
                    str(img_path),
                    dpi=self.config.dpi
                )
                self.logger.debug(
                    f"Preprocessed page {page.page_number}: {meta['operations']}"
                )
                
                # Convert to PIL for Tesseract
                pil_img = cv2_to_pil(processed_img)
            except Exception as e:
                self.logger.warning(
                    f"Preprocessing failed for page {page.page_number}: {e}. Using original."
                )
                pil_img = Image.open(img_path)
        else:
            pil_img = Image.open(img_path)
        
        # Perform OCR
        ocr_text = await self._run_tesseract(pil_img)
        
        # Create OCR element
        if ocr_text.strip():
            ocr_element = DocumentElement(
                id=f"ocr_p{page.page_number}",
                element_type=ElementType.PARAGRAPH,
                content=ocr_text,
                page_number=page.page_number,
                position=0,
                is_ocr=True,
                metadata={"ocr_engine": "tesseract", "lang": self.config.lang}
            )
            
            # Add OCR text as primary content if no text was extracted
            if not page.elements or page.raw_text.strip() == "":
                page.elements.insert(0, ocr_element)
                page.raw_text = ocr_text
            else:
                # Append OCR text for reference/comparison
                page.raw_text += "\n\n[OCR Supplement]:\n" + ocr_text
        
        # Cleanup
        try:
            img_path.unlink()
        except Exception:
            pass
    
    async def _run_tesseract(self, image: Image.Image) -> str:
        """
        Run Tesseract OCR on an image.
        
        Args:
            image: PIL Image object
        
        Returns:
            Extracted text
        """
        loop = asyncio.get_event_loop()
        
        def run_ocr():
            custom_config = f'--oem {self.config.oem} --psm {self.config.psm}'
            text = pytesseract.image_to_string(
                image,
                lang=self.config.lang,
                config=custom_config
            )
            return text
        
        text = await loop.run_in_executor(None, run_ocr)
        return text
    
    async def process_image_ocr(
        self,
        image_path: str,
        element: DocumentElement
    ) -> DocumentElement:
        """
        Process a standalone image with OCR.
        
        Args:
            image_path: Path to image file
            element: DocumentElement to update
        
        Returns:
            Updated DocumentElement with OCR text
        """
        try:
            # Load and preprocess image
            if self.config.preprocess:
                processed_img, meta = preprocess_image(image_path)
                pil_img = cv2_to_pil(processed_img)
            else:
                pil_img = Image.open(image_path)
            
            # Run OCR
            ocr_text = await self._run_tesseract(pil_img)
            
            # Update element
            element.content = ocr_text
            element.is_ocr = True
            element.translation_status = ProcessingStatus.PENDING
            element.metadata["ocr_processed"] = True
            
            self.logger.debug(f"OCR extracted {len(ocr_text)} chars from image")
            
        except Exception as e:
            self.logger.error(f"OCR failed for image {image_path}: {e}")
            element.content = f"[OCR Error: {str(e)}]"
            element.metadata["ocr_error"] = str(e)
        
        return element
    
    async def extract_text_from_image_bytes(
        self,
        image_bytes: bytes,
        lang: Optional[str] = None
    ) -> str:
        """
        Extract text from image bytes.
        
        Args:
            image_bytes: Raw image data
            lang: Override language setting
        
        Returns:
            Extracted text
        """
        image = Image.open(io.BytesIO(image_bytes))
        
        if self.config.preprocess:
            # Convert to numpy for preprocessing
            img_array = np.array(image)
            if len(img_array.shape) == 3:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Temp save for preprocessing
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                temp_path = f.name
                cv2.imwrite(temp_path, img_array)
            
            try:
                processed, _ = preprocess_image(temp_path)
                image = cv2_to_pil(processed)
            finally:
                Path(temp_path).unlink(missing_ok=True)
        
        lang = lang or self.config.lang
        custom_config = f'--oem {self.config.oem} --psm {self.config.psm}'
        
        loop = asyncio.get_event_loop()
        
        def run_ocr():
            return pytesseract.image_to_string(
                image,
                lang=lang,
                config=custom_config
            )
        
        text = await loop.run_in_executor(None, run_ocr)
        return text
    
    @staticmethod
    def validate_tesseract() -> Tuple[bool, str]:
        """
        Validate Tesseract installation and language data.
        
        Returns:
            Tuple of (is_valid, message)
        """
        try:
            # Get Tesseract version
            version = pytesseract.get_tesseract_version()
            
            # Get available languages
            langs = pytesseract.get_languages(config='')
            
            required_langs = ['chi_sim', 'eng']  # Chinese Simplified and English
            missing = [l for l in required_langs if l not in langs]
            
            if missing:
                return False, f"Missing language packs: {missing}. Available: {langs}"
            
            return True, f"Tesseract v{version}, languages: {langs}"
            
        except Exception as e:
            return False, f"Tesseract validation failed: {e}"
