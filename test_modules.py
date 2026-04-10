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
from pathlib import Path

# Добавляем путь к директории src в sys.path
src_path = Path(__file__).parent / "src"
sys.path.append(str(src_path))

from core.document_processor import DocumentProcessor
from core.translation_service import LLMTranslationService
from core.docx_builder import DocxBuilder
from core.models import PageContent, DocumentElement, TableData, ElementType, TranslationChunk
from utils.logger import setup_logger

logger = setup_logger()

def test_extraction():
    """Тестирование извлечения содержимого из PDF"""
    processor = DocumentProcessor()
    
    # Проверяем наличие тестового файла
    test_file = Path("test_files") / "sample_document.pdf"
    if not test_file.exists():
        print(f"Тестовый файл {test_file} не найден")
        return False
    
    try:
        pages = processor.extract_pages(test_file)
        print(f"Извлечено страниц: {len(pages)}")
        
        for i, page in enumerate(pages):
            print(f"Страница {i + 1}: {len(page.elements)} элементов")
            
            for element in page.elements:
                if element.element_type == ElementType.TEXT:
                    print(f"  Текст: {element.content[:100]}...")
                elif element.element_type == ElementType.TABLE:
                    table_data = element.content
                    print(f"  Таблица: {table_data.rows} строк, {table_data.cols} столбцов")
                    
        return len(pages) > 0
        
    except Exception as e:
        logger.error(f"Ошибка при извлечении: {e}")
        return False

def test_translation():
    """Тестирование перевода текста"""
    try:
        translator = LLMTranslationService()
        
        # Подготовим тестовые чанки для перевода
        chunks = [
            TranslationChunk(
                id=1,
                text="This is a sample text for translation testing.",
                context="Test document",
                element_type=ElementType.TEXT
            ),
            TranslationChunk(
                id=2,
                text="Another paragraph to translate.",
                context="Test document",
                element_type=ElementType.TEXT
            )
        ]
        
        print("Начинаем перевод...")
        translated_chunks = translator.translate_chunks(chunks)
        
        for original, translated in zip(chunks, translated_chunks):
            print(f"Оригинал: {original.text}")
            print(f"Перевод: {translated}")
            print("-" * 50)
            
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при переводе: {e}")
        return False

def test_docx_creation():
    """Тестирование создания DOCX файла"""
    try:
        builder = DocxBuilder()
        
        # Создаем тестовое содержимое документа
        pages_content = [
            PageContent(
                page_num=1,
                elements=[
                    DocumentElement(
                        element_type=ElementType.TEXT,
                        content="Привет, это тестовый текст.",
                        formatting={}
                    ),
                    DocumentElement(
                        element_type=ElementType.TABLE,
                        content=TableData(
                            headers=["Имя", "Возраст"],
                            rows=[["Иван", "30"], ["Мария", "25"]]
                        ),
                        formatting={"style": "Table Grid"}
                    )
                ]
            )
        ]
        
        output_path = Path("output") / "test_output.docx"
        output_path.parent.mkdir(exist_ok=True)
        
        builder.build_document(pages_content, str(output_path))
        
        if output_path.exists():
            print(f"DOCX файл успешно создан: {output_path}")
            return True
        else:
            print("DOCX файл не был создан")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при создании DOCX: {e}")
        return False

def main():
    """Основная функция для запуска всех тестов"""
    print("Запуск тестов модулей...")
    
    print("\n1. Тестирование извлечения содержимого:")
    extraction_success = test_extraction()
    
    print("\n2. Тестирование перевода:")
    translation_success = test_translation()
    
    print("\n3. Тестирование создания DOCX:")
    docx_success = test_docx_creation()
    
    print(f"\nРезультаты тестов:")
    print(f"Извлечение: {'Успешно' if extraction_success else 'Ошибка'}")
    print(f"Перевод: {'Успешно' if translation_success else 'Ошибка'}")
    print(f"Создание DOCX: {'Успешно' if docx_success else 'Ошибка'}")
    
    all_tests_passed = extraction_success and translation_success and docx_success
    print(f"\nВсе тесты пройдены: {'Да' if all_tests_passed else 'Нет'}")

if __name__ == "__main__":
    main()
