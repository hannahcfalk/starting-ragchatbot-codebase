"""Integration tests for RAG System"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from rag_system import RAGSystem


@pytest.fixture
def mock_config():
    """Mock configuration object for RAGSystem"""
    config = Mock()
    config.API_KEY = "test_key"
    config.MODEL = "test_model"
    config.CHUNK_SIZE = 800
    config.CHUNK_OVERLAP = 100
    config.CHROMA_PATH = "./test_chroma_db"
    config.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    config.MAX_RESULTS = 5
    config.MAX_HISTORY = 2
    return config


class TestRAGSystemIntegration:
    """Integration tests for RAG System functionality"""

    @pytest.fixture
    def rag_system_mocked(self, mock_config):
        """Create RAG system with mocked dependencies"""
        with patch('rag_system.DocumentProcessor') as MockDocProcessor, \
             patch('rag_system.VectorStore') as MockVectorStore, \
             patch('rag_system.AIGenerator') as MockAIGenerator, \
             patch('rag_system.SessionManager') as MockSessionManager:

            MockDocProcessor.return_value = Mock()
            mock_store = Mock()
            mock_ai_gen = Mock()
            mock_ai_gen.generate_response = Mock(return_value="Test response")
            mock_session = Mock()
            mock_session.get_conversation_history.return_value = None

            MockVectorStore.return_value = mock_store
            MockAIGenerator.return_value = mock_ai_gen
            MockSessionManager.return_value = mock_session

            rag = RAGSystem(mock_config)

            yield {
                'rag': rag,
                'vector_store': mock_store,
                'ai_generator': mock_ai_gen,
                'session_manager': mock_session
            }

    def test_tools_passed_to_ai_generator(self, rag_system_mocked):
        """Test that tools are correctly passed to ai_generator"""
        rag = rag_system_mocked['rag']
        ai_gen = rag_system_mocked['ai_generator']

        # Set up tool manager mock
        rag.tool_manager.get_last_sources = Mock(return_value=[])
        rag.tool_manager.reset_sources = Mock()

        # Execute query
        rag.query("What is MCP?")

        # Verify ai_generator called with tools
        call_kwargs = ai_gen.generate_response.call_args[1]
        assert 'tools' in call_kwargs, "tools parameter missing from ai_generator call"
        assert isinstance(call_kwargs['tools'], list)
        assert len(call_kwargs['tools']) == 2  # CourseSearchTool + CourseOutlineTool

    def test_query_flow_without_session(self, rag_system_mocked):
        """Test query flow without session (no history)"""
        rag = rag_system_mocked['rag']
        ai_gen = rag_system_mocked['ai_generator']

        # Set up tool manager mock
        rag.tool_manager.get_last_sources = Mock(return_value=[])
        rag.tool_manager.reset_sources = Mock()

        result = rag.query("What is MCP?")

        # Verify ai_generator called
        ai_gen.generate_response.assert_called_once()

        # Verify history is None (no session)
        call_kwargs = ai_gen.generate_response.call_args[1]
        assert call_kwargs['conversation_history'] is None

        # Verify tool_manager passed
        assert 'tool_manager' in call_kwargs
        assert call_kwargs['tool_manager'] == rag.tool_manager

    def test_query_flow_with_session(self, rag_system_mocked):
        """Test query with session ID for conversation history"""
        rag = rag_system_mocked['rag']
        ai_gen = rag_system_mocked['ai_generator']
        session_mgr = rag_system_mocked['session_manager']

        # Mock session history
        session_mgr.get_conversation_history.return_value = "User: Previous question\nAssistant: Previous answer"

        # Set up tool manager mock
        rag.tool_manager.get_last_sources = Mock(return_value=[])
        rag.tool_manager.reset_sources = Mock()

        result = rag.query("Follow-up question", session_id="test_session")

        # Verify history retrieved
        session_mgr.get_conversation_history.assert_called_once_with("test_session")

        # Verify history passed to ai_generator
        call_kwargs = ai_gen.generate_response.call_args[1]
        assert call_kwargs['conversation_history'] is not None
        assert "Previous question" in call_kwargs['conversation_history']

    def test_source_retrieval_and_reset(self, rag_system_mocked):
        """Test that sources are retrieved and reset correctly"""
        rag = rag_system_mocked['rag']

        # Mock sources
        test_sources = [{'text': 'Source 1', 'link': 'http://example.com'}]
        rag.tool_manager.get_last_sources = Mock(return_value=test_sources)
        rag.tool_manager.reset_sources = Mock()

        response, sources = rag.query("Test query")

        # Verify sources retrieved
        rag.tool_manager.get_last_sources.assert_called_once()

        # Verify sources reset after retrieval
        rag.tool_manager.reset_sources.assert_called_once()

        # Verify sources returned
        assert sources == test_sources

    def test_tool_definitions_format(self, mock_config):
        """Test that tool definitions are in correct OpenAI format"""
        with patch('rag_system.DocumentProcessor') as MockDocProcessor, \
             patch('rag_system.VectorStore'), \
             patch('rag_system.AIGenerator'), \
             patch('rag_system.SessionManager'):

            MockDocProcessor.return_value = Mock()
            rag = RAGSystem(mock_config)
            definitions = rag.tool_manager.get_tool_definitions()

            # Verify format
            assert isinstance(definitions, list)
            assert len(definitions) > 0

            # Check each definition
            for tool_def in definitions:
                assert 'type' in tool_def
                assert tool_def['type'] == 'function'
                assert 'function' in tool_def
                assert 'name' in tool_def['function']
                assert 'description' in tool_def['function']
                assert 'parameters' in tool_def['function']

    def test_session_updated_after_query(self, rag_system_mocked):
        """Test that session is updated with new exchange"""
        rag = rag_system_mocked['rag']
        session_mgr = rag_system_mocked['session_manager']

        # Setup mocks
        rag.tool_manager.get_last_sources = Mock(return_value=[])
        rag.tool_manager.reset_sources = Mock()

        query_text = "What is MCP?"
        rag.query(query_text, session_id="test_session")

        # Verify session add_exchange was called
        session_mgr.add_exchange.assert_called_once()
        call_args = session_mgr.add_exchange.call_args[0]

        # Verify correct data passed to add_exchange
        assert call_args[0] == "test_session"  # session_id
        assert call_args[1] == query_text  # query
        # call_args[2] is response, which is mocked

    def test_tools_registered_on_init(self, mock_config):
        """Test that CourseSearchTool and CourseOutlineTool are registered on init"""
        with patch('rag_system.DocumentProcessor') as MockDocProcessor, \
             patch('rag_system.VectorStore'), \
             patch('rag_system.AIGenerator'), \
             patch('rag_system.SessionManager'):

            MockDocProcessor.return_value = Mock()
            rag = RAGSystem(mock_config)

            # Verify tools registered
            tools = rag.tool_manager.tools
            assert 'search_course_content' in tools
            assert 'get_course_outline' in tools

            # Verify correct tool types
            from search_tools import CourseSearchTool, CourseOutlineTool
            assert isinstance(tools['search_course_content'], CourseSearchTool)
            assert isinstance(tools['get_course_outline'], CourseOutlineTool)

    def test_query_returns_correct_structure(self, rag_system_mocked):
        """Test that query returns tuple with response and sources"""
        rag = rag_system_mocked['rag']
        rag.tool_manager.get_last_sources = Mock(return_value=[])
        rag.tool_manager.reset_sources = Mock()

        response, sources = rag.query("Test query")

        # Verify return structure (tuple)
        assert isinstance(response, str)
        assert isinstance(sources, list)


class TestRAGSystemEdgeCases:
    """Edge case and error handling tests"""

    @pytest.fixture
    def rag_system_mocked(self, mock_config):
        """Create RAG system with mocked dependencies"""
        with patch('rag_system.DocumentProcessor') as MockDocProcessor, \
             patch('rag_system.VectorStore') as MockVectorStore, \
             patch('rag_system.AIGenerator') as MockAIGenerator, \
             patch('rag_system.SessionManager') as MockSessionManager:

            MockDocProcessor.return_value = Mock()
            mock_store = Mock()
            mock_ai_gen = Mock()
            mock_ai_gen.generate_response = Mock(return_value="Test response")
            mock_session = Mock()
            mock_session.get_history.return_value = None

            MockVectorStore.return_value = mock_store
            MockAIGenerator.return_value = mock_ai_gen
            MockSessionManager.return_value = mock_session

            rag = RAGSystem(mock_config)

            yield {
                'rag': rag,
                'ai_generator': mock_ai_gen,
                'session_manager': mock_session
            }

    def test_empty_query(self, rag_system_mocked):
        """Test handling of empty query string"""
        rag = rag_system_mocked['rag']
        rag.tool_manager.get_last_sources = Mock(return_value=[])
        rag.tool_manager.reset_sources = Mock()

        response, sources = rag.query("")

        # Should still call ai_generator
        assert response is not None

    def test_no_sources_from_tools(self, rag_system_mocked):
        """Test when tools return no sources"""
        rag = rag_system_mocked['rag']
        rag.tool_manager.get_last_sources = Mock(return_value=[])
        rag.tool_manager.reset_sources = Mock()

        response, sources = rag.query("Test query")

        # Verify empty sources list returned
        assert sources == []
