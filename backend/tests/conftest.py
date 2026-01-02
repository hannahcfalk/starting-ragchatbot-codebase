"""Pytest fixtures for RAG chatbot tests"""

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from vector_store import SearchResults


@pytest.fixture
def sample_course_metadata():
    """Sample course metadata for MCP course"""
    return {
        "title": "MCP: Build Rich-Context AI Apps with Anthropic",
        "instructor": "Elie Schoppik",
        "course_link": "https://www.deeplearning.ai/short-courses/mcp-build-rich-context-ai-apps-with-anthropic/",
        "lessons_json": json.dumps(
            [
                {
                    "lesson_number": 0,
                    "lesson_title": "Introduction",
                    "lesson_link": "https://example.com/lesson0",
                },
                {
                    "lesson_number": 1,
                    "lesson_title": "Why MCP",
                    "lesson_link": "https://example.com/lesson1",
                },
                {
                    "lesson_number": 2,
                    "lesson_title": "MCP Architecture",
                    "lesson_link": "https://example.com/lesson2",
                },
            ]
        ),
        "lesson_count": 3,
    }


@pytest.fixture
def sample_search_results():
    """Sample search results for testing"""
    return SearchResults(
        documents=[
            "MCP stands for Model Context Protocol",
            "MCP enables rich context for AI applications",
        ],
        metadata=[
            {"course_title": "MCP: Build Rich-Context AI Apps with Anthropic", "lesson_number": 1},
            {"course_title": "MCP: Build Rich-Context AI Apps with Anthropic", "lesson_number": 2},
        ],
        distances=[0.1, 0.15],
        error=None,
    )


@pytest.fixture
def mock_vector_store(sample_search_results, sample_course_metadata):
    """Mock VectorStore for unit tests"""
    mock_store = Mock()

    # Mock search method
    mock_store.search.return_value = sample_search_results

    # Mock course name resolution
    mock_store._resolve_course_name.return_value = "MCP: Build Rich-Context AI Apps with Anthropic"

    # Mock course catalog access
    mock_catalog = Mock()
    mock_catalog.get.return_value = {"metadatas": [sample_course_metadata]}
    mock_store.course_catalog = mock_catalog

    # Mock link retrieval
    mock_store.get_course_link.return_value = (
        "https://www.deeplearning.ai/short-courses/mcp-build-rich-context-ai-apps-with-anthropic/"
    )
    mock_store.get_lesson_link.return_value = "https://example.com/lesson1"

    return mock_store


@pytest.fixture
def mock_openai_response_no_tools():
    """Mock OpenAI response without tool calls"""
    mock_response = Mock()
    mock_message = Mock()
    mock_message.tool_calls = None
    mock_message.content = "This is a direct answer without using any tools."
    mock_response.choices = [Mock(message=mock_message)]
    return mock_response


@pytest.fixture
def mock_openai_response_with_tool_call():
    """Mock OpenAI response with a tool call"""
    mock_response = Mock()
    mock_message = Mock()

    # Create mock tool call
    mock_tool_call = Mock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "search_course_content"
    mock_tool_call.function.arguments = json.dumps({"query": "MCP basics"})

    mock_message.tool_calls = [mock_tool_call]
    mock_message.content = None
    mock_response.choices = [Mock(message=mock_message)]
    return mock_response


@pytest.fixture
def mock_openai_response_final():
    """Mock OpenAI final response after tool execution"""
    mock_response = Mock()
    mock_message = Mock()
    mock_message.tool_calls = None
    mock_message.content = "Based on the search results, MCP is the Model Context Protocol."
    mock_response.choices = [Mock(message=mock_message)]
    return mock_response


@pytest.fixture
def mock_openai_client(mock_openai_response_no_tools):
    """Mock OpenAI client for AI generator tests"""
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = mock_openai_response_no_tools
    return mock_client


@pytest.fixture
def mock_tool_manager():
    """Mock ToolManager for testing"""
    mock_manager = Mock()

    # Mock tool definitions
    mock_manager.get_tool_definitions.return_value = [
        {
            "type": "function",
            "function": {
                "name": "search_course_content",
                "description": "Search course materials",
                "parameters": {},
            },
        }
    ]

    # Mock tool execution
    mock_manager.execute_tool.return_value = "Mock search results"

    # Mock source management
    mock_manager.get_last_sources.return_value = []
    mock_manager.reset_sources.return_value = None

    return mock_manager


@pytest.fixture
def empty_search_results():
    """Empty search results for testing no results scenario"""
    return SearchResults(documents=[], metadata=[], distances=[], error=None)


@pytest.fixture
def error_search_results():
    """Search results with error for testing error handling"""
    return SearchResults(documents=[], metadata=[], distances=[], error="Course not found")


# API Testing Fixtures


@pytest.fixture
def mock_rag_system():
    """Mock RAGSystem for API tests"""
    mock_rag = Mock()

    # Mock session manager
    mock_rag.session_manager.create_session.return_value = "test-session-123"

    # Mock query method
    mock_rag.query.return_value = (
        "This is a test response about MCP.",
        [
            {"text": "MCP Course - Lesson 1", "link": "https://example.com/lesson1"},
            {"text": "MCP Course - Lesson 2", "link": "https://example.com/lesson2"},
        ],
    )

    # Mock analytics
    mock_rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": [
            "MCP: Build Rich-Context AI Apps with Anthropic",
            "Advanced RAG Techniques",
        ],
    }

    return mock_rag


@pytest.fixture
def test_app(mock_rag_system):
    """Create a test FastAPI app without static file mounting"""

    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    # Create test app
    app = FastAPI(title="Course Materials RAG System - Test", root_path="")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Pydantic models
    class QueryRequest(BaseModel):
        query: str
        session_id: str | None = None

    class Source(BaseModel):
        text: str
        link: str | None = None

    class QueryResponse(BaseModel):
        answer: str
        sources: list[Source]
        session_id: str

    class CourseStats(BaseModel):
        total_courses: int
        course_titles: list[str]

    # API Endpoints
    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = mock_rag_system.session_manager.create_session()

            answer, sources = mock_rag_system.query(request.query, session_id)

            source_objects = [
                Source(**s) if isinstance(s, dict) else Source(text=s) for s in sources
            ]

            return QueryResponse(answer=answer, sources=source_objects, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"], course_titles=analytics["course_titles"]
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


@pytest.fixture
def client(test_app):
    """Create a test client for the FastAPI app"""
    return TestClient(test_app)


@pytest.fixture
def sample_query_request():
    """Sample query request for API tests"""
    return {"query": "What is MCP?", "session_id": None}


@pytest.fixture
def sample_query_request_with_session():
    """Sample query request with session ID for API tests"""
    return {"query": "Tell me more about MCP architecture", "session_id": "existing-session-456"}
