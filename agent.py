from prompts import SYSTEM_INSTRUCTION
from tools import READ_DOC_TOOL, SEARCH_DOCS_TOOL, execute_tool


class AgentError(Exception):
    """The agent could not produce an answer within its limits."""


def create_agent_turn(client, turn_input, previous_interaction_id=None):
    return client.interactions.create(
        model="gemini-3.8-flash",
        system_instruction=SYSTEM_INSTRUCTION,
        input=turn_input,
        tools=[SEARCH_DOCS_TOOL, READ_DOC_TOOL],
        previous_interaction_id=previous_interaction_id,
        generation_config={
            "max_output_tokens": 1024,
            "thinking_level": "low",
        },
    )


def answer_question(question: str, client, embedded_chunks, documents) -> str:
    print("\nQUESTION:", question)

    turn_input = question
    previous_interaction_id = None
    tool_calls_used = 0

    for turn in range(1, 4):
        response = create_agent_turn(
            client,
            turn_input,
            previous_interaction_id,
        )

        calls = [
            step for step in response.steps
            if step.type == "function_call"
        ]

        if not calls:
            if not response.output_text:
                raise AgentError(
                    "Model returned no final answer.",
                )
            print(f"COMPLETE: turns={turn} tool_calls={tool_calls_used}")
            return response.output_text

        if tool_calls_used + len(calls) > 2:
            raise AgentError(
                "Agent exceeded the two-tool-call limit.",
            )

        tool_calls_used += len(calls)
        turn_input = [
            execute_tool(
                call,
                client,
                embedded_chunks,
                documents,
            )
            for call in calls
        ]
        previous_interaction_id = response.id

    raise AgentError(
        "Agent exceeded the three-model-turn limit.",
    )
