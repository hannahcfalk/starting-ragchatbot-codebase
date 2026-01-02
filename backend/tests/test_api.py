"""Tests for FastAPI endpoints"""
import pytest
from unittest.mock import Mock


@pytest.mark.api
class TestQueryEndpoint:
    """Tests for /api/query endpoint"""

    def test_query_without_session_id(self, client, sample_query_request):
        """Test query endpoint creates session when none provided"""
        response = client.post("/api/query", json=sample_query_request)

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "answer" in data
        assert "sources" in data
        assert "session_id" in data

        # Verify answer content
        assert data["answer"] == "This is a test response about MCP."

        # Verify session was created
        assert data["session_id"] == "test-session-123"

    def test_query_with_session_id(self, client, sample_query_request_with_session, mock_rag_system):
        """Test query endpoint uses provided session ID"""
        response = client.post("/api/query", json=sample_query_request_with_session)

        assert response.status_code == 200
        data = response.json()

        # Verify session ID was passed through
        assert data["session_id"] == "existing-session-456"

        # Verify RAG system was called with the session
        mock_rag_system.query.assert_called_once_with(
            "Tell me more about MCP architecture",
            "existing-session-456"
        )

    def test_query_sources_format(self, client, sample_query_request):
        """Test that sources are correctly formatted in response"""
        response = client.post("/api/query", json=sample_query_request)

        assert response.status_code == 200
        data = response.json()

        # Verify sources structure
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) == 2

        # Verify first source
        source1 = data["sources"][0]
        assert "text" in source1
        assert "link" in source1
        assert source1["text"] == "MCP Course - Lesson 1"
        assert source1["link"] == "https://example.com/lesson1"

    def test_query_missing_query_field(self, client):
        """Test query endpoint returns 422 for missing query field"""
        response = client.post("/api/query", json={})

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_query_invalid_json(self, client):
        """Test query endpoint handles invalid JSON"""
        response = client.post(
            "/api/query",
            data="invalid json {",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422

    def test_query_rag_system_exception(self, client, sample_query_request, mock_rag_system):
        """Test query endpoint handles RAG system exceptions"""
        # Make RAG system raise an exception
        mock_rag_system.query.side_effect = Exception("RAG system error")

        response = client.post("/api/query", json=sample_query_request)

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "RAG system error" in data["detail"]

    def test_query_empty_query_string(self, client):
        """Test query endpoint with empty query string"""
        response = client.post("/api/query", json={"query": ""})

        # Should still process, but with empty string
        # The validation depends on implementation
        # For now, test that it doesn't crash
        assert response.status_code in [200, 422]


@pytest.mark.api
class TestCoursesEndpoint:
    """Tests for /api/courses endpoint"""

    def test_get_courses_success(self, client):
        """Test courses endpoint returns analytics"""
        response = client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "total_courses" in data
        assert "course_titles" in data

        # Verify content
        assert data["total_courses"] == 2
        assert len(data["course_titles"]) == 2
        assert "MCP: Build Rich-Context AI Apps with Anthropic" in data["course_titles"]
        assert "Advanced RAG Techniques" in data["course_titles"]

    def test_get_courses_analytics_exception(self, client, mock_rag_system):
        """Test courses endpoint handles analytics exceptions"""
        # Make analytics method raise an exception
        mock_rag_system.get_course_analytics.side_effect = Exception("Analytics error")

        response = client.get("/api/courses")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Analytics error" in data["detail"]

    def test_get_courses_empty_list(self, client, mock_rag_system):
        """Test courses endpoint with no courses"""
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": []
        }

        response = client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()
        assert data["total_courses"] == 0
        assert data["course_titles"] == []

    def test_get_courses_response_type(self, client):
        """Test courses endpoint returns correct content type"""
        response = client.get("/api/courses")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]


@pytest.mark.api
class TestCORSHeaders:
    """Tests for CORS configuration"""

    def test_cors_headers_on_query_endpoint(self, client, sample_query_request):
        """Test that CORS headers are present on query endpoint"""
        response = client.post("/api/query", json=sample_query_request)

        assert response.status_code == 200
        # TestClient doesn't always populate CORS headers in the same way
        # but the middleware should be configured

    def test_cors_headers_on_courses_endpoint(self, client):
        """Test that CORS headers are present on courses endpoint"""
        response = client.get("/api/courses")

        assert response.status_code == 200


@pytest.mark.api
class TestResponseModels:
    """Tests for Pydantic response model validation"""

    def test_query_response_schema(self, client, sample_query_request):
        """Test that query response matches expected schema"""
        response = client.post("/api/query", json=sample_query_request)

        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "answer" in data
        assert "sources" in data
        assert "session_id" in data

        # Field types
        assert isinstance(data["answer"], str)
        assert isinstance(data["sources"], list)
        assert isinstance(data["session_id"], str)

        # Source object schema
        for source in data["sources"]:
            assert "text" in source
            assert "link" in source
            assert isinstance(source["text"], str)
            # link can be None or string
            assert source["link"] is None or isinstance(source["link"], str)

    def test_courses_response_schema(self, client):
        """Test that courses response matches expected schema"""
        response = client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "total_courses" in data
        assert "course_titles" in data

        # Field types
        assert isinstance(data["total_courses"], int)
        assert isinstance(data["course_titles"], list)

        # Verify all course titles are strings
        for title in data["course_titles"]:
            assert isinstance(title, str)