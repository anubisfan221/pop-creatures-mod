# Pop Creatures Mod

Welcome to the **Pop Creatures Mod**, a multi‑fandom expansion for **ARK: Survival Ascended**. This project builds on the foundation of the Dragons of Berk mod and introduces creatures from across movies, TV, comics, and games. Each creature is lovingly crafted with custom models, animations, abilities, and gear.

This repository hosts the source for the mod's documentation, issue tracking, and GitHub Pages site. It does **not** contain any cooked Dev Kit assets. Those will be distributed as releases.

## Getting Started

See the docs in the `/docs` folder for installation instructions, spawn commands, and developer notes.

## Contributing

Contributions are welcome! Please read `CONTRIBUTING.md` to get started.

## License

This project is licensed under the MIT License – see the `LICENSE` file for details.

## Sims 4 Mods AI Organizer Utility

A standalone helper script is included at `sims4_mod_organizer.py` for players who want to scan and organize a Sims 4 Mods folder.

### What it does
- Scans mod files (`.package`, `.ts4script`, and common archives)
- Categorizes files with rule-based matching
- Uses an optional AI fallback classifier (OpenAI-compatible API) for unknown files
- Detects duplicate files via SHA-256 hash
- Generates a JSON inventory report
- Can preview or apply file moves into category folders

### Quick start
```bash
python3 sims4_mod_organizer.py "/path/to/The Sims 4/Mods"
python3 sims4_mod_organizer.py "/path/to/The Sims 4/Mods" --organize
python3 sims4_mod_organizer.py "/path/to/The Sims 4/Mods" --organize --apply
```

### Optional AI setup
Set these environment variables before running:
- `OPENAI_API_KEY` (required for AI fallback)
- `OPENAI_MODEL` (optional, default `gpt-4o-mini`)
- `OPENAI_BASE_URL` (optional for OpenAI-compatible providers)
