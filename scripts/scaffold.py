import os

dirs = [
    "app/api/v1",
    "app/core",
    "app/models",
    "app/schemas",
    "app/repositories",
    "app/services",
    "app/agents",
    "app/agents/prompts",
    "app/tools",
    "app/tools/mcp",
    "app/mcp_servers",
    "app/sandbox",
    "app/llm",
    "app/llm/providers",
    "app/guardrails",
    "app/evaluation",
    "app/evaluation/tasks",
    "app/observability",
    "app/workers",
    "tests/unit",
    "tests/integration",
    "tests/agent",
    "tests/security",
    "docs/adr",
    "scripts",
    "migrations",
    "docker",
]

for d in dirs:
    os.makedirs(d, exist_ok=True)
    if not d.startswith(("docs", "scripts", "migrations", "docker", "app/agents/prompts", "app/evaluation/tasks")):
        init_file = os.path.join(d, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w", encoding="utf-8") as f:
                f.write(f'"""Package for {d}."""\n')

print("All package directories and __init__.py files created.")
