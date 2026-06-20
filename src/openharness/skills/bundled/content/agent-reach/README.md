# Agent Reach dev2 Bundled Skill Adapter

This directory is the dev2 bundled-skill adapter for the upstream Agent Reach project.

Source consulted:

- `D:\Agent-Reach-main\Agent-Reach-main`
- `D:\Agent-Reach-main\Agent-Reach-main\agent_reach\skill\SKILL.md`
- `D:\Agent-Reach-main\Agent-Reach-main\agent_reach\skill\references\*.md`

The adapter keeps Agent Reach's skill shape and route categories, but dev2 does not package the upstream executable platform runtime or high-risk platform setup flows. User-local configuration remains the user's responsibility and must not be committed or bundled.

Included:

- `SKILL.md`
- `SKILL_en.md`
- `references/`
- `LICENSE`
- `.env.example`

Excluded:

- `agent_reach/` executable Python package
- platform automation scripts and tests
- real `.env`, keys, cookies, tokens, proxy credentials, browser sessions
- one-click Cookie/login/proxy/bypass flows
