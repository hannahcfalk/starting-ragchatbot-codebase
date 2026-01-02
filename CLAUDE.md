# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Retrieval-Augmented Generation (RAG) system for answering questions about course materials. The system uses:
- **FastAPI** backend serving both API endpoints and static frontend
- **ChromaDB** for vector storage with semantic search
- **Claude 3.5 Sonnet** via Portkey/Bedrock for AI generation
- **sentence-transformers** (all-MiniLM-L6-v2) for embeddings
- **Tool-based architecture** where the AI uses search tools to retrieve information

## Development Commands

### Setup
```bash
# Install dependencies
uv sync

# Create .env file with required API key
cp .env.example .env
# Then add your PORTKEY_API_KEY to .env
```

### Running the Application
```bash
# Quick start (recommended)
./run.sh

# Manual start
cd backend && uv run uvicorn app:app --reload --port 8000
```

Access points:
- Web UI: http://localhost:8000
- API docs: http://localhost:8000/docs

### Testing
```bash
# Run all tests
cd backend && uv run pytest

# Run specific test file
cd backend && uv run pytest tests/test_search_tools.py

# Run with verbose output
cd backend && uv run pytest -v
```

## Architecture Overview

### Core RAG Pipeline Flow

1. **Query Reception**: User query → FastAPI endpoint (`/api/query`)
2. **RAG Orchestration**: `RAGSystem.query()` coordinates the full pipeline
3. **AI with Tools**: `AIGenerator` receives query + tool definitions
4. **Tool Calling Loop**:
   - AI decides which tool to use based on query type
   - `ToolManager` executes the selected tool
   - Tool returns results to AI
   - AI synthesizes final response
5. **Response**: Answer + sources returned to user

### Key Components

**RAGSystem** (backend/rag_system.py)
- Central orchestrator that coordinates all components
- Manages document ingestion (`add_course_document`, `add_course_folder`)
- Handles queries by routing to AI with tools
- Maintains conversation sessions

**AIGenerator** (backend/ai_generator.py)
- Wraps OpenAI client configured for Portkey/Bedrock
- Implements tool calling loop (receives tool calls → executes → returns results)
- System prompt instructs AI when to use which tool
- Uses temperature=0 and max_tokens=800

**VectorStore** (backend/vector_store.py)
- Two ChromaDB collections:
  - `course_catalog`: Course-level metadata (title, instructor, lessons list)
  - `course_content`: Chunked lesson content with references
- `search()` method: Semantic course name resolution + filtered content search
- Helper methods: `_resolve_course_name()` uses vector search to fuzzy-match course names

**ToolManager & Tools** (backend/search_tools.py)
- `CourseSearchTool`: Semantic search in course content, returns formatted results with sources
- `CourseOutlineTool`: Retrieves full course structure with all lessons
- Tools return both response text (for AI) and sources with links (for UI)
- `last_sources` mechanism: Tools store sources that UI retrieves after query completes

**DocumentProcessor** (backend/document_processor.py)
- Parses structured course documents (expected format in docstring)
- Expected format: Course metadata → Lesson markers → Content
- Sentence-based chunking with overlap (configurable via config.py)
- Adds context prefixes to chunks (e.g., "Course X Lesson Y content: ...")

### Data Models (backend/models.py)

- `Course`: title (unique ID), instructor, course_link, lessons list
- `Lesson`: lesson_number, title, lesson_link
- `CourseChunk`: content, course_title, lesson_number, chunk_index

### Configuration (backend/config.py)

Key settings loaded from environment:
- `PORTKEY_API_KEY`: Required for Bedrock/Claude access
- `MODEL`: Claude model identifier (default: claude-3-5-sonnet-20240620)
- `EMBEDDING_MODEL`: sentence-transformers model (default: all-MiniLM-L6-v2)
- `CHUNK_SIZE`: 800 characters
- `CHUNK_OVERLAP`: 100 characters
- `MAX_RESULTS`: 5 search results
- `MAX_HISTORY`: 2 conversation exchanges remembered

### Frontend Structure

Simple HTML/CSS/JS application in `frontend/`:
- `index.html`: Main UI with chat interface
- `script.js`: API calls to `/api/query` and response handling
- `style.css`: Styling
- Served as static files via FastAPI's StaticFiles mount

## Important Patterns

### Tool Selection Logic
The AI chooses tools based on query type (defined in system prompt):
- **Course outline queries** → `get_course_outline`
- **Content search queries** → `search_course_content`
- **General knowledge** → No tool, uses existing knowledge

### Course Name Resolution
When users provide course names (full or partial):
1. `VectorStore._resolve_course_name()` does semantic search in `course_catalog`
2. Returns exact course title from best match
3. Uses resolved title for filtering content searches

### Source Tracking for UI
1. Tools store sources in `last_sources` during execution
2. After AI response, `RAGSystem` calls `tool_manager.get_last_sources()`
3. Sources include both text description and clickable links
4. Sources reset after retrieval to avoid stale data

### Document Loading
On startup (`app.py` startup event):
- Checks for `../docs` folder
- Loads any PDF/DOCX/TXT files
- Skips courses already in database (checks by title)

### Session Management
- Optional session IDs for conversation context
- `SessionManager` tracks last N exchanges
- History passed to AI for context-aware responses

## Testing

Tests use pytest with fixtures defined in `conftest.py`:
- Mock vector stores and AI generators
- Test tool execution, search filtering, and AI generation
- Located in `backend/tests/`

## Code Quality

### Running Quality Checks

```bash
# Format code automatically (applies changes)
./scripts/format.sh

# Check formatting without changes (CI-friendly)
./scripts/check.sh

# Run linters (Ruff + mypy type checker)
./scripts/lint.sh

# Run all quality checks + tests (recommended before commits)
./scripts/quality.sh
```

### Tools Configured

**Black** - Code formatting
- Line length: 100 characters
- Python 3.13 target version
- Automatically formats code for consistent style

**isort** - Import sorting
- Black-compatible profile
- Organizes imports: stdlib → third-party → first-party
- Configured with project's local modules

**Ruff** - Fast linting
- Checks for errors, bugs, and code smells
- Runs 10-100x faster than flake8
- Rules: pycodestyle, pyflakes, naming, bugbear, comprehensions, simplify
- Test files have relaxed rules for fixtures and mocks

**mypy** - Type checking
- Validates type hints throughout codebase
- Lenient configuration for gradual adoption
- Ignores missing stubs for external libraries (chromadb, sentence-transformers, portkey-ai)

### Pre-commit Hooks

Pre-commit hooks are installed to automatically run quality checks before each commit:

```bash
# Hooks run automatically on `git commit`
# To run manually on all files:
uv run pre-commit run --all-files

# To skip hooks temporarily (not recommended):
git commit --no-verify
```

Configured hooks:
- Black formatting
- isort import sorting
- Ruff linting
- Trailing whitespace removal
- End-of-file fixer
- YAML validation
- Large file check
