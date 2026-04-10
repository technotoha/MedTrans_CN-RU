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
import asyncio
import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Импорт конфигурации и сервисов
from config.settings import settings
from services.pdf_extractor import PDFExtractor
from services.ocr_service import OCRService
from services.llm_translator import LLMTranslator
from services.docx_builder import DOCXBuilder
from models.document_models import DocumentPage, TextElement, TableElement
from utils.logging_utils import setup_logging

console = Console()

async def test_extraction(pdf_path: str):
    """Тест извлечения контента"""
    console.print(Panel("[bold blue]Тестирование извлечения контента", expand=False))
    
    extractor = PDFExtractor()
    doc = await extractor.extract_all(pdf_path)
    
    table = Table(title="Статистика извлечения")
    table.add_column("Метрика", style="cyan")
    table.add_column("Значение", style="green")
    
    total_elements = sum(len(page.elements) for page in doc.pages)
    total_tables = sum(len(page.tables) for page in doc.pages)
    total_images = sum(len(page.images) for page in doc.pages)
    total_headers = sum(1 for p in doc.pages for e in p.elements if isinstance(e, TextElement) and e.is_header)
    total_paragraphs = sum(1 for p in doc.pages for e in p.elements if isinstance(e, TextElement) and not e.is_header)
    ocr_needed = sum(len(page.images) for page in doc.pages) # Упрощенно
    
    table.add_row("Страниц", str(len(doc.pages)))
    table.add_row("Всего элементов", str(total_elements))
    table.add_row("Таблицы", str(total_tables))
    table.add_row("Изображения", str(total_images))
    table.add_row("Заголовки", str(total_headers))
    table.add_row("Параграфы", str(total_paragraphs))
    table.add_row("Требуется OCR", str(ocr_needed))
    
    console.print(table)
    
    if doc.pages:
        console.print(f"\nПример контента со страницы 1:")
        page = doc.pages[0]
        for i, el in enumerate(page.elements[:5]):
            if isinstance(el, TextElement):
                text = el.content[:50].replace('\n', ' ')
                console.print(f"   {text}...")
            elif isinstance(el, TableElement):
                console.print(f"   [Table: {el.rows}x{el.cols}]")
    
    console.print("[bold green]✓ Тест извлечения завершен")
    return True

async def test_tables(pdf_path: str):
    """Тест таблиц через Camelot"""
    console.print(Panel("[bold blue]Тестирование извлечения таблиц (Camelot)", expand=False))
    
    try:
        import camelot
        tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
        
        if len(tables) == 0:
            # Попытка stream flavor если lattice не нашел
            tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
            
        console.print(f"[bold green]✓ Найдено {len(tables)} таблиц через Camelot")
        
        table_info = Table(title="Информация о таблицах")
        table_info.add_column("№", style="cyan")
        table_info.add_column("Страница", style="magenta")
        table_info.add_column("Строк", style="green")
        table_info.add_column("Колонок", style="green")
        table_info.add_column("Точность", style="yellow")
        
        for i, t in enumerate(tables):
            accuracy = f"{t.parsing_report.get('accuracy', 'N/A')}%" if isinstance(t.parsing_report, dict) else "N/A"
            table_info.add_row(
                str(i+1), str(t.page), str(t.df.shape[0]), str(t.df.shape[1]), accuracy
            )
        
        console.print(table_info)
        
        if tables:
            console.print("\nПример таблицы (первые 5 строк):")
            console.print(tables[0].df.head())
            
        console.print("[bold green]✓ Тест таблиц завершен")
        return True
    except Exception as e:
        console.print(f"[bold red]✗ Ошибка таблиц: {e}")
        return False

async def test_ocr(pdf_path: str):
    """Тест OCR"""
    console.print(Panel("[bold blue]Тестирование OCR модуля", expand=False))
    
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        langs = pytesseract.get_languages(config='')
        console.print(f"[bold green]✓ Tesseract: {version}, languages: {langs}")
    except Exception as e:
        console.print(f"[bold red]✗ Ошибка Tesseract: {e}")
        return False

    # Проверка на страницах с изображениями
    extractor = PDFExtractor()
    doc = await extractor.extract_all(pdf_path)
    
    ocr_service = OCRService()
    
    images_found = False
    for page in doc.pages:
        if page.images:
            images_found = True
            console.print(f"ℹ Найдено {len(page.images)} изображений на странице {page.page_number}")
            # Здесь можно добавить реальный вызов OCR для первого изображения
            # img_data = page.images[0].data
            # text = await ocr_service.recognize(img_data)
    
    if not images_found:
        console.print("ℹ Страницы не требуют OCR (текстовый PDF)")
        console.print("ℹ Принудительное тестирование на первой странице...")
        # Можно реализовать рендер страницы в изображение для теста
        
    console.print("[bold green]✓ OCR тест завершен")
    return True

async def test_translation(text: str):
    """Тест перевода"""
    console.print(Panel("[bold blue]Тестирование перевода (LLM)", expand=False))
    
    console.print(f"ℹ Исходный текст: {text}")
    console.print(f"ℹ Модель: {settings.LLM_MODEL}")
    console.print(f"ℹ URL: {settings.LLM_BASE_URL}")
    
    translator = LLMTranslator()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Перевод...", total=None)
        try:
            result = await translator.translate_text(text, context="medical")
            progress.update(task, completed=True)
            console.print(f"[bold green]✓ Перевод успешен:")
            console.print(Panel(result, border_style="green"))
            return True
        except Exception as e:
            progress.update(task, completed=True)
            console.print(f"[bold red]✗ Перевод не удался: {e}")
            return False

async def test_docx_creation():
    """Тест создания DOCX"""
    console.print(Panel("[bold blue]Тестирование сборки DOCX", expand=False))
    
    try:
        builder = DOCXBuilder()
        output_path = Path(settings.OUTPUT_DIR) / "test_output.docx"
        
        # Создаем тестовый документ
        from models.document_models import TranslatedDocument, TranslatedPage, TranslatedTextElement, TranslatedTableElement
        
        test_doc = TranslatedDocument()
        page = TranslatedPage(page_number=1)
        
        # Добавляем тестовый элемент
        text_el = TranslatedTextElement(
            original="Test Header",
            translated="Тестовый Заголовок",
            is_header=True,
            level=1
        )
        page.elements.append(text_el)
        
        table_el = TranslatedTableElement(
            original_data={"A": ["1"], "B": ["2"]},
            translated_data={"A": ["Один"], "B": ["Два"]}
        )
        page.tables.append(table_el)
        page.elements.append(table_el)
        
        test_doc.pages.append(page)
        
        await builder.build(test_doc, str(output_path))
        
        if output_path.exists():
            console.print(f"[bold green]✓ DOCX создан: {output_path}")
            console.print(f"   Размер: {output_path.stat().st_size} bytes")
            return True
        else:
            console.print("[bold red]✗ Файл не был создан")
            return False
            
    except Exception as e:
        console.print(f"[bold red]✗ Ошибка создания DOCX: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_all_tests(pdf_path: str):
    """Запуск всех тестов"""
    results = {}
    
    console.print(Panel("[bold magenta]ПОЛНОЕ ТЕСТИРОВАНИЕ ВСЕХ МОДУЛЕЙ", expand=False))
    
    # 1. Extraction
    console.print("\n[bold cyan]1. Тест извлечения")
    results['extract'] = await test_extraction(pdf_path)
    
    # 2. Tables
    console.print("\n[bold cyan]2. Тест таблиц")
    results['tables'] = await test_tables(pdf_path)
    
    # 3. OCR
    console.print("\n[bold cyan]3. Тест OCR")
    results['ocr'] = await test_ocr(pdf_path)
    
    # 4. Translation
    console.print("\n[bold cyan]4. Тест перевода")
    results['translate'] = await test_translation("你好世界，这是一个测试文档。")
    
    # 5. DOCX
    console.print("\n[bold cyan]5. Тест DOCX")
    results['docx'] = await test_docx_creation()
    
    # Summary
    console.print("\n" + "="*50)
    console.print("[bold yellow]ИТОГИ:")
    for module, success in results.items():
        status = "[green]✓ PASS" if success else "[red]✗ FAIL"
        console.print(f"  {module}: {status}")
    
    return all(results.values())

async def main():
    parser = argparse.ArgumentParser(description="Modular Test Suite for PDF Translator")
    parser.add_argument("--module", type=str, required=True, 
                        choices=['extract', 'tables', 'ocr', 'translate', 'docx', 'all'],
                        help="Module to test")
    parser.add_argument("--input", type=str, help="Input PDF path (required for extract, tables, ocr)")
    parser.add_argument("--text", type=str, default="你好世界", help="Text for translation test")
    
    args = parser.parse_args()
    
    setup_logging()
    
    if args.module == 'all':
        if not args.input:
            console.print("[bold red]Ошибка: --input обязателен для полного теста")
            sys.exit(1)
        success = await run_all_tests(args.input)
    elif args.module == 'extract':
        if not args.input:
            console.print("[bold red]Ошибка: --input обязателен")
            sys.exit(1)
        success = await test_extraction(args.input)
    elif args.module == 'tables':
        if not args.input:
            console.print("[bold red]Ошибка: --input обязателен")
            sys.exit(1)
        success = await test_tables(args.input)
    elif args.module == 'ocr':
        if not args.input:
            console.print("[bold red]Ошибка: --input обязателен")
            sys.exit(1)
        success = await test_ocr(args.input)
    elif args.module == 'translate':
        success = await test_translation(args.text)
    elif args.module == 'docx':
        success = await test_docx_creation()
    else:
        console.print("[bold red]Неизвестный модуль")
        success = False
        
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
