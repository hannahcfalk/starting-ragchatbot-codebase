import json
from abc import ABC, abstractmethod
from typing import Any

from vector_store import SearchResults, VectorStore


class Tool(ABC):
    """Abstract base class for all tools"""

    @abstractmethod
    def get_tool_definition(self) -> dict[str, Any]:
        """Return Anthropic tool definition for this tool"""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool with given parameters"""
        pass


class CourseSearchTool(Tool):
    """Tool for searching course content with semantic course name matching"""

    def __init__(self, vector_store: VectorStore):
        self.store = vector_store
        self.last_sources = []  # Track sources from last search

    def get_tool_definition(self) -> dict[str, Any]:
        """Return OpenAI-compatible tool definition for this tool"""
        return {
            "type": "function",
            "function": {
                "name": "search_course_content",
                "description": "Search course materials with smart course name matching and lesson filtering",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to search for in the course content",
                        },
                        "course_name": {
                            "type": "string",
                            "description": "Course title (partial matches work, e.g. 'MCP', 'Introduction')",
                        },
                        "lesson_number": {
                            "type": "integer",
                            "description": "Specific lesson number to search within (e.g. 1, 2, 3)",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def execute(
        self, query: str, course_name: str | None = None, lesson_number: int | None = None
    ) -> str:
        """
        Execute the search tool with given parameters.

        Args:
            query: What to search for
            course_name: Optional course filter
            lesson_number: Optional lesson filter

        Returns:
            Formatted search results or error message
        """

        # Use the vector store's unified search interface
        results = self.store.search(
            query=query, course_name=course_name, lesson_number=lesson_number
        )

        # Handle errors
        if results.error:
            return results.error

        # Handle empty results
        if results.is_empty():
            filter_info = ""
            if course_name:
                filter_info += f" in course '{course_name}'"
            if lesson_number:
                filter_info += f" in lesson {lesson_number}"
            return f"No relevant content found{filter_info}."

        # Format and return results
        return self._format_results(results)

    def _format_results(self, results: SearchResults) -> str:
        """Format search results with course and lesson context"""
        formatted = []
        sources = []  # Track sources for the UI (now with links)

        for doc, meta in zip(results.documents, results.metadata):
            course_title = meta.get("course_title", "unknown")
            lesson_num = meta.get("lesson_number")

            # Build context header
            header = f"[{course_title}"
            if lesson_num is not None:
                header += f" - Lesson {lesson_num}"
            header += "]"

            # Build source text for the UI
            source_text = course_title
            if lesson_num is not None:
                source_text += f" - Lesson {lesson_num}"

            # Get link: try lesson link first, fall back to course link
            link = None
            if lesson_num is not None:
                link = self.store.get_lesson_link(course_title, lesson_num)
            if not link:
                link = self.store.get_course_link(course_title)

            sources.append({"text": source_text, "link": link})

            formatted.append(f"{header}\n{doc}")

        # Store sources for retrieval
        self.last_sources = sources

        return "\n\n".join(formatted)


class CourseOutlineTool(Tool):
    """Tool for getting complete course outline with all lessons"""

    def __init__(self, vector_store: VectorStore):
        self.store = vector_store
        self.last_sources = []  # Track sources from last search

    def get_tool_definition(self) -> dict[str, Any]:
        """Return OpenAI-compatible tool definition for this tool"""
        return {
            "type": "function",
            "function": {
                "name": "get_course_outline",
                "description": "Get complete course outline including all lessons with their titles and links. Use this when user asks about course structure, lesson list, or table of contents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "course_name": {
                            "type": "string",
                            "description": "Course title (partial matches work, e.g. 'MCP', 'Introduction')",
                        }
                    },
                    "required": ["course_name"],
                },
            },
        }

    def execute(self, course_name: str) -> str:
        """
        Get complete course outline with all lessons.

        Args:
            course_name: Course name or partial title to search for

        Returns:
            Formatted course outline string or error message
        """

        # Step 1: Resolve course name using semantic matching
        resolved_course_title = self.store._resolve_course_name(course_name)

        # Step 2: Handle course not found
        if not resolved_course_title:
            return f"No course found matching '{course_name}'. Please check the course name and try again."

        # Step 3: Get course metadata from course_catalog
        try:
            results = self.store.course_catalog.get(ids=[resolved_course_title])

            if not results or not results.get("metadatas") or not results["metadatas"]:
                return f"Course '{course_name}' was found but metadata is unavailable."

            metadata = results["metadatas"][0]

        except Exception as e:
            return f"Error retrieving course outline: {str(e)}"

        # Step 4: Parse and format the course outline
        return self._format_course_outline(metadata, resolved_course_title)

    def _format_course_outline(self, metadata: dict[str, Any], course_title: str) -> str:
        """
        Format course metadata into readable outline.

        Args:
            metadata: Course metadata from ChromaDB
            course_title: Resolved course title

        Returns:
            Formatted course outline string
        """

        # Extract basic course info
        title = metadata.get("title", course_title)
        instructor = metadata.get("instructor", "Unknown")
        course_link = metadata.get("course_link")
        lessons_json = metadata.get("lessons_json", "[]")
        lesson_count = metadata.get("lesson_count", 0)

        # Parse lessons from JSON
        try:
            lessons = json.loads(lessons_json)
        except json.JSONDecodeError:
            lessons = []

        # Build formatted output
        output_parts = [
            f"Course: {title}",
            f"Instructor: {instructor}",
        ]

        if course_link:
            output_parts.append(f"Course Link: {course_link}")

        output_parts.append(f"\nLessons ({lesson_count} total):")
        output_parts.append("-" * 50)

        # Format each lesson
        for lesson in lessons:
            lesson_num = lesson.get("lesson_number")
            lesson_title = lesson.get("lesson_title", "Untitled")
            lesson_link = lesson.get("lesson_link")

            lesson_line = f"Lesson {lesson_num}: {lesson_title}"
            if lesson_link:
                lesson_line += f"\n  Link: {lesson_link}"

            output_parts.append(lesson_line)

        # Store source for UI
        self.last_sources = [{"text": f"{title} - Course Outline", "link": course_link}]

        return "\n".join(output_parts)


class ToolManager:
    """Manages available tools for the AI"""

    def __init__(self):
        self.tools = {}

    def register_tool(self, tool: Tool):
        """Register any tool that implements the Tool interface"""
        tool_def = tool.get_tool_definition()
        # Handle OpenAI format: name is nested under "function"
        tool_name = tool_def.get("function", {}).get("name") or tool_def.get("name")
        if not tool_name:
            raise ValueError("Tool must have a 'name' in its definition")
        self.tools[tool_name] = tool

    def get_tool_definitions(self) -> list:
        """Get all tool definitions for Anthropic tool calling"""
        return [tool.get_tool_definition() for tool in self.tools.values()]

    def execute_tool(self, tool_name: str, arguments: str) -> str:
        """Execute a tool by name with given parameters.

        Args:
            tool_name: Name of the tool to execute
            arguments: JSON string of arguments from the LLM

        Returns:
            Tool execution result as string
        """
        if tool_name not in self.tools:
            return f"Tool '{tool_name}' not found"

        # Parse JSON arguments string into kwargs
        try:
            kwargs = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return f"Invalid JSON arguments: {arguments}"

        return self.tools[tool_name].execute(**kwargs)

    def get_last_sources(self) -> list:
        """Get sources from the last search operation"""
        # Check all tools for last_sources attribute
        for tool in self.tools.values():
            if hasattr(tool, "last_sources") and tool.last_sources:
                return tool.last_sources
        return []

    def reset_sources(self):
        """Reset sources from all tools that track sources"""
        for tool in self.tools.values():
            if hasattr(tool, "last_sources"):
                tool.last_sources = []
