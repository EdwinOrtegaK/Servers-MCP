# Servers-MCP

This repository contains multiple **MCP servers** used in the PokeChatbot Host project.  
It includes:

- **Trivial Server (remote/HTTP)** → Provides simple tools (echo, random Pokémon).  
- **GitHub MCP Server** → Accesses GitHub repository metadata, issues, pull requests, and files.  
- **Filesystem MCP Server** → Provides access to local project files.  

## 📦 Prerequisites

- Python **3.10+**
- `pip install -r requirements.txt`
- A working **virtual environment** (`.venv`)
- Internet access (for GitHub MCP and remote servers)

## 🚀 Running the Host

Start the host CLI, which connects to all configured MCP servers:

```bash
python -m src.host.cli
```

Expected output:

```
🚀 Poke VGC — MCP Host
============================================================
✓ Connected to PokeChatbot VGC (local)
✓ Connected to VGC HTTP Remote (remote)
✓ Connected to GitHub MCP Server
✓ Connected to Filesystem MCP Server
```

## 🔧 Available MCP Servers

### 1. **Trivial Remote Server (HTTP)**

This is the MCP server deployed to the cloud. It provides simple demo tools.

#### Tools:
- `echo` → Returns the same text
- `random_pokemon` → Returns a random Pokémon (optionally filtered by type)

#### Example queries:
```text
Trainer: Echo hello world
Trainer: Give me a random water-type Pokémon
```

### 2. **GitHub MCP Server**

Provides access to GitHub repos. Requires the environment variable:

```bash
export GITHUB_TOKEN=your_personal_access_token
```

#### Tools:
- `github_repo_info`
- `github_list_issues`
- `github_get_file`
- `github_search_issues`
- `github_pr_status`
- `github_compare`

#### Example queries:
```text
Trainer: Get info about repo openai/openai-python
Trainer: List issues from my-repo
Trainer: Show file README.md from my-repo
```

### 3. **Filesystem MCP Server**

Provides access to your local project files under the workspace.

#### Tools:
- `files_list`
- `files_read`

#### Example queries:
```text
Trainer: List files in /server
Trainer: Read server/main.py
```

---

## 🧪 Testing Tools

Once the host is running, you can directly try:

```text
Trainer: Give me a Trick Room team
Trainer: Echo "Testing remote echo"
Trainer: List files in data/restricted
Trainer: Get info about repo octocat/Hello-World
Trainer: Give me a random Fire Pokémon
```

## ✅ Summary

- `PokeVGC Team Builder` → Local MCP server for VGC team generation  
- `Trivial HTTP Server` → Remote server deployed to cloud (simple tools)  
- `GitHub MCP Server` → GitHub metadata and repo access  
- `Filesystem MCP Server` → Local file explorer  

All of these are accessible through the **host CLI** with:

```bash
python -m src.host.cli
```
