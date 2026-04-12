"""Starter lists offered by the Phase 5.3 onboarding wizard.

PRESET_CATEGORIES extends the minimal src.config._DEFAULT_CATEGORIES
with a broader starter set so new users have sensible defaults to
pick from.

PRESET_CHANNELS is intentionally empty — populating it with specific
YouTube handles would mean making up channel IDs the bot never
verified. The wizard handles an empty list by skipping the
"pick channels" step entirely. Users add channels later via /add.
To ship a curated list, add entries manually before first deploy:

    {"category": "claude-code", "name": "Anthropic",
     "url": "https://youtube.com/@anthropic-ai"}
"""

from __future__ import annotations

# slug → human description (used by both the wizard UI and as the
# description argument when add_category() writes it to categories.yml)
PRESET_CATEGORIES: dict[str, str] = {
    "ai-agents":       "AI agents, multi-agent systems, Claude Code patterns",
    "claude-code":     "Claude Code workflows, hooks, skills, sub-agents",
    "llm-apps":        "Building apps with LLMs, RAG, cost optimization",
    "ai-research":     "AI papers, benchmarks, new model releases",
    "devops-selfhost": "Docker, Hetzner, self-hosting, homelab",
    "wordpress":       "WordPress & WooCommerce development",
    "automation":      "n8n, Zapier, workflow automation",
    "web-dev":         "Frontend, backend, fullstack web",
    "productivity":    "Obsidian, note-taking, second-brain systems",
    "science":         "General science, physics, biology explainers",
}

# Hand-curated list of trusted starter channels. Each entry must have
# a real, stable YouTube handle. Keep 3-5 per category max. Empty list
# is fine — the wizard skips the channels step in that case.
PRESET_CHANNELS: list[dict[str, str]] = []
