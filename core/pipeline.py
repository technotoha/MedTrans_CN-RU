"""
Core translation pipeline orchestrator.
Coordinates all services to process PDF documents end-to-end.
"""

import asyncio
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from models.document_models import (
    PageContent, DocumentElement, TranslationChunk,
    DocumentMetadata, ProcessingReport, ProcessingStatus, ElementType
)
from config.settings import settings, Settings
from services.pdf_extractor import PDFExtractor
from services.ocr_service import OCRService
from services.llm_translator import LLMTranslationService
from services.docx_builder import DOCXBuilder
from utils.chunking_utils import smart_chunk_elements, merge_chunks_by_page
from utils.logging_utils import setup_logger, get_logger


logger = get_logger(__name__)


class TranslationPipeline:
    """
    Main pipeline orchestrator for PDF translation.
    
    Coordinates the complete workflow:
    1. PDF extraction
    2. OCR processing (if needed)
    3. Text chunking
    4. LLM translation
    5. DOCX reconstruction
    
    Features:
    - Async processing for efficiency
    - Progress tracking
    - Error handling and recovery
    - Detailed reporting
    """
    
    def __init__(self, custom_settings: Optional[Settings] = None):
        """
        Initialize the translation pipeline.
        
        Args:
            custom_settings: Optional custom configuration
        """
        self.settings = custom_settings or settings
        self.logger = logger
        
        # Initialize services
        self.extractor = PDFExtractor(dpi=self.settings.ocr.dpi)
        self.ocr_service = OCRService()
        self.translator = LLMTranslationService()
        self.docx_builder = DOCXBuilder()
        
        # State tracking
        self.pages: List[PageContent] = []
        self.chunks: List[TranslationChunk] = []
        self.report: Optional[ProcessingReport] = None
        self.start_time: Optional[float] = None
    
    async def process_file(
        self,
        pdf_path: str,
        output_path: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> ProcessingReport:
        """
        Process a single PDF file through the complete pipeline.
        
        Args:
            pdf_path: Path to input PDF
            output_path: Path for output DOCX (optional, auto-generated if not provided)
            progress_callback: Optional callback(stage, progress) for UI updates
        
        Returns:
            ProcessingReport with results and statistics
        """
        self.start_time = time.time()
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        self.logger.info(f"Starting pipeline for: {pdf_path.name}")
        
        # Generate output path if not provided
        if not output_path:
            output_dir = Path(self.settings.pipeline.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{pdf_path.stem}_translated.docx"
        
        try:
            # Stage 1: Extract content from PDF
            if progress_callback:
                await progress_callback("extract", 0.0)
            
            self.logger.info("Stage 1: Extracting content from PDF")
            self.pages = await self.extractor.extract_all(str(pdf_path))
            
            if progress_callback:
                await progress_callback("extract", 1.0)
            
            # Stage 2: OCR processing for scanned pages
            ocr_pages = sum(1 for p in self.pages if p.ocr_required)
            if ocr_pages > 0:
                if progress_callback:
                    await progress_callback("ocr", 0.0)
                
                self.logger.info(f"Stage 2: Processing {ocr_pages} pages with OCR")
                temp_dir = Path(self.settings.pipeline.temp_dir)
                self.pages = await self.ocr_service.process_pages(
                    self.pages, 
                    str(pdf_path),
                    temp_dir
                )
                
                if progress_callback:
                    await progress_callback("ocr", 1.0)
            
            # Stage 3: Prepare elements for translation
            if progress_callback:
                await progress_callback("chunking", 0.0)
            
            self.logger.info("Stage 3: Preparing text chunks for translation")
            self.chunks = await self._prepare_chunks()
            
            if progress_callback:
                await progress_callback("chunking", 1.0)
            
            # Stage 4: Translate chunks
            if progress_callback:
                await progress_callback("translate", 0.0)
            
            self.logger.info(f"Stage 4: Translating {len(self.chunks)} chunks")
            self.chunks = await self.translator.translate_chunks(
                self.chunks,
                progress_callback=self._translation_progress
            )
            
            if progress_callback:
                await progress_callback("translate", 1.0)
            
            # Stage 5: Build DOCX document
            if progress_callback:
                await progress_callback("build", 0.0)
            
            self.logger.info("Stage 5: Building DOCX document")
            metadata = self._create_metadata(pdf_path)
            await self.docx_builder.build_document(
                self.pages,
                str(output_path),
                metadata
            )
            
            if progress_callback:
                await progress_callback("build", 1.0)
            
            # Generate report
            self.report = self._generate_report(pdf_path, output_path)
            
            self.logger.info(
                f"Pipeline completed successfully! Output: {output_path}"
            )
            
            return self.report
            
        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}", exc_info=True)
            
            # Generate error report
            self.report = self._generate_report(
                pdf_path, 
                output_path, 
                status=ProcessingStatus.FAILED,
                errors=[str(e)]
            )
            
            raise
    
    async def process_directory(
        self,
        input_dir: str,
        output_dir: Optional[str] = None,
        pattern: str = "*.pdf",
        progress_callback: Optional[callable] = None
    ) -> List[ProcessingReport]:
        """
        Process multiple PDF files in a directory.
        
        Args:
            input_dir: Directory containing PDF files
            output_dir: Output directory (optional)
            pattern: Glob pattern for files
            progress_callback: Optional callback(file, stage, progress)
        
        Returns:
            List of ProcessingReport for each file
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir) if output_dir else Path(self.settings.pipeline.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_files = list(input_dir.glob(pattern))
        
        if not pdf_files:
            self.logger.warning(f"No PDF files found in {input_dir}")
            return []
        
        self.logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        reports = []
        for idx, pdf_file in enumerate(pdf_files):
            self.logger.info(f"Processing file {idx + 1}/{len(pdf_files)}: {pdf_file.name}")
            
            output_path = output_dir / f"{pdf_file.stem}_translated.docx"
            
            try:
                report = await self.process_file(
                    str(pdf_file),
                    str(output_path),
                    progress_callback
                )
                reports.append(report)
                
            except Exception as e:
                self.logger.error(f"Failed to process {pdf_file.name}: {e}")
                # Continue with next file
                continue
        
        return reports
    
    async def _prepare_chunks(self) -> List[TranslationChunk]:
        """Prepare text chunks from extracted elements."""
        all_elements = []
        
        for page in self.pages:
            # Get translatable elements
            for element in page.elements:
                if element.element_type in [
                    ElementType.TEXT,
                    ElementType.PARAGRAPH,
                    ElementType.HEADER,
                    ElementType.TABLE,
                    ElementType.LIST_ITEM
                ]:
                    # Skip already translated or empty elements
                    if element.content.strip():
                        all_elements.append(element)
        
        # Create chunks with smart splitting
        chunks = smart_chunk_elements(
            all_elements,
            max_chars=self.settings.pipeline.chunk_size,
            overlap_chars=self.settings.pipeline.overlap_size,
            respect_structure=True
        )
        
        self.logger.info(f"Created {len(chunks)} translation chunks")
        return chunks
    
    async def _translation_progress(self, chunk: TranslationChunk, result):
        """Handle translation progress updates."""
        completed = sum(
            1 for c in self.chunks 
            if c.status == ProcessingStatus.COMPLETED
        )
        total = len(self.chunks)
        progress = completed / total if total > 0 else 0
        
        self.logger.debug(
            f"Translation progress: {completed}/{total} ({progress:.1%})"
        )
    
    def _create_metadata(self, pdf_path: Path) -> Dict[str, Any]:
        """Create document metadata."""
        return {
            "title": f"Translation of {pdf_path.name}",
            "subject": "Chinese to Russian Translation",
            "author": "PDF Translation Pipeline"
        }
    
    def _generate_report(
        self,
        pdf_path: Path,
        output_path: Path,
        status: ProcessingStatus = ProcessingStatus.COMPLETED,
        errors: Optional[List[str]] = None
    ) -> ProcessingReport:
        """Generate comprehensive processing report."""
        processing_time = time.time() - self.start_time if self.start_time else 0
        
        # Count statistics
        elements_translated = sum(
            1 for c in self.chunks 
            if c.status == ProcessingStatus.COMPLETED
        )
        
        tables_extracted = sum(
            1 for p in self.pages 
            for e in p.elements 
            if e.element_type == ElementType.TABLE
        )
        
        images_ocr = sum(
            1 for p in self.pages 
            for e in p.elements 
            if e.is_ocr
        )
        
        # Collect warnings and errors
        all_warnings = []
        for chunk in self.chunks:
            if chunk.translation_notes:
                all_warnings.append(f"Chunk {chunk.chunk_id}: {chunk.translation_notes}")
        
        metadata = DocumentMetadata(
            filename=pdf_path.name,
            total_pages=len(self.pages),
            file_size_bytes=pdf_path.stat().st_size if pdf_path.exists() else 0,
            created_at=datetime.now(),
            processed_at=datetime.now()
        )
        
        report = ProcessingReport(
            document=metadata,
            pages_processed=len(self.pages),
            elements_translated=elements_translated,
            tables_extracted=tables_extracted,
            images_ocr_processed=images_ocr,
            errors=errors or [],
            warnings=all_warnings,
            processing_time_seconds=processing_time,
            status=status
        )
        
        return report
    
    async def cleanup(self):
        """Clean up resources."""
        await self.translator.close()
        
        # Clean temp directory
        temp_dir = Path(self.settings.pipeline.temp_dir)
        if temp_dir.exists():
            try:
                for f in temp_dir.glob("*"):
                    f.unlink()
                temp_dir.rmdir()
            except Exception as e:
                self.logger.warning(f"Failed to clean temp directory: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            "pages_extracted": len(self.pages),
            "chunks_created": len(self.chunks),
            "chunks_translated": sum(
                1 for c in self.chunks 
                if c.status == ProcessingStatus.COMPLETED
            ),
            "report_available": self.report is not None
        }


async def run_pipeline(
    pdf_path: str,
    output_path: Optional[str] = None,
    api_key: Optional[str] = None,
    llm_model: Optional[str] = None
) -> ProcessingReport:
    """
    Convenience function to run the translation pipeline.
    
    Args:
        pdf_path: Path to input PDF
        output_path: Path for output DOCX
        api_key: LLM API key (overrides environment)
        llm_model: LLM model name (overrides config)
    
    Returns:
        ProcessingReport with results
    """
    # Setup logging
    setup_logger(
        log_level=settings.pipeline.log_level,
        log_file=settings.pipeline.log_file
    )
    
    # Override settings if provided
    if api_key:
        settings.llm.api_key = api_key
    if llm_model:
        settings.llm.model = llm_model
    
    # Create and run pipeline
    pipeline = TranslationPipeline()
    
    try:
        report = await pipeline.process_file(pdf_path, output_path)
        return report
    finally:
        await pipeline.cleanup()
