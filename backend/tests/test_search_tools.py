"""Tests for CourseSearchTool, CourseOutlineTool, and ToolManager"""

import json
from unittest.mock import Mock

from search_tools import CourseOutlineTool, CourseSearchTool, ToolManager


class TestCourseSearchTool:
    """Tests for CourseSearchTool.execute()"""

    def test_basic_search_success(self, mock_vector_store, sample_search_results):
        """Test successful search with query only"""
        tool = CourseSearchTool(mock_vector_store)

        result = tool.execute(query="MCP basics")

        # Assert search was called
        mock_vector_store.search.assert_called_once_with(
            query="MCP basics", course_name=None, lesson_number=None
        )

        # Assert result is formatted correctly
        assert "MCP: Build Rich-Context AI Apps with Anthropic" in result
        assert "Lesson 1" in result
        assert "MCP stands for Model Context Protocol" in result

        # Assert sources are tracked
        assert len(tool.last_sources) == 2
        assert (
            tool.last_sources[0]["text"]
            == "MCP: Build Rich-Context AI Apps with Anthropic - Lesson 1"
        )
        assert tool.last_sources[0]["link"] is not None

    def test_search_with_course_filter(self, mock_vector_store):
        """Test search filtered by course name"""
        tool = CourseSearchTool(mock_vector_store)

        result = tool.execute(query="server implementation", course_name="MCP")

        # Assert search called with course filter
        mock_vector_store.search.assert_called_once_with(
            query="server implementation", course_name="MCP", lesson_number=None
        )

        assert "MCP: Build Rich-Context AI Apps with Anthropic" in result

    def test_search_with_lesson_filter(self, mock_vector_store):
        """Test search filtered by lesson number"""
        tool = CourseSearchTool(mock_vector_store)

        result = tool.execute(query="introduction", lesson_number=1)

        # Assert search called with lesson filter
        mock_vector_store.search.assert_called_once_with(
            query="introduction", course_name=None, lesson_number=1
        )

    def test_search_with_combined_filters(self, mock_vector_store):
        """Test search with both course and lesson filters"""
        tool = CourseSearchTool(mock_vector_store)

        result = tool.execute(query="protocol", course_name="MCP", lesson_number=2)

        # Assert both filters applied
        mock_vector_store.search.assert_called_once_with(
            query="protocol", course_name="MCP", lesson_number=2
        )

    def test_empty_results_handling(self, mock_vector_store, empty_search_results):
        """Test handling of no results found"""
        mock_vector_store.search.return_value = empty_search_results
        tool = CourseSearchTool(mock_vector_store)

        result = tool.execute(query="nonexistent content")

        assert "No relevant content found" in result

    def test_empty_results_with_filters(self, mock_vector_store, empty_search_results):
        """Test empty results message includes filter information"""
        mock_vector_store.search.return_value = empty_search_results
        tool = CourseSearchTool(mock_vector_store)

        result = tool.execute(query="test", course_name="MCP", lesson_number=5)

        assert "No relevant content found" in result
        assert "MCP" in result
        assert "lesson 5" in result

    def test_error_handling(self, mock_vector_store, error_search_results):
        """Test handling of search errors"""
        mock_vector_store.search.return_value = error_search_results
        tool = CourseSearchTool(mock_vector_store)

        result = tool.execute(query="test query")

        assert "Course not found" in result

    def test_result_formatting(self, mock_vector_store):
        """Test proper formatting of search results"""
        tool = CourseSearchTool(mock_vector_store)

        result = tool.execute(query="MCP")

        # Check format: [Course Title - Lesson X]
        assert "[MCP: Build Rich-Context AI Apps with Anthropic - Lesson 1]" in result
        assert "[MCP: Build Rich-Context AI Apps with Anthropic - Lesson 2]" in result

        # Check documents are separated
        assert "\n\n" in result

    def test_source_tracking_with_links(self, mock_vector_store):
        """Test that sources are tracked correctly with links"""
        tool = CourseSearchTool(mock_vector_store)

        tool.execute(query="MCP basics")

        # Verify sources tracked
        assert len(tool.last_sources) > 0

        # Verify source structure
        source = tool.last_sources[0]
        assert "text" in source
        assert "link" in source

        # Verify lesson link is included
        assert source["link"] is not None

    def test_get_tool_definition(self):
        """Test tool definition is correctly formatted"""
        tool = CourseSearchTool(Mock())
        definition = tool.get_tool_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "search_course_content"
        assert "description" in definition["function"]
        assert "parameters" in definition["function"]
        assert "query" in definition["function"]["parameters"]["properties"]


class TestCourseOutlineTool:
    """Tests for CourseOutlineTool.execute()"""

    def test_outline_retrieval_success(self, mock_vector_store, sample_course_metadata):
        """Test successful retrieval of course outline"""
        tool = CourseOutlineTool(mock_vector_store)

        result = tool.execute(course_name="MCP")

        # Assert course name was resolved
        mock_vector_store._resolve_course_name.assert_called_once_with("MCP")

        # Assert catalog was queried
        mock_vector_store.course_catalog.get.assert_called_once()

        # Assert result contains expected information
        assert "MCP: Build Rich-Context AI Apps with Anthropic" in result
        assert "Elie Schoppik" in result
        assert "Lesson 0: Introduction" in result
        assert "Lesson 1: Why MCP" in result
        assert "Lesson 2: MCP Architecture" in result

    def test_partial_course_name_matching(self, mock_vector_store, sample_course_metadata):
        """Test that partial course names work via semantic search"""
        tool = CourseOutlineTool(mock_vector_store)

        result = tool.execute(course_name="MCP")

        # Verify course resolution was called
        mock_vector_store._resolve_course_name.assert_called_with("MCP")
        assert "MCP: Build Rich-Context AI Apps with Anthropic" in result

    def test_course_not_found(self, mock_vector_store):
        """Test handling when course doesn't exist"""
        mock_vector_store._resolve_course_name.return_value = None
        tool = CourseOutlineTool(mock_vector_store)

        result = tool.execute(course_name="NonexistentCourse")

        assert "No course found matching" in result
        assert "NonexistentCourse" in result

    def test_metadata_unavailable(self, mock_vector_store):
        """Test handling when course exists but metadata missing"""
        mock_vector_store.course_catalog.get.return_value = {"metadatas": []}
        tool = CourseOutlineTool(mock_vector_store)

        result = tool.execute(course_name="MCP")

        assert "metadata is unavailable" in result

    def test_lesson_count_verification(self, mock_vector_store, sample_course_metadata):
        """Test that lesson count is displayed correctly"""
        tool = CourseOutlineTool(mock_vector_store)

        result = tool.execute(course_name="MCP")

        assert "3 total" in result

    def test_links_present_in_output(self, mock_vector_store, sample_course_metadata):
        """Test that course and lesson links are included"""
        tool = CourseOutlineTool(mock_vector_store)

        result = tool.execute(course_name="MCP")

        # Check course link
        assert "https://www.deeplearning.ai" in result

        # Check lesson links
        assert "https://example.com/lesson0" in result
        assert "https://example.com/lesson1" in result

    def test_source_tracking(self, mock_vector_store, sample_course_metadata):
        """Test that source tracking works correctly"""
        tool = CourseOutlineTool(mock_vector_store)

        tool.execute(course_name="MCP")

        # Verify sources tracked
        assert len(tool.last_sources) == 1

        # Verify source content
        source = tool.last_sources[0]
        assert "Course Outline" in source["text"]
        assert source["link"] is not None

    def test_malformed_json_handling(self, mock_vector_store, sample_course_metadata):
        """Test handling of invalid lessons_json"""
        # Create metadata with invalid JSON
        bad_metadata = sample_course_metadata.copy()
        bad_metadata["lessons_json"] = "invalid json {"

        mock_vector_store.course_catalog.get.return_value = {"metadatas": [bad_metadata]}
        tool = CourseOutlineTool(mock_vector_store)

        result = tool.execute(course_name="MCP")

        # Should still return course info, just no lessons
        assert "MCP: Build Rich-Context AI Apps with Anthropic" in result
        assert "Elie Schoppik" in result

    def test_get_tool_definition(self):
        """Test tool definition is correctly formatted"""
        tool = CourseOutlineTool(Mock())
        definition = tool.get_tool_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "get_course_outline"
        assert "course structure" in definition["function"]["description"].lower()
        assert "course_name" in definition["function"]["parameters"]["properties"]


class TestToolManager:
    """Tests for ToolManager"""

    def test_tool_registration(self, mock_vector_store):
        """Test registering tools"""
        manager = ToolManager()
        tool = CourseSearchTool(mock_vector_store)

        manager.register_tool(tool)

        assert "search_course_content" in manager.tools
        assert manager.tools["search_course_content"] == tool

    def test_register_multiple_tools(self, mock_vector_store):
        """Test registering multiple tools"""
        manager = ToolManager()
        search_tool = CourseSearchTool(mock_vector_store)
        outline_tool = CourseOutlineTool(mock_vector_store)

        manager.register_tool(search_tool)
        manager.register_tool(outline_tool)

        assert len(manager.tools) == 2
        assert "search_course_content" in manager.tools
        assert "get_course_outline" in manager.tools

    def test_get_tool_definitions(self, mock_vector_store):
        """Test retrieving all tool definitions"""
        manager = ToolManager()
        manager.register_tool(CourseSearchTool(mock_vector_store))
        manager.register_tool(CourseOutlineTool(mock_vector_store))

        definitions = manager.get_tool_definitions()

        assert isinstance(definitions, list)
        assert len(definitions) == 2
        assert all("type" in d and d["type"] == "function" for d in definitions)

    def test_execute_tool_success(self, mock_vector_store):
        """Test successful tool execution"""
        manager = ToolManager()
        tool = CourseSearchTool(mock_vector_store)
        manager.register_tool(tool)

        arguments = json.dumps({"query": "MCP basics"})
        result = manager.execute_tool("search_course_content", arguments)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_tool_not_found(self):
        """Test execution of non-existent tool"""
        manager = ToolManager()

        result = manager.execute_tool("nonexistent_tool", "{}")

        assert "Tool 'nonexistent_tool' not found" in result

    def test_invalid_json_arguments(self, mock_vector_store):
        """Test handling of invalid JSON arguments"""
        manager = ToolManager()
        manager.register_tool(CourseSearchTool(mock_vector_store))

        result = manager.execute_tool("search_course_content", "invalid json {")

        assert "Invalid JSON arguments" in result

    def test_get_last_sources(self, mock_vector_store):
        """Test retrieving sources from tools"""
        manager = ToolManager()
        tool = CourseSearchTool(mock_vector_store)
        manager.register_tool(tool)

        # Execute search to populate sources
        manager.execute_tool("search_course_content", json.dumps({"query": "MCP"}))

        sources = manager.get_last_sources()
        assert isinstance(sources, list)
        assert len(sources) > 0

    def test_reset_sources(self, mock_vector_store):
        """Test resetting sources across all tools"""
        manager = ToolManager()
        tool = CourseSearchTool(mock_vector_store)
        manager.register_tool(tool)

        # Execute search to populate sources
        manager.execute_tool("search_course_content", json.dumps({"query": "MCP"}))
        assert len(tool.last_sources) > 0

        # Reset sources
        manager.reset_sources()
        assert len(tool.last_sources) == 0

    def test_get_last_sources_empty(self):
        """Test get_last_sources when no tools have sources"""
        manager = ToolManager()
        sources = manager.get_last_sources()
        assert sources == []
