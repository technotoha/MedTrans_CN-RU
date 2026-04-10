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
import sys
import argparse
from pathlib import Path

# Добавляем путь к директории проекта в sys.path
project_path = Path(__file__).parent
sys.path.append(str(project_path))

from services.pdf_extractor import PDFExtractor
from services.ocr_service import OCRService
from services.llm_translator import LLMTranslationService
from models.document_models import PageContent, DocumentElement, TableData, ElementType, TranslationChunk
from utils.logging_utils import setup_logger, get_logger

logger = get_logger(__name__)
setup_logger()


async def test_extraction(input_file: str):
    """Тестирование извлечения содержимого из PDF"""
    print("╭──────────────────────────────────╮")
    print("│ Тестирование извлечения контента │")
    print("╰──────────────────────────────────╯")
    
    extractor = PDFExtractor(dpi=300)
    
    try:
        pages = await extractor.extract_all(input_file)
        print(f"✅ Успешно извлечено {len(pages)} страниц.")
        
        total_elements = 0
        total_text_chars = 0
        
        for page in pages:
            elements_count = len(page.elements)
            text_chars = sum(
                len(elem.content) 
                for elem in page.elements 
                if elem.element_type == ElementType.TEXT
            )
            total_elements += elements_count
            total_text_chars += text_chars
            
            print(f"  Страница {page.page_number}: {elements_count} элементов, {text_chars} символов текста.")
            
            # Выводим первые несколько элементов для демонстрации
            for i, element in enumerate(page.elements[:3]):
                if element.element_type == ElementType.TEXT:
                    preview = element.content[:80].replace('\n', ' ')
                    print(f"    [{element.element_type.value}]: {preview}...")
                elif element.element_type == ElementType.TABLE:
                    table = element.table_data
                    print(f"    [TABLE]: {table.rows if table else 'N/A'} строк")
                elif element.element_type == ElementType.IMAGE:
                    print(f"    [IMAGE]: {element.image_path}")
            
            if len(page.elements) > 3:
                print(f"    ... и ещё {len(page.elements) - 3} элементов")
            
            # Проверка необходимости OCR
            if page.ocr_required:
                print(f"  ⚠️  Страница {page.page_number} требует OCR (мало текста или есть изображения)")
        
        print(f"📊 Всего элементов: {total_elements}")
        print(f"📝 Всего символов текста: {total_text_chars}")
        
        return len(pages) > 0
        
    except Exception as e:
        logger.error(f"Ошибка при извлечении: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ocr(input_file: str):
    """Тестирование OCR модуля"""
    print("╭──────────────────────────────╮")
    print("│ Тестирование модуля OCR      │")
    print("╰──────────────────────────────╯")
    
    try:
        ocr_service = OCRService()
        print(f"✅ OCR сервис инициализирован. Языки: {ocr_service.config_lang}")
        
        # Для OCR нужны изображения страниц
        # Рендерим страницу в изображение и передаём на OCR
        import fitz
        doc = fitz.open(input_file)
        
        for page_num in range(min(len(doc), 1)):  # Тестируем первую страницу
            page = doc[page_num]
            
            # Рендерим страницу в изображение
            mat = fitz.Matrix(300/72, 300/72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            
            print(f"\n🔍 OCR страницы {page_num + 1}...")
            text = await ocr_service.recognize(img_data)
            
            if text:
                print(f"✅ Распознанный текст ({len(text)} символов):")
                print(f"   {text[:200]}{'...' if len(text) > 200 else ''}")
            else:
                print("⚠️  Текст не распознан (возможно, нет текста на изображении)")
        
        doc.close()
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при OCR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_translation():
    """Тестирование модуля перевода"""
    print("╭──────────────────────────────╮")
    print("│ Тестирование модуля перевода │")
    print("╰──────────────────────────────╯")
    
    try:
        translator = LLMTranslationService()
        print("✅ Сервис перевода инициализирован.")
        
        # Создаём тестовые элементы
        elem1 = DocumentElement(
            id="test_elem_1",
            element_type=ElementType.TEXT,
            content="医生诊断患者患有急性支气管炎。",
            page_number=1,
            position=0
        )
        elem2 = DocumentElement(
            id="test_elem_2",
            element_type=ElementType.TEXT,
            content="处方药：阿莫西林 500mg，每日三次。",
            page_number=1,
            position=1
        )
        
        # Тестовые чанки с китайским текстом
        chunks = [
            TranslationChunk(
                chunk_id="chunk_1",
                elements=[elem1],
                source_text="医生诊断患者患有急性支气管炎。"
            ),
            TranslationChunk(
                chunk_id="chunk_2",
                elements=[elem2],
                source_text="处方药：阿莫西林 500mg，每日三次。"
            )
        ]
        
        print("\n🔄 Перевод тестовых чанков...")
        translated_chunks = await translator.translate_chunks(chunks)
        
        for original, translated in zip(chunks, translated_chunks):
            print(f"\nОригинал (zh): {original.source_text}")
            print(f"Перевод (ru):   {translated.translated_text or 'N/A'}")
            print("-" * 50)
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при переводе: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Основная функция для запуска тестов"""
    parser = argparse.ArgumentParser(description="Тестирование модулей PDF переводчика")
    parser.add_argument(
        "--module", 
        choices=["extract", "ocr", "translate", "all"],
        default="all",
        help="Модуль для тестирования"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Путь к входному PDF файлу"
    )
    parser.add_argument(
        "--text",
        type=str,
        help="Текст для перевода (для теста translate)"
    )
    
    args = parser.parse_args()
    
    # Определяем входной файл
    input_file = args.input
    if not input_file:
        # Поиск тестового файла по умолчанию
        for path in [
            Path("input/test3.pdf"),
            Path("test3.pdf"),
            Path("input/sample.pdf")
        ]:
            if path.exists():
                input_file = str(path)
                break
    
    if args.module in ["extract", "ocr", "all"] and not input_file:
        print("❌ Ошибка: Не указан входной PDF файл!")
        print("Используйте --input <путь_к_файлу>")
        sys.exit(1)
    
    print("╭──────────────────────────────────╮")
    print("│ ПОЛНОЕ ТЕСТИРОВАНИЕ ВСЕХ МОДУЛЕЙ │")
    print("╰──────────────────────────────────╯")
    
    results = {}
    
    # Тест извлечения
    if args.module in ["extract", "all"]:
        results["extraction"] = await test_extraction(input_file)
        print()
    
    # Тест OCR
    if args.module in ["ocr", "all"]:
        results["ocr"] = await test_ocr(input_file)
        print()
    
    # Тест перевода
    if args.module in ["translate", "all"]:
        results["translation"] = await test_translation()
    
    # Итоги
    print("\n" + "=" * 40)
    print("ИТОГИ ТЕСТИРОВАНИЯ:")
    for module, success in results.items():
        status = "✅ Успешно" if success else "❌ Ошибка"
        print(f"  {module}: {status}")
    
    all_passed = all(results.values())
    print(f"\nВсе тесты пройдены: {'Да' if all_passed else 'Нет'}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
