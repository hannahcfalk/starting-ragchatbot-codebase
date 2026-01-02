from openai import OpenAI
from portkey_ai import createHeaders


class AIGenerator:
    """Handles interactions with Claude API via Portkey for generating responses"""

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to comprehensive tools for course information.

Tool Usage Guidelines:
- **Course outline queries**: Use get_course_outline tool for questions about course structure, lesson lists, or table of contents
- **Content search queries**: Use search_course_content tool for questions about specific course content or detailed educational materials
- **Sequential tool calling**: You can make up to 2 tool calls per query in separate rounds
- **Multi-step reasoning**: Use the first tool's results to inform the second tool call
- **Example workflows**:
  - Get course outline → Search for specific content from a lesson
  - Search one course → Compare with content from another course
- **Important**: Each tool call is independent - reason about previous results before making the next call
- Synthesize tool results into accurate, fact-based responses
- If tool yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without tools
- **Course structure questions**: Use get_course_outline first, then answer
- **Course-specific content questions**: Use search_course_content first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, tool explanations, or question-type analysis
 - Do not mention "based on the search results" or "using the outline tool"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://modelops-gateway.cellsdev-1.skyscannerplatform.net/v1",
            default_headers=createHeaders(api_key=api_key, provider="@bedrock-sandbox"),
        )
        self.model = model

        # Pre-build base API parameters
        self.base_params = {"model": self.model, "temperature": 0, "max_tokens": 800}

    def generate_response(
        self,
        query: str,
        conversation_history: str | None = None,
        tools: list | None = None,
        tool_manager=None,
        max_rounds: int = 2,
    ) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        # Build messages for chat completions API
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]

        # Build API call parameters
        api_params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.base_params["max_tokens"],
            "temperature": self.base_params["temperature"],
        }

        # Add tools if provided
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"

        # Get response from Claude via Portkey
        response = self.client.chat.completions.create(**api_params)
        assistant_message = response.choices[0].message

        # Track tool calling rounds (max 2 per query)
        round_count = 0

        # Tool-calling loop: handle tool calls until we get a final response
        while assistant_message.tool_calls and tool_manager and round_count < max_rounds:
            round_count += 1
            # Add assistant's message with tool calls to conversation
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_message.tool_calls
                    ],
                }
            )

            # Execute each tool call and add results
            tool_execution_failed = False
            for tool_call in assistant_message.tool_calls:
                try:
                    tool_result = tool_manager.execute_tool(
                        tool_call.function.name, tool_call.function.arguments
                    )
                except Exception as e:
                    # Tool execution failed - add error message and terminate
                    tool_result = f"Error executing {tool_call.function.name}: {str(e)}"
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": tool_result}
                    )
                    # Set flags to terminate the loop
                    round_count = max_rounds
                    tool_execution_failed = True
                    break

                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": tool_result}
                )

            # Skip API call if tool execution failed
            if tool_execution_failed:
                break

            # Get next response from Claude
            api_params["messages"] = messages
            response = self.client.chat.completions.create(**api_params)
            assistant_message = response.choices[0].message

        # Return the final response content
        return assistant_message.content
