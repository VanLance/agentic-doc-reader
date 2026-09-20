from functools import partial

from retrieval import search


SEARCH_DOCS_TOOL = {
    "type": "function",
    "name": "search_docs",
    "description": (
        "Search the Parcel Orders developer documentation. "
        "Use this to find evidence before answering project-specific questions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "A focused search query describing the documentation "
                    "needed to answer the user's question."
                ),
            },
        },
        "required": ["query"],
    },
}

READ_DOC_TOOL = {
    "type": "function",
    "name": "read_doc",
    "description": (
        "Read a complete Parcel Orders documentation file. "
        "Use when search results are cut off or more surrounding context "
        "is needed. Supply a source returned by search_docs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": (
                    "The exact source label from a search result, "
                    "for example docs/events.md."
                ),
            },
        },
        "required": ["source"],
    },
}


def search_docs(query: str, client, embedded_chunks) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")

    query = query.strip()
    results = search(
        client,
        query,
        embedded_chunks,
        top_k=3,
    )

    context = "\n\n".join(
        f"[Source: {result['source']} | Chunk: {result['chunk_index']}]\n"
        f"{result['text']}"
        for result in results
    )
    return context


def read_doc(source: str, documents) -> str:
    if not isinstance(source, str) or not source.strip():
        return "Tool error: source must be a non-empty string."

    source = source.strip()
    text = documents.get(source)

    if text is None:
        return "Tool error: unknown source. Use a source returned by search_docs."

    return f"[Source: {source} | Full document]\n{text}"


def execute_tool(call, client, embedded_chunks, documents):
    print("\nTOOL REQUEST:", call.name, call.arguments)

    available_tools = {
        "search_docs": (
            partial(search_docs, client=client, embedded_chunks=embedded_chunks),
            "query",
        ),
        "read_doc": (
            partial(read_doc, documents=documents),
            "source",
        ),
    }

    if call.name not in available_tools:
        result = "Tool error: unknown tool. Use search_docs or read_doc."
    else:
        function, argument_name = available_tools[call.name]
        arguments = call.arguments

        if (
            not isinstance(arguments, dict)
            or set(arguments) != {argument_name}
            or not isinstance(arguments[argument_name], str)
            or not arguments[argument_name].strip()
        ):
            result = (
                "Tool error: provide exactly one non-empty string argument: "
                f"{argument_name}."
            )
        else:
            result = function(arguments[argument_name])

    return {
        "type": "function_result",
        "name": call.name,
        "call_id": call.id,
        "result": [{"type": "text", "text": result}],
    }
