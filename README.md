# PDF Translation Pipeline (Chinese → Russian)

Автоматизированный пайплайн для перевода PDF-документов с китайского на русский язык с сохранением структуры, обработкой таблиц и OCR.

## 🏗 Архитектура проекта

```
/workspace/
├── main.py                 # Точка входа CLI
├── requirements.txt        # Зависимости Python
├── config/
│   ├── __init__.py
│   └── settings.py         # Конфигурация через Pydantic
├── core/
│   ├── __init__.py
│   └── pipeline.py         # Оркестратор пайплайна
├── models/
│   ├── __init__.py
│   └── document_models.py  # Модели данных (Pydantic)
├── services/
│   ├── __init__.py
│   ├── pdf_extractor.py    # Извлечение контента из PDF
│   ├── ocr_service.py      # OCR обработка (Tesseract)
│   ├── llm_translator.py   # LLM перевод (OpenAI API)
│   └── docx_builder.py     # Сборка DOCX документа
├── utils/
│   ├── __init__.py
│   ├── logging_utils.py    # Логирование
│   ├── image_utils.py      # Препроцессинг изображений
│   └── chunking_utils.py   # Разбиение текста на чанки
├── input/                  # Входные PDF файлы
├── output/                 # Выходные DOCX файлы
└── temp/                   # Временные файлы
```

## 📋 Требования

### Системные зависимости

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-chi-tra \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    libtesseract-dev \
    libleptonica-dev
```

**macOS:**
```bash
brew install tesseract tesseract-lang
```

**Windows:**
Скачайте установщик с https://github.com/UB-Mannheim/tesseract/wiki

### Python зависимости

```bash
pip install -r requirements.txt
```

## ⚙️ Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `LLM_API_KEY` | API ключ для LLM | - |
| `LLM_BASE_URL` | URL API совместимого с OpenAI | `https://api.openai.com/v1` |
| `LLM_MODEL` | Модель для перевода | `gpt-4o` |
| `LLM_MAX_TOKENS` | Максимум токенов в ответе | `4096` |
| `LLM_TEMPERATURE` | Температура генерации | `0.3` |
| `OCR_LANG` | Языки для OCR | `chi_sim+rus+eng` |
| `OCR_DPI` | DPI для рендеринга | `300` |
| `MAX_CONCURRENT_TASKS` | Параллельные задачи | `5` |

### Пример .env файла

```bash
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
OCR_LANG=chi_sim+rus+eng
```

## 🚀 Использование

### Перевод одного файла

```bash
python main.py --input document.pdf --output translated.docx
```

### Пакетная обработка директории

```bash
python main.py --input-dir ./pdfs --output-dir ./translations
```

### С указанием модели и API ключа

```bash
python main.py \
    --input document.pdf \
    --model gpt-4o \
    --api-key sk-xxx
```

### Проверка OCR

```bash
python main.py --validate-ocr
```

### Режим отладки

```bash
python main.py --input document.pdf --log-level DEBUG
```

## 🔧 Программный API

```python
import asyncio
from core.pipeline import TranslationPipeline

async def translate_document():
    pipeline = TranslationPipeline()
    
    try:
        report = await pipeline.process_file(
            pdf_path="document.pdf",
            output_path="translated.docx",
            progress_callback=lambda stage, progress: print(f"{stage}: {progress:.0%}")
        )
        
        print(f"Переведено элементов: {report.elements_translated}")
        print(f"Таблиц извлечено: {report.tables_extracted}")
        print(f"Время обработки: {report.processing_time_seconds:.2f}s")
        
    finally:
        await pipeline.cleanup()

asyncio.run(translate_document())
```

## 📊 Особенности архитектуры

### 1. **Асинхронная обработка**
- Все I/O операции асинхронные
- Параллельная обработка чанков при переводе
- Rate limiting для API запросов

### 2. **Умное разбиение на чанки**
- Сохранение контекста между чанками (overlap)
- Отдельная обработка таблиц
- Уважение к структуре документа

### 3. **OCR с препроцессингом**
- Автоматическое определение страниц требующих OCR
- Улучшение качества изображений (deskew, denoise, binarize)
- Адаптивная бинаризация

### 4. **Сохранение структуры**
- Распознавание заголовков по размеру шрифта
- Извлечение таблиц через pdfplumber
- Позиционирование элементов через bounding boxes

### 5. **Контроль качества перевода**
- Валидация результата (длина, наличие иероглифов)
- Детекция refusal patterns
- Возможность верификации через LLM

## 🛡 Обработка ошибок

- Автоматические retry при сбоях API
- Graceful degradation при отсутствии OCR
- Подробное логирование всех этапов
- Отчёт о проблемах в ProcessingReport

## 📝 Форматы поддержки

**Вход:** PDF (текстовые и сканированные)
**Выход:** DOCX с сохранением:
- Заголовков разных уровней
- Абзацев и списков
- Таблиц с форматированием
- Изображений (с OCR подписями)

## 🎯 Рекомендации

### Для лучших результатов:

1. **Качество PDF**: Чем выше качество скана, тем лучше OCR
2. **Модель LLM**: Используйте GPT-4o или аналогичные для качественного перевода
3. **Размер чанков**: Настройте `CHUNK_SIZE` для баланса контекста/скорости
4. **Языки OCR**: Добавьте нужные языковые пакеты Tesseract

### Производительность:

- Увеличьте `MAX_CONCURRENT_TASKS` для мощных систем
- Используйте локальные LLM для больших объёмов
- Кэшируйте результаты для повторной обработки

## 📄 Лицензия

MIT License
