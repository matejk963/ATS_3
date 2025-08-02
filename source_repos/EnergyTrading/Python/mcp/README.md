# Enhanced Energy Trading MCP Server

A comprehensive Model Context Protocol (MCP) server designed for energy trading operations, providing advanced database tools, system monitoring, and trading-specific functionality.

## Features

### Database Tools
- **Enhanced Query Execution**: Run SQL queries with safety checks and performance monitoring
- **Table Management**: List and analyze table structures with metadata
- **Query Performance Analysis**: Use EXPLAIN ANALYZE for query optimization
- **Connection Pooling**: Efficient database connection management

### System Monitoring
- **Health Checks**: Comprehensive system and database health monitoring
- **Performance Metrics**: CPU, memory, and disk usage tracking
- **Resource Monitoring**: Real-time system resource analysis

### File Operations
- **Secure File Management**: Create, list, and manage files with security checks
- **Python Script Execution**: Run and test Python scripts with monitoring
- **Test File Creation**: Generate test files for development and testing

### Energy Trading Specific
- **Market Data Analysis**: Specialized tools for analyzing market data
- **Data Quality Checks**: Validate trading data integrity and completeness
- **Performance Optimization**: Trading-specific query and data optimizations

## Installation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Database**:
   - Ensure your database configuration is set up in the Common/config_load.py
   - Verify PostgreSQL connection parameters

3. **Set up VS Code Integration**:
   - Copy `mcp.json` to your VS Code MCP servers configuration
   - Place instruction files in `.vscode/instructions/`
   - Place prompt files in `.vscode/prompts/`

## VS Code Integration

### Instruction Files
The server includes specialized instruction files for:
- **Python Coding Guidelines** (`python-coding-guidelines.instructions.md`)
- **MCP Server Development** (`mcp-server-guidelines.instructions.md`)
- **Energy Trading Domain** (`energy-trading-domain.instructions.md`)

### Prompt Files
Pre-configured prompts for common tasks:
- **Database Schema Analysis** (`analyze-database-schema.prompt.md`)
- **Data Processor Creation** (`create-data-processor.prompt.md`)
- **System Health Check** (`system-health-check.prompt.md`)
- **Market Data Analysis** (`market-data-analysis.prompt.md`)

## Available Tools

### Database Tools
- `get_server_status()` - System and database health metrics
- `list_tables(schema)` - List tables with metadata
- `get_table_info(table_name, schema)` - Detailed table information
- `run_query(sql, max_rows, return_format)` - Execute SQL queries safely
- `analyze_query_performance(sql)` - Query performance analysis

### File Operations
- `run_python_file(file_path, args, timeout)` - Execute Python scripts
- `create_test_file(file_name, content, directory)` - Create test files
- `list_files(directory, pattern, recursive)` - List directory contents

### Energy Trading
- `get_market_data_summary(table_name, date_column, value_column)` - Market data analysis

## Usage Examples

### Running the Server
```bash
python mcp-server-enhanced.py
```

### Using in VS Code
1. Configure the server in your MCP settings
2. Use prompt files with `/` commands in chat
3. Let instruction files guide AI responses automatically

### Direct Tool Usage
The server responds to MCP protocol requests and can be integrated with any MCP-compatible client.

## Configuration

### Database Configuration
The server reads database configuration from your existing config setup. Ensure the following structure:
```json
{
  "PostgreSQL": {
    "host": "localhost",
    "port": 5432,
    "user": "username",
    "password": "password"
  }
}
```

### MCP Configuration
Add to your VS Code settings or mcp.json:
```json
{
  "servers": {
    "energy-trading-mcp": {
      "command": "python",
      "args": ["mcp-server-enhanced.py"],
      "env": {
        "PYTHONPATH": "path/to/your/python/project"
      }
    }
  }
}
```

## Security Features

- **SQL Injection Protection**: Parameterized queries and keyword filtering
- **File Access Control**: Restricted to current directory and subdirectories
- **Query Safety**: Only SELECT statements allowed for general queries
- **Timeout Protection**: Configurable timeouts for all operations

## Performance Features

- **Connection Pooling**: Efficient database connection reuse
- **Query Monitoring**: Execution time tracking and analysis
- **Resource Monitoring**: System resource usage tracking
- **Caching**: Intelligent caching for frequently accessed data

## Logging

The server provides comprehensive logging:
- Structured logging format
- File and console output
- Error tracking and debugging
- Performance metrics logging

## Development

### Adding New Tools
1. Create a new function decorated with `@mcp.tool()`
2. Include comprehensive docstrings
3. Implement proper error handling
4. Add logging for monitoring

### Testing
```bash
pytest tests/
```

### Code Quality
```bash
black mcp-server-enhanced.py
flake8 mcp-server-enhanced.py
```

## Energy Trading Considerations

This server is specifically designed for energy trading environments and includes:
- Timezone-aware datetime handling
- Financial precision for monetary calculations
- Market data validation and quality checks
- Trading-specific performance optimizations
- Regulatory compliance logging

## License

This project is part of the Energy Trading system and follows the same licensing terms.

## Deployment

### Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Deploy the server
python deploy.py deploy

# Or start manually
python deploy.py start
```

### VS Code Integration
This MCP server is designed to work with VS Code v1.100+ and includes:

- **Instruction Files**: Automatic context application for energy trading domain
- **Prompt Files**: Reusable prompts for common tasks
- **Task Integration**: Pre-configured VS Code tasks for server management
- **IntelliSense**: Energy trading specific code completion

See [VS_CODE_INTEGRATION.md](VS_CODE_INTEGRATION.md) for detailed usage instructions.

### Using VS Code Tasks
1. Open Command Palette (`Ctrl+Shift+P`)
2. Type "Tasks: Run Task"
3. Select:
   - "Start MCP Server" - Start the server in background
   - "Test MCP Server" - Run the test suite

### Server Management
```bash
# Check server status
python deploy.py status

# Stop server
python deploy.py stop

# Run health checks
python deploy.py test
```
