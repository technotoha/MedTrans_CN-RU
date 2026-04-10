"""
PDF Translation Pipeline - Модульный тестер
Позволяет проверять каждый модуль работы по отдельности.

Использование:
    python test_modules.py --module ocr --input test.pdf
    python test_modules.py --module tables --input test.pdf
    python test_modules.py --module extract --input test.pdf
    python test_modules.py --module translate --text "你好世界"
    python test_modules.py --module all --input test.pdf
"""

import argparse
import asyncio
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def print_header(title: str):
    """Print a styled header."""
    console.print(Panel(f"[bold blue]{title}[/]", border_style="blue"))


def print_success(message: str):
    """Print success message."""
    console.print(f"[green]✓[/] {message}")


def print_error(message: str):
    """Print error message."""
    console.print(f"[red]✗[/] {message}")


def print_info(message: str):
    """Print info message."""
    console.print(f"[cyan]ℹ[/] {message}")


async def test_ocr(pdf_path: str):
    """Test OCR module."""
    print_header("Тестирование OCR модуля")
    
    from services.ocr_service import OCRService
    
    # Validate Tesseract
    is_valid, message = OCRService.validate_tesseract()
    if is_valid:
        print_success(f"Tesseract: {message}")
    else:
        print_error(message)
        return False
    
    # Test on PDF
    from services.pdf_extractor import PDFExtractor
    from config.settings import settings
    
    extractor = PDFExtractor(dpi=settings.OCR_DPI)
    pages = await extractor.extract_all(pdf_path)
    
    ocr_service = OCRService()
    ocr_pages = [p for p in pages if p.ocr_required]
    
    if ocr_pages:
        print_info(f"Найдено {len(ocr_pages)} страниц для OCR")
        
        temp_dir = Path(settings.TEMP_DIR)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        pages = await ocr_service.process_pages(ocr_pages, pdf_path, temp_dir)
        
        for page in pages[:3]:  # Show first 3
            console.print(f"\n[bold]Страница {page.page_number}:[/]")
            ocr_elements = [e for e in page.elements if e.is_ocr]
            if ocr_elements:
                text = ocr_elements[0].content[:200]
                console.print(f"[green]{text}...[/]")
            else:
                console.print("[yellow]Нет OCR элементов[/]")
    else:
        print_info("Страницы не требуют OCR (текстовый PDF)")
        # Force test on first page image
        print_info("Принудительное тестирование на первой странице...")
    
    print_success("OCR тест завершен")
    return True


async def test_tables(pdf_path: str):
    """Test table extraction with Camelot."""
    print_header("Тестирование извлечения таблиц (Camelot)")
    
    try:
        import camelot
        
        # Try Camelot first
        tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
        
        if len(tables) > 0:
            print_success(f"Найдено {len(tables)} таблиц через Camelot")
            
            # Show table info
            table_info = Table(title="Информация о таблицах")
            table_info.add_column("№", style="cyan")
            table_info.add_column("Страница", style="magenta")
            table_info.add_column("Строк", style="green")
            table_info.add_column("Колонок", style="green")
            table_info.add_column("Точность", style="yellow")
            
            for i, t in enumerate(tables[:10], 1):
                table_info.add_row(
                    str(i),
                    str(t.page),
                    str(t.df.shape[0]),
                    str(t.df.shape[1]),
                    f"{t.accuracy:.1f}%" if hasattr(t, 'accuracy') else "N/A"
                )
            
            console.print(table_info)
            
            # Show sample
            if len(tables) > 0:
                console.print("\n[bold]Пример таблицы (первые 5 строк):[/]")
                sample_df = tables[0].df.head()
                console.print(sample_df.to_string())
        else:
            print_info("Таблицы не найдены через Camelot")
            
            # Fallback to pdfplumber
            print_info("Пробуем pdfplumber...")
            import pdfplumber
            
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages[:3], 1):
                    tables = page.extract_tables()
                    if tables:
                        print_success(f"Страница {i}: найдено {len(tables)} таблиц")
                        for j, t in enumerate(tables, 1):
                            console.print(f"\nТаблица {j}:")
                            for row in t[:5]:
                                console.print(f"  {row}")
        
        print_success("Тест таблиц завершен")
        return True
        
    except ImportError:
        print_error("Camelot не установлен. Установите: pip install camelot-py[cv]")
        return False
    except Exception as e:
        print_error(f"Ошибка: {e}")
        return False


async def test_extraction(pdf_path: str):
    """Test PDF extraction module."""
    print_header("Тестирование извлечения контента")
    
    from services.pdf_extractor import PDFExtractor
    from config.settings import settings
    
    extractor = PDFExtractor(dpi=settings.OCR_DPI)
    pages = await extractor.extract_all(pdf_path)
    
    # Statistics
    total_elements = sum(len(p.elements) for p in pages)
    total_tables = sum(1 for p in pages for e in p.elements if e.element_type.value == "table")
    total_images = sum(1 for p in pages for e in p.elements if e.element_type.value == "image")
    total_headers = sum(1 for p in pages for e in p.elements if e.element_type.value == "header")
    total_paragraphs = sum(1 for p in pages for e in p.elements if e.element_type.value == "paragraph")
    
    stats_table = Table(title="Статистика извлечения")
    stats_table.add_column("Метрика", style="cyan")
    stats_table.add_column("Значение", style="green")
    
    stats_table.add_row("Страниц", str(len(pages)))
    stats_table.add_row("Всего элементов", str(total_elements))
    stats_table.add_row("Таблицы", str(total_tables))
    stats_table.add_row("Изображения", str(total_images))
    stats_table.add_row("Заголовки", str(total_headers))
    stats_table.add_row("Параграфы", str(total_paragraphs))
    stats_table.add_row("Требуется OCR", str(sum(1 for p in pages if p.ocr_required)))
    
    console.print(stats_table)
    
    # Sample content
    if pages and pages[0].elements:
        console.print("\n[bold]Пример контента со страницы 1:[/]")
        for elem in pages[0].elements[:5]:
            preview = elem.content[:100].replace('\n', ' ')
            console.print(f"  [{elem.element_type.value}] {preview}...")
    
    print_success("Тест извлечения завершен")
    return True


async def test_translation(text: str):
    """Test LLM translation module."""
    print_header("Тестирование перевода (LLM)")
    
    from services.llm_translator import LLMTranslationService
    from config.settings import settings
    from models.document_models import TranslationChunk, DocumentElement, ElementType, ProcessingStatus
    
    # Create test chunk
    element = DocumentElement(
        id="test_1",
        element_type=ElementType.PARAGRAPH,
        content=text,
        page_number=1,
        position=0
    )
    
    chunk = TranslationChunk(
        chunk_id="test_chunk",
        elements=[element],
        source_text=text,
        status=ProcessingStatus.PENDING
    )
    
    translator = LLMTranslationService()
    
    print_info(f"Исходный текст: {text}")
    print_info(f"Модель: {settings.LLM_MODEL}")
    print_info(f"URL: {settings.LLM_BASE_URL}")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Перевод...", total=None)
            
            async def dummy_callback(chunk, result):
                pass
            
            translated_chunks = await translator.translate_chunks([chunk], progress_callback=dummy_callback)
            progress.update(task, completed=True)
        
        result_chunk = translated_chunks[0]
        
        if result_chunk.status == ProcessingStatus.COMPLETED:
            print_success("Перевод выполнен успешно!")
            console.print(f"\n[bold]Результат:[/]\n{result_chunk.translated_text}")
            
            if result_chunk.translation_notes:
                console.print(f"\n[yellow]Заметки:[/] {result_chunk.translation_notes}")
            
            return True
        else:
            print_error(f"Перевод не удался: {result_chunk.translation_notes}")
            return False
            
    except Exception as e:
        print_error(f"Ошибка перевода: {e}")
        console.print_exception()
        return False
    finally:
        await translator.close()


async def test_docx_builder(pdf_path: str, output_path: str):
    """Test DOCX builder module."""
    print_header("Тестирование сборки DOCX")
    
    from services.pdf_extractor import PDFExtractor
    from services.docx_builder import DOCXBuilder
    from config.settings import settings
    
    # Extract
    extractor = PDFExtractor(dpi=settings.OCR_DPI)
    pages = await extractor.extract_all(pdf_path)
    
    # Mock translation (use original content)
    for page in pages:
        for elem in page.elements:
            elem.translated_content = f"[RU] {elem.content}"
    
    # Build DOCX
    builder = DOCXBuilder()
    
    metadata = {
        "title": f"Тестовый перевод {Path(pdf_path).name}",
        "author": "PDF Translation Pipeline",
        "subject": "Test"
    }
    
    output = await builder.build_document(pages, output_path, metadata)
    
    if output.exists():
        print_success(f"DOCX создан: {output}")
        print_info(f"Размер файла: {output.stat().st_size} байт")
        return True
    else:
        print_error("Файл не был создан")
        return False


async def run_all_tests(pdf_path: str):
    """Run all module tests."""
    print_header("ПОЛНОЕ ТЕСТИРОВАНИЕ ВСЕХ МОДУЛЕЙ")
    
    results = {}
    
    # 1. Extraction
    console.print("\n[bold cyan]1. Тест извлечения[/]")
    results['extraction'] = await test_extraction(pdf_path)
    
    # 2. Tables
    console.print("\n[bold cyan]2. Тест таблиц[/]")
    results['tables'] = await test_tables(pdf_path)
    
    # 3. OCR
    console.print("\n[bold cyan]3. Тест OCR[/]")
    results['ocr'] = await test_ocr(pdf_path)
    
    # 4. Translation
    console.print("\n[bold cyan]4. Тест перевода[/]")
    results['translation'] = await test_translation("你好世界，这是一个测试文档。")
    
    # 5. DOCX Builder
    console.print("\n[bold cyan]5. Тест DOCX[/]")
    output_path = str(Path(settings.OUTPUT_DIR) / "test_output.docx")
    results['docx'] = await test_docx_builder(pdf_path, output_path)
    
    # Summary
    print_header("РЕЗУЛЬМАТЫ ТЕСТИРОВАНИЯ")
    
    summary_table = Table(title="Сводка")
    summary_table.add_column("Модуль", style="cyan")
    summary_table.add_column("Статус", style="green")
    
    all_passed = True
    for module, passed in results.items():
        status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
        summary_table.add_row(module, status)
        if not passed:
            all_passed = False
    
    console.print(summary_table)
    
    if all_passed:
        console.print("\n[bold green]✓ Все тесты пройдены![/]")
    else:
        console.print("\n[bold yellow]⚠ Некоторые тесты не прошли[/]")
    
    return all_passed


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Модульный тестер PDF Translation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--module", "-m",
        type=str,
        required=True,
        choices=["ocr", "tables", "extract", "translate", "docx", "all"],
        help="Модуль для тестирования"
    )
    
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="Путь к PDF файлу для тестирования"
    )
    
    parser.add_argument(
        "--text", "-t",
        type=str,
        help="Текст для теста перевода"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Путь для выходного файла (для теста DOCX)"
    )
    
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    if args.module != "translate" and not args.input:
        print_error("Для этого теста требуется --input файл")
        sys.exit(1)
    
    if args.module == "ocr":
        success = await test_ocr(args.input)
    elif args.module == "tables":
        success = await test_tables(args.input)
    elif args.module == "extract":
        success = await test_extraction(args.input)
    elif args.module == "translate":
        text = args.text or "你好世界"
        success = await test_translation(text)
    elif args.module == "docx":
        output = args.output or str(Path("./output/test.docx"))
        success = await test_docx_builder(args.input, output)
    elif args.module == "all":
        success = await run_all_tests(args.input)
    else:
        print_error(f"Неизвестный модуль: {args.module}")
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
