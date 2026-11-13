# One read-only memory MCP server, reached through hand-written tools

MCP (Model Context Protocol) is the standard way to offer tools to an LLM: a server lists its tools, and a model calls them over the network. The original brief had four MCP servers (market data, broker, memory, and Jev) and connected them to the agent with LangChain's MCP package. Since ADR 0003 the LLM only selects episodes, and it calls exactly three tools, all of them read-only and all of them in memory: search episodes, read episodes in full, and read the track record. We decided that memory is the only MCP server and that it offers those three tools and nothing else. Market data, the broker, and Jev are plain Python modules inside the agent, and code writes to memory through a plain module too. The agent reaches the server with the official MCP SDK's own client (SDK version 2) and three tool definitions written by hand. We chose this because reliability comes first. Code calling code through MCP gains nothing and adds a network hop to every call (Jev answers in about 0.17 seconds and is asked about every asset at every step), plus three more services that can fail and stop a run. And a server with no write tools, logged in to Snowflake with a role that can only read, cannot place an order, call Jev, or change memory, whatever the LLM asks of it.

## Considered Options

- **All four as MCP servers (the original brief).** More MCP to show, but slower runs and more moving parts, for tools no model calls.
- **No MCP server: the LLM's three tools as functions inside the agent.** The simplest option. Rejected: MCP is a requirement of the project, and the separate server is what lets the LLM's side of the system hold a read-only database role.
- **LangChain's current MCP package (`langchain[mcp]`, class `MCPAdapter`), which loads a server's tools automatically.** Rejected for now. Code fills in the run and the step on every tool call so that the LLM cannot ask about a later moment, and the LLM must not see those two inputs. As of 2026-11-13 the package has no documented way to hide an input from the model, and it is marked beta ("The API may change").
- **The package the brief named (`langchain-mcp-adapters`).** Archived, and it only works with version 1 of the MCP SDK, which gets security fixes only.

## Consequences

- The brief's requirement of four custom MCP servers becomes one. Kubernetes runs three long-lived services (the memory server, the API, and the web app) plus the jobs.
- Each of the three tools is described twice: on the server, and in the agent's hand-written definition, which shows the LLM the tool without the run and the step and fills them in. A test compares the hand-written definitions with the server's own tool list, so a mismatch fails.
- The first episode search of a full evaluation, which code runs, goes through the same server tool the LLM uses, so both get the same search.
- The memory server's Snowflake role is a fourth role next to the brief's three, and it can only read. It needs no permission for the embedding model, since nothing is embedded during a run.
- The LLM's tool loop is a small LangGraph graph of our own (model turn, tool turn, repeat). The limits are 6 tool calls and 60 seconds, then one last turn with the tools removed; LangChain's ready-made limits cannot remove the tools for a last turn and have no time limit.
- If LangChain's package leaves beta and learns to hide inputs, switching to it changes the agent only. The server stays as it is.
