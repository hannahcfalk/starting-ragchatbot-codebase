"""Tests for AIGenerator tool calling functionality"""
import pytest
from unittest.mock import Mock, patch, call
import json
from ai_generator import AIGenerator


class TestAIGeneratorToolCalling:
    """Tests for AIGenerator.generate_response() with tool calling"""

    @pytest.fixture
    def ai_generator(self):
        """Create AIGenerator instance with mocked client"""
        with patch('ai_generator.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            generator = AIGenerator(api_key="test_key", model="test_model")
            generator.client = mock_client
            return generator

    def test_no_tool_calls_direct_response(self, ai_generator, mock_openai_response_no_tools):
        """Test response without any tool usage"""
        ai_generator.client.chat.completions.create.return_value = mock_openai_response_no_tools

        result = ai_generator.generate_response(
            query="What is 2+2?",
            tools=None,
            tool_manager=None
        )

        assert result == "This is a direct answer without using any tools."
        assert ai_generator.client.chat.completions.create.call_count == 1

    def test_single_tool_call_loop(self, ai_generator, mock_openai_response_with_tool_call,
                                   mock_openai_response_final, mock_tool_manager):
        """Test single tool call and final response"""
        # First call returns tool_calls, second call returns final answer
        ai_generator.client.chat.completions.create.side_effect = [
            mock_openai_response_with_tool_call,
            mock_openai_response_final
        ]

        result = ai_generator.generate_response(
            query="What is MCP?",
            tools=[{"type": "function", "function": {"name": "search_course_content"}}],
            tool_manager=mock_tool_manager
        )

        # Assert tool was executed
        mock_tool_manager.execute_tool.assert_called_once_with(
            "search_course_content",
            json.dumps({"query": "MCP basics"})
        )

        # Assert final response returned
        assert result == "Based on the search results, MCP is the Model Context Protocol."

        # Assert API was called twice (initial + after tool execution)
        assert ai_generator.client.chat.completions.create.call_count == 2

    def test_two_sequential_rounds(self, ai_generator, mock_tool_manager):
        """Test two sequential tool call rounds (max rounds)"""
        # Create responses for: tool_call -> tool_call -> final
        response_1 = Mock()
        tc1 = Mock()
        tc1.id = "call_1"
        tc1.function.name = "search_course_content"
        tc1.function.arguments = json.dumps({"query": "MCP"})
        response_1.choices = [Mock(message=Mock(tool_calls=[tc1], content=None))]

        response_2 = Mock()
        tc2 = Mock()
        tc2.id = "call_2"
        tc2.function.name = "get_course_outline"
        tc2.function.arguments = json.dumps({"course_name": "MCP"})
        response_2.choices = [Mock(message=Mock(tool_calls=[tc2], content=None))]

        response_final = Mock()
        response_final.choices = [Mock(message=Mock(tool_calls=None, content="Final answer"))]

        ai_generator.client.chat.completions.create.side_effect = [
            response_1,
            response_2,
            response_final
        ]

        result = ai_generator.generate_response(
            query="Tell me about MCP",
            tools=[{"type": "function"}],
            tool_manager=mock_tool_manager
        )

        # Assert both tools executed (2 rounds)
        assert mock_tool_manager.execute_tool.call_count == 2
        # Assert API called 3 times (initial + 2 rounds)
        assert ai_generator.client.chat.completions.create.call_count == 3
        assert result == "Final answer"

    def test_max_rounds_enforced(self, ai_generator, mock_tool_manager):
        """Test that system stops after 2 rounds even if Claude wants more"""
        # Create responses where Claude always wants to call tools
        response_with_tools = Mock()
        tc = Mock()
        tc.id = "call_123"
        tc.function.name = "search_course_content"
        tc.function.arguments = json.dumps({"query": "test"})
        response_with_tools.choices = [Mock(message=Mock(tool_calls=[tc], content=None))]

        # Mock will return tool calls 3 times (more than max_rounds=2)
        ai_generator.client.chat.completions.create.return_value = response_with_tools

        result = ai_generator.generate_response(
            query="Test query",
            tools=[{"type": "function"}],
            tool_manager=mock_tool_manager
        )

        # Should stop after 2 rounds
        # API calls: initial (1) + round 1 (1) + round 2 (1) = 3 total
        assert ai_generator.client.chat.completions.create.call_count == 3
        # Tool executed exactly 2 times (max_rounds)
        assert mock_tool_manager.execute_tool.call_count == 2
        # Result is None because last response had tool_calls (no final answer)
        assert result is None

    def test_tool_execution_error_terminates_rounds(self, ai_generator, mock_tool_manager):
        """Test that tool execution errors terminate the round loop"""
        # First API call returns tool call
        response_with_tool = Mock()
        tc = Mock()
        tc.id = "call_123"
        tc.function.name = "search_course_content"
        tc.function.arguments = json.dumps({"query": "test"})
        response_with_tool.choices = [Mock(message=Mock(tool_calls=[tc], content=None))]

        # Set up mock to return tool call on first call
        ai_generator.client.chat.completions.create.return_value = response_with_tool

        # Tool execution raises exception
        mock_tool_manager.execute_tool.side_effect = Exception("Tool execution failed")

        result = ai_generator.generate_response(
            query="Test query",
            tools=[{"type": "function"}],
            tool_manager=mock_tool_manager
        )

        # Only 1 API call made (initial), loop terminates on error
        assert ai_generator.client.chat.completions.create.call_count == 1
        # Tool execution attempted once
        assert mock_tool_manager.execute_tool.call_count == 1
        # Result is None (loop terminated before getting final answer)
        assert result is None

    def test_sequential_rounds_different_tools(self, ai_generator, mock_tool_manager):
        """Test realistic multi-step workflow with different tools"""
        # Round 1: get_course_outline
        response_1 = Mock()
        tc1 = Mock()
        tc1.id = "call_1"
        tc1.function.name = "get_course_outline"
        tc1.function.arguments = json.dumps({"course_name": "MCP"})
        response_1.choices = [Mock(message=Mock(tool_calls=[tc1], content=None))]

        # Round 2: search_course_content (using data from round 1)
        response_2 = Mock()
        tc2 = Mock()
        tc2.id = "call_2"
        tc2.function.name = "search_course_content"
        tc2.function.arguments = json.dumps({"query": "lesson 4 content"})
        response_2.choices = [Mock(message=Mock(tool_calls=[tc2], content=None))]

        # Final: answer without tools
        response_final = Mock()
        response_final.choices = [Mock(message=Mock(tool_calls=None, content="Course X lesson 4 discusses MCP architecture"))]

        ai_generator.client.chat.completions.create.side_effect = [
            response_1,
            response_2,
            response_final
        ]

        result = ai_generator.generate_response(
            query="What is discussed in lesson 4 of MCP course?",
            tools=[{"type": "function"}],
            tool_manager=mock_tool_manager
        )

        # Both tools executed in order
        assert mock_tool_manager.execute_tool.call_count == 2
        assert mock_tool_manager.execute_tool.call_args_list[0][0][0] == "get_course_outline"
        assert mock_tool_manager.execute_tool.call_args_list[1][0][0] == "search_course_content"
        # API called 3 times
        assert ai_generator.client.chat.completions.create.call_count == 3
        # Final answer returned
        assert result == "Course X lesson 4 discusses MCP architecture"

    def test_single_round_backward_compatibility(self, ai_generator, mock_openai_response_with_tool_call,
                                                 mock_openai_response_final, mock_tool_manager):
        """Test that single-round queries still work as before"""
        # Round 1: Tool call
        # Final: Answer without tools
        ai_generator.client.chat.completions.create.side_effect = [
            mock_openai_response_with_tool_call,
            mock_openai_response_final
        ]

        result = ai_generator.generate_response(
            query="What is MCP?",
            tools=[{"type": "function"}],
            tool_manager=mock_tool_manager
        )

        # Tool executed once
        assert mock_tool_manager.execute_tool.call_count == 1
        # API called 2 times (initial + round 1)
        assert ai_generator.client.chat.completions.create.call_count == 2
        # Final answer returned
        assert result == "Based on the search results, MCP is the Model Context Protocol."

    def test_max_rounds_parameter(self, ai_generator, mock_tool_manager):
        """Test that max_rounds parameter works correctly"""
        # Create responses where Claude always wants to call tools
        response_with_tools = Mock()
        tc = Mock()
        tc.id = "call_123"
        tc.function.name = "search_course_content"
        tc.function.arguments = json.dumps({"query": "test"})
        response_with_tools.choices = [Mock(message=Mock(tool_calls=[tc], content=None))]

        ai_generator.client.chat.completions.create.return_value = response_with_tools

        # Pass max_rounds=1
        result = ai_generator.generate_response(
            query="Test query",
            tools=[{"type": "function"}],
            tool_manager=mock_tool_manager,
            max_rounds=1
        )

        # Should stop after 1 round
        # API calls: initial (1) + round 1 (1) = 2 total
        assert ai_generator.client.chat.completions.create.call_count == 2
        # Tool executed exactly 1 time
        assert mock_tool_manager.execute_tool.call_count == 1

    def test_tools_not_provided_in_api_call(self, ai_generator, mock_openai_response_no_tools):
        """Test that API call omits tools parameter when tools=None"""
        ai_generator.client.chat.completions.create.return_value = mock_openai_response_no_tools

        ai_generator.generate_response(
            query="Test query",
            tools=None,
            tool_manager=None
        )

        # Get the API call arguments
        call_args = ai_generator.client.chat.completions.create.call_args[1]

        # Assert tools not in API parameters
        assert 'tools' not in call_args
        assert 'tool_choice' not in call_args

    def test_tools_provided_in_api_call(self, ai_generator, mock_openai_response_no_tools):
        """Test that API call includes tools parameter when tools provided"""
        ai_generator.client.chat.completions.create.return_value = mock_openai_response_no_tools

        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        ai_generator.generate_response(
            query="Test query",
            tools=tools,
            tool_manager=Mock()
        )

        # Get the API call arguments
        call_args = ai_generator.client.chat.completions.create.call_args[1]

        # Assert tools ARE in API parameters
        assert 'tools' in call_args
        assert call_args['tools'] == tools
        assert 'tool_choice' in call_args
        assert call_args['tool_choice'] == 'auto'

    def test_tool_manager_not_provided_no_execution(self, ai_generator, mock_openai_response_with_tool_call):
        """Test that loop doesn't execute without tool_manager"""
        ai_generator.client.chat.completions.create.return_value = mock_openai_response_with_tool_call

        # Call with tools but no tool_manager
        result = ai_generator.generate_response(
            query="Test query",
            tools=[{"type": "function"}],
            tool_manager=None
        )

        # Since no tool_manager, loop exits immediately
        # Response should be None (from assistant_message.content)
        assert result is None
        assert ai_generator.client.chat.completions.create.call_count == 1

    def test_conversation_history_included_in_system_message(self, ai_generator, mock_openai_response_no_tools):
        """Test that conversation history is included in system message"""
        ai_generator.client.chat.completions.create.return_value = mock_openai_response_no_tools

        history = "User: What is MCP?\nAssistant: MCP is Model Context Protocol."
        ai_generator.generate_response(
            query="Tell me more",
            conversation_history=history,
            tools=None,
            tool_manager=None
        )

        # Get the messages sent to API
        call_args = ai_generator.client.chat.completions.create.call_args[1]
        messages = call_args['messages']

        # Check system message includes history
        assert messages[0]['role'] == 'system'
        assert "Previous conversation:" in messages[0]['content']
        assert history in messages[0]['content']

    def test_no_conversation_history_system_message(self, ai_generator, mock_openai_response_no_tools):
        """Test system message without conversation history"""
        ai_generator.client.chat.completions.create.return_value = mock_openai_response_no_tools

        ai_generator.generate_response(
            query="Test query",
            conversation_history=None,
            tools=None,
            tool_manager=None
        )

        # Get the messages sent to API
        call_args = ai_generator.client.chat.completions.create.call_args[1]
        messages = call_args['messages']

        # Check system message does NOT include history section
        assert messages[0]['role'] == 'system'
        assert "Previous conversation:" not in messages[0]['content']

    def test_api_parameters_correct(self, ai_generator, mock_openai_response_no_tools):
        """Test that API call parameters are correct"""
        ai_generator.client.chat.completions.create.return_value = mock_openai_response_no_tools

        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        ai_generator.generate_response(
            query="Test",
            tools=tools,
            tool_manager=Mock()
        )

        call_args = ai_generator.client.chat.completions.create.call_args[1]

        # Verify all expected parameters
        assert call_args['model'] == "test_model"
        assert call_args['temperature'] == 0
        assert call_args['max_tokens'] == 800
        assert 'messages' in call_args
        assert len(call_args['messages']) == 2  # system + user
        assert call_args['messages'][0]['role'] == 'system'
        assert call_args['messages'][1]['role'] == 'user'
        assert call_args['messages'][1]['content'] == 'Test'
        assert call_args['tools'] == tools
        assert call_args['tool_choice'] == 'auto'

    def test_tool_execution_messages_added_correctly(self, ai_generator, mock_tool_manager):
        """Test that tool execution messages are added to conversation"""
        response_with_tool = Mock()
        tc = Mock()
        tc.id = "call_123"
        tc.function.name = "search_course_content"
        tc.function.arguments = json.dumps({"query": "test"})
        response_with_tool.choices = [Mock(message=Mock(tool_calls=[tc], content=None))]

        response_final = Mock()
        response_final.choices = [Mock(message=Mock(tool_calls=None, content="Final answer"))]

        ai_generator.client.chat.completions.create.side_effect = [
            response_with_tool,
            response_final
        ]

        ai_generator.generate_response(
            query="Test",
            tools=[{"type": "function"}],
            tool_manager=mock_tool_manager
        )

        # Get the second API call (after tool execution)
        second_call_args = ai_generator.client.chat.completions.create.call_args_list[1][1]
        messages = second_call_args['messages']

        # Verify message structure:
        # 1. system
        # 2. user
        # 3. assistant (with tool_calls)
        # 4. tool (with tool result)
        assert len(messages) == 4
        assert messages[0]['role'] == 'system'
        assert messages[1]['role'] == 'user'
        assert messages[2]['role'] == 'assistant'
        assert 'tool_calls' in messages[2]
        assert messages[3]['role'] == 'tool'
        assert messages[3]['tool_call_id'] == 'call_123'
        assert isinstance(messages[3]['content'], str)

    def test_system_prompt_content(self, ai_generator, mock_openai_response_no_tools):
        """Test that system prompt contains expected instructions"""
        ai_generator.client.chat.completions.create.return_value = mock_openai_response_no_tools

        ai_generator.generate_response(query="Test", tools=None, tool_manager=None)

        call_args = ai_generator.client.chat.completions.create.call_args[1]
        system_content = call_args['messages'][0]['content']

        # Verify system prompt has key instructions
        assert "course materials" in system_content.lower()
        assert "tool" in system_content.lower()
