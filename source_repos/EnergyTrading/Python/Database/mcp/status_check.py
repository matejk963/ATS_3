#!/usr/bin/env python3
"""
MCP Setup Status Check
"""
import os
import json

def check_mcp_status():
    """Check the current status of MCP setup."""
    print("🔍 MCP Setup Status Check")
    print("=" * 40)
    
    # Check core files
    core_files = {
        "MCP Server": "mcp-server-enhanced.py",
        "Configuration": "mcp.json", 
        "Requirements": "requirements.txt",
        "README": "README.md"
    }
    
    print("\n📁 Core Files:")
    for name, file in core_files.items():
        status = "✓" if os.path.exists(file) else "✗"
        print(f"  {status} {name}: {file}")
    
    # Check VS Code integration
    vscode_files = {
        "VS Code Settings": ".vscode/settings.json",
        "VS Code Tasks": ".vscode/tasks.json",
        "Launch Config": ".vscode/launch.json"
    }
    
    print("\n🔧 VS Code Integration:")
    for name, file in vscode_files.items():
        status = "✓" if os.path.exists(file) else "✗"
        print(f"  {status} {name}: {file}")
    
    # Check instruction files
    instructions_dir = ".vscode/instructions"
    print(f"\n📝 Instruction Files ({instructions_dir}):")
    if os.path.exists(instructions_dir):
        for file in os.listdir(instructions_dir):
            if file.endswith('.instructions.md'):
                print(f"  ✓ {file}")
    else:
        print("  ✗ Instructions directory not found")
    
    # Check prompt files  
    prompts_dir = ".vscode/prompts"
    print(f"\n💬 Prompt Files ({prompts_dir}):")
    if os.path.exists(prompts_dir):
        for file in os.listdir(prompts_dir):
            if file.endswith('.prompt.md'):
                print(f"  ✓ {file}")
    else:
        print("  ✗ Prompts directory not found")
    
    # Check JSON files validity
    print("\n🔍 Configuration Validation:")
    json_files = ["mcp.json", ".vscode/settings.json", ".vscode/tasks.json"]
    for file in json_files:
        if os.path.exists(file):
            try:
                with open(file, 'r') as f:
                    json.load(f)
                print(f"  ✓ {file} - Valid JSON")
            except json.JSONDecodeError:
                print(f"  ✗ {file} - Invalid JSON")
        else:
            print(f"  ✗ {file} - Not found")
    
    # Check database tools availability
    print("\n🗄️  Database Tools:")
    try:
        import psycopg2
        print("  ✓ PostgreSQL driver (psycopg2) available")
    except ImportError:
        print("  ✗ PostgreSQL driver missing")
    
    try:
        import fastmcp
        print("  ✓ FastMCP library available")
    except ImportError:
        print("  ✗ FastMCP library missing")
    
    try:
        import pandas
        print("  ✓ Pandas library available")
    except ImportError:
        print("  ✗ Pandas library missing")
    
    print("\n" + "=" * 40)
    print("Status check complete! ✨")

if __name__ == "__main__":
    check_mcp_status()
