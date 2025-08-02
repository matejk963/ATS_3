# TimescaleDB MCP Server

A Model Context Protocol (MCP) server for TimescaleDB that enhances AI assistance with energy trading data processing code.

## Overview

This server provides GitHub Copilot with context about your TimescaleDB database schema, improving the quality of generated SQL queries and data processing code.

## Features

- Database schema discovery
- TimescaleDB hypertable metadata
- Table relationships via foreign keys
- Sample data access
- Simple HTTP API

## Usage

### Starting the Server

Run the server using one of these methods:

1. Use the batch file:
   ```
   run_mcp_server.bat
   ```

2. From Python:
   ```
   python Database/mcp/server.py
   ```

3. From PowerShell:
   ```
   ./Database/mcp/run_mcp_server.ps1
   ```

The server runs on port 23456 by default.

### Testing the Server

Run the test script to verify the server is working properly:

```
python Database/mcp/test.py
```

### Using with GitHub Copilot

Once the server is running, Copilot will automatically use the database schema information when generating code. No additional steps are required.

## Troubleshooting

- If you encounter connection issues, make sure your TimescaleDB instance is running and accessible
- Check that the server is running on port 23456
- If VS Code isn't connecting to the MCP server, verify the settings in `.vscode/settings.json`
