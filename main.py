#!/usr/bin/env python3
"""
Main entry point for the PDF Translation Pipeline.

Usage:
    python main.py --input document.pdf --output translated.docx
    python main.py --input-dir ./pdfs --output-dir ./translations
    python main.py --validate-ocr

Environment variables:
    LLM_API_KEY: Your OpenAI-compatible API key
    LLM_BASE_URL: API base URL (default: https://api.openai.com/v1)
    LLM_MODEL: Model to use (default: gpt-4o)
"""

import argparse
import asyncio
import sys
from pathlib import Path

from config.settings import settings
from utils.logging_utils import setup_logger
from core.pipeline import run_pipeline, TranslationPipeline


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="PDF Translation Pipeline (Chinese → Russian)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input document.pdf
  %(prog)s --input document.pdf --output translation.docx
  %(prog)s --input-dir ./documents --output-dir ./translations
  %(prog)s --validate-ocr

Environment Variables:
  LLM_API_KEY       Your API key for the LLM service
  LLM_BASE_URL      Base URL for LLM API (default: OpenAI)
  LLM_MODEL         Model name (default: gpt-4o)
  OCR_LANG          OCR languages (default: chi_sim+rus+eng)
        """
    )
    
    # Input/Output
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input", "-i",
        type=str,
        help="Path to a single PDF file"
    )
    input_group.add_argument(
        "--input-dir", "-d",
        type=str,
        help="Path to directory containing PDF files"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output path for DOCX file (single file mode)"
    )
    parser.add_argument(
        "--output-dir", "-D",
        type=str,
        help="Output directory for translated files (directory mode)"
    )
    
    # Configuration
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="LLM model to use (overrides config)"
    )
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        default=None,
        help="LLM API key (overrides environment)"
    )
    parser.add_argument(
        "--log-level", "-l",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    # Utilities
    parser.add_argument(
        "--validate-ocr",
        action="store_true",
        help="Validate Tesseract OCR installation and exit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate input without processing"
    )
    
    return parser.parse_args()


async def validate_ocr():
    """Validate OCR installation."""
    from services.ocr_service import OCRService
    
    print("Validating Tesseract OCR installation...")
    is_valid, message = OCRService.validate_tesseract()
    
    if is_valid:
        print(f"✓ {message}")
        return True
    else:
        print(f"✗ {message}")
        print("\nTo install Tesseract:")
        print("  Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-rus")
        print("  macOS: brew install tesseract tesseract-lang")
        print("  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki")
        return False


async def process_single_file(input_path: str, output_path: str, args):
    """Process a single PDF file."""
    input_file = Path(input_path)
    
    if not input_file.exists():
        print(f"Error: File not found: {input_file}")
        return False
    
    print(f"\n{'='*60}")
    print(f"Processing: {input_file.name}")
    print(f"{'='*60}\n")
    
    try:
        report = await run_pipeline(
            pdf_path=str(input_file),
            output_path=output_path,
            api_key=args.api_key,
            llm_model=args.model
        )
        
        # Print summary
        print(f"\n{'='*60}")
        print("PROCESSING COMPLETE")
        print(f"{'='*60}")
        print(f"Pages processed:     {report.pages_processed}")
        print(f"Elements translated: {report.elements_translated}")
        print(f"Tables extracted:    {report.tables_extracted}")
        print(f"OCR images:          {report.images_ocr_processed}")
        print(f"Processing time:     {report.processing_time_seconds:.2f}s")
        print(f"Output file:         {output_path}")
        
        if report.errors:
            print(f"\nErrors: {len(report.errors)}")
            for error in report.errors:
                print(f"  - {error}")
        
        if report.warnings:
            print(f"\nWarnings: {len(report.warnings)}")
        
        return report.status.value == "completed"
        
    except Exception as e:
        print(f"\nError: {e}")
        return False


async def process_directory(input_dir: str, output_dir: str, args):
    """Process all PDF files in a directory."""
    input_path = Path(input_dir)
    
    if not input_path.exists():
        print(f"Error: Directory not found: {input_path}")
        return False
    
    if not input_path.is_dir():
        print(f"Error: Not a directory: {input_path}")
        return False
    
    pdf_files = list(input_path.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in {input_path}")
        return False
    
    print(f"\n{'='*60}")
    print(f"Found {len(pdf_files)} PDF files to process")
    print(f"{'='*60}\n")
    
    pipeline = TranslationPipeline()
    
    success_count = 0
    fail_count = 0
    
    for idx, pdf_file in enumerate(pdf_files, 1):
        print(f"\n[{idx}/{len(pdf_files)}] Processing: {pdf_file.name}")
        
        output_path = Path(output_dir) / f"{pdf_file.stem}_translated.docx"
        
        try:
            report = await pipeline.process_file(
                str(pdf_file),
                str(output_path)
            )
            
            if report.status.value == "completed":
                success_count += 1
                print(f"  ✓ Completed in {report.processing_time_seconds:.2f}s")
            else:
                fail_count += 1
                print(f"  ✗ Failed: {report.errors}")
                
        except Exception as e:
            fail_count += 1
            print(f"  ✗ Error: {e}")
        
        finally:
            await pipeline.cleanup()
    
    print(f"\n{'='*60}")
    print(f"BATCH PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"Total files:    {len(pdf_files)}")
    print(f"Successful:     {success_count}")
    print(f"Failed:         {fail_count}")
    
    return fail_count == 0


async def main():
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    log_file = Path("./logs/pipeline.log")
    setup_logger(
        log_level=args.log_level,
        log_file=log_file,
        console_output=True
    )
    
    # Handle OCR validation
    if args.validate_ocr:
        success = await validate_ocr()
        sys.exit(0 if success else 1)
    
    # Check API key
    if not settings.llm.api_key and not args.api_key:
        print("Warning: No LLM_API_KEY set. Translation will fail.")
        print("Set the environment variable or use --api-key flag.")
        
        if args.dry_run:
            print("Dry run mode - continuing without API key")
        # else:
        #     print("\nTo get an API key:")
        #     print("  - OpenAI: https://platform.openai.com/api-keys")
        #     print("  - Or use any OpenAI-compatible service")
        #     sys.exit(1)
    
    # Process based on mode
    if args.input:
        output_path = args.output or f"./output/{Path(args.input).stem}_translated.docx"
        success = await process_single_file(args.input, output_path, args)
    elif args.input_dir:
        output_dir = args.output_dir or "./output"
        success = await process_directory(args.input_dir, output_dir, args)
    else:
        print("Error: Either --input or --input-dir is required")
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
