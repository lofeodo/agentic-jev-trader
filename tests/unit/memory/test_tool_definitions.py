"""The bridge's three hand-written tool definitions against the memory server's own tool list
(spec appendix 5, section 4; appendix 10, section 2; ADR 0006). A mismatch fails.

Each tool is described twice: on the server, with the inputs code fills in (the sim, the step,
what the search serves), and in the definition the LLM sees, without them.
"""

from jev_trader.memory.bridge import LOOKUP_TOOLS, definitions
from jev_trader.memory.search import FULL_EVALUATION, POSITION_REVIEW
from jev_trader.memory.server import FILLED_IN_BY_CODE
from tests.unit.memory.conftest import HOST, PATTERNS, run, served

JOBS = (FULL_EVALUATION, POSITION_REVIEW)


def server_tools(store):
    from jev_trader.memory.bridge import connect

    async def body():
        async with (
            served(store) as http,
            connect(f"http://{HOST}", http_client=http) as session,
        ):
            listed = await session.list_tools()
        return {t.name: t.input_schema for t in listed.tools}

    return run(body)


def _type(schema: dict) -> str:
    """A property's type, looking through "or nothing" (anyOf with null)."""
    if "anyOf" in schema:
        (kept,) = [s for s in schema["anyOf"] if s.get("type") != "null"]
        return _type(kept)
    return schema["type"]


def _enum(schema: dict) -> list | None:
    if "anyOf" in schema:
        return next((s["enum"] for s in schema["anyOf"] if "enum" in s), None)
    return schema.get("enum")


def mismatches(server: dict[str, dict]) -> list[str]:
    found = []
    if set(server) != set(LOOKUP_TOOLS):
        found.append(f"server tools {sorted(server)} != {sorted(LOOKUP_TOOLS)}")
    seen: dict[str, set[str]] = {name: set() for name in LOOKUP_TOOLS}
    for job in JOBS:
        for d in definitions(job, PATTERNS):
            on_server = server.get(d.name)
            if on_server is None:
                continue
            props, filled = on_server["properties"], set(FILLED_IN_BY_CODE[d.name])
            required = set(on_server.get("required", []))
            mine = d.input_schema["properties"]
            seen[d.name] |= set(mine)
            if hidden := filled & set(mine):
                found.append(f"{job} {d.name} shows code's inputs {sorted(hidden)}")
            for name, schema in mine.items():
                theirs = props.get(name)
                if theirs is None:
                    found.append(f"{job} {d.name}.{name} is not on the server")
                    continue
                if _type(theirs) != schema["type"]:
                    found.append(f"{job} {d.name}.{name} type differs")
                allowed = _enum(theirs)
                if allowed is not None and not set(schema.get("enum", [])) <= set(
                    allowed
                ):
                    found.append(
                        f"{job} {d.name}.{name} allows values the server does not"
                    )
                if schema["type"] == "array":
                    for limit, key in (
                        ("minItems", "minItems"),
                        ("maxItems", "maxItems"),
                    ):
                        if theirs.get(key) != schema[limit]:
                            found.append(f"{job} {d.name}.{name} {limit} differs")
            if required - filled != set(d.input_schema["required"]):
                found.append(f"{job} {d.name} requires different inputs")
    for name, mine in seen.items():
        if name in server:
            extra = (
                set(server[name]["properties"]) - set(FILLED_IN_BY_CODE[name]) - mine
            )
            if extra:
                found.append(
                    f"{name} has server inputs no definition shows: {sorted(extra)}"
                )
    return found


def test_the_hand_written_definitions_match_the_servers_tool_list(memory):
    assert mismatches(server_tools(memory.store)) == []


def test_a_server_input_the_definitions_leave_out_is_caught(memory):
    tools = server_tools(memory.store)
    tools["read_track_record"]["properties"]["window"] = {"type": "integer"}
    tools["search_episodes"]["properties"]["decided"]["enum"].remove("hold")
    assert mismatches(tools) == [
        "position_review search_episodes.decided allows values the server does not",
        "read_track_record has server inputs no definition shows: ['window']",
    ]


def test_the_llm_never_sees_the_sim_or_the_step():
    for job in JOBS:
        for d in definitions(job, PATTERNS):
            assert not {"sim", "step"} & set(d.input_schema["properties"])
