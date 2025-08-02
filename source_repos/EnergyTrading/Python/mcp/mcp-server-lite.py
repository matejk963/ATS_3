#!/usr/bin/env python3
"""
Lightweight MCP Server for Energy Trading Database Operations
Only includes database access tools - no file operations or Python execution
"""

import json
import logging
import os
import platform
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to sys.path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil
import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastmcp import FastMCP

from Common.config_load import get_config_path

# Configure logging to stderr only
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr  # Ensure logs go to stderr, not stdout
)
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP("Energy Trading Database MCP Server")


class DatabaseManager:
    """Manages database connections and operations with intelligent routing."""

    def __init__(self):
        self.config_cache = {}
        self.engines = {}
        self.sessions = {}
        logger.info("DatabaseManager: Initializing...")
        self._load_all_configs()
        logger.info(f"DatabaseManager: Initialized with {len(self.config_cache)} configs")

    @staticmethod
    def create_connection_string(config_dict):
        """Create connection string based on database type - matches DB_reader.py format."""
        db_type = config_dict['dbtype']
        username = config_dict['user']
        password = config_dict['password']
        host = config_dict['host']
        port = config_dict['port']
        database = config_dict['database']
        
        if db_type == 'oracle':
            connection_string = f"oracle+oracledb://{username}:{password}" \
                f"@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))" \
                f"(CONNECT_DATA=(SERVER=DEDICATED)(SERVICE_NAME={database})))"
        elif db_type == 'postgre':
            connection_string = f"{db_type}sql://{username}:{password}" \
                f"@{host}:{port}/{database}"
        elif db_type == 'timescaledb':
            connection_string = f"postgresql://{username}:{password}" \
                f"@{host}:{port}/postgres"
        else:
            # Default to PostgreSQL format
            connection_string = f"postgresql://{username}:{password}@{host}:{port}/{database}"
        
        return connection_string

    def _load_all_configs(self):
        """Load all available database configurations."""
        logger.info("DatabaseManager: Starting configuration load...")
        try:
            config_path = get_config_path()
            logger.info(f"Config path: {config_path}")
            
            with open(config_path, "r") as f:
                config = json.load(f)
            
            logger.info(f"Config file loaded. Available sections: {list(config.keys())}")
            
            # Cache all database configurations - using same keys as DB_reader.py
            if "timescaledb" in config:
                self.config_cache["timescaledb"] = config["timescaledb"]
                logger.info(f"TimescaleDB config loaded: {config['timescaledb'].get('host')}:{config['timescaledb'].get('port')}")
            
            if "PostgreSQL" in config:
                self.config_cache["PostgreSQL"] = config["PostgreSQL"] 
                logger.info(f"PostgreSQL config loaded: {config['PostgreSQL'].get('host')}:{config['PostgreSQL'].get('port')}")
            
            # Add any other database configs that might exist
            for db_name, db_config in config.items():
                if db_name not in self.config_cache and isinstance(db_config, dict) and 'dbtype' in db_config:
                    self.config_cache[db_name] = db_config
                    logger.info(f"{db_name} config loaded: {db_config.get('host')}:{db_config.get('port')}")
            
            logger.info(f"Total configs cached: {len(self.config_cache)}")
                
        except Exception as e:
            logger.error(f"Config loading failed: {e}")
            logger.error(traceback.format_exc())
            self.config_cache = {"default": self._get_default_config()}
            logger.info("Using default config as fallback")

    def _get_db_type_for_task(self, task_type: str) -> str:
        """Determine which database to use based on task type."""
        logger.debug(f"Evaluating task_type: '{task_type}'")
        
        # TimescaleDB for time-series and market data operations
        timescale_tasks = [
            "market_data", "time_series", "pricing", "forecast", 
            "historical", "real_time", "analytics", "aggregation"
        ]
        
        # PostgreSQL for general operations, metadata, configurations
        postgres_tasks = [
            "schema", "tables", "metadata", "admin", "general", "config"
        ]
        
        task_lower = task_type.lower()
        
        # Check for TimescaleDB tasks
        matching_ts_tasks = [ts_task for ts_task in timescale_tasks if ts_task in task_lower]
        if matching_ts_tasks:
            if "timescaledb" in self.config_cache:
                logger.info(f"Using TimescaleDB for task '{task_type}'")
                return "timescaledb"
            else:
                logger.warning(f"TimescaleDB config not available, checking alternatives")
        
        # Check for PostgreSQL tasks
        matching_pg_tasks = [pg_task for pg_task in postgres_tasks if pg_task in task_lower]
        if matching_pg_tasks:
            if "PostgreSQL" in self.config_cache:
                logger.info(f"Using PostgreSQL for task '{task_type}'")
                return "PostgreSQL"
            else:
                logger.warning(f"PostgreSQL config not available, checking alternatives")
          # Default fallback order: timescaledb -> PostgreSQL -> first available -> default
        if "timescaledb" in self.config_cache:
            logger.info(f"Fallback to TimescaleDB")
            return "timescaledb"
        elif "PostgreSQL" in self.config_cache:
            logger.info(f"Fallback to PostgreSQL")
            return "PostgreSQL"
        elif self.config_cache:
            # Use first available config
            first_db = list(self.config_cache.keys())[0]
            logger.info(f"Fallback to first available: {first_db}")
            return first_db
        else:
            logger.warning(f"Using default config")
            return "default"

    def _get_default_config(self):
        """Get default database configuration."""
        return {
            "dbtype": "postgre",
            "user": "postgres",
            "password": "password",
            "host": "localhost",
            "port": 5432,
            "database": "postgres"
        }

    def get_connection(self, task_type: str = "general", database: str = None) -> Tuple[Optional[Any], Optional[str]]:
        """Get database connection based on explicit database parameter or task type."""
        if database:
            # Use explicit database parameter if provided
            if database in self.config_cache:
                db_type = database
                logger.info(f"Using explicitly specified database: {database}")
            else:
                logger.error(f"Requested database '{database}' not found in config. Available: {list(self.config_cache.keys())}")
                return None, None
        else:
            # Fall back to task type logic
            db_type = self._get_db_type_for_task(task_type)
        
        try:
            if db_type not in self.engines:
                config = self.config_cache.get(db_type, self._get_default_config())
                connection_string = self.create_connection_string(config)
                self.engines[db_type] = create_engine(connection_string, pool_pre_ping=True)
                self.sessions[db_type] = sessionmaker(bind=self.engines[db_type])
                
            session = self.sessions[db_type]()
            return session, db_type
            
        except Exception as e:
            logger.error(f"Failed to get {db_type} connection: {e}")
            return None, None

    def return_connection(self, session, db_type: str):
        """Return connection to pool."""
        if session:
            try:
                session.close()
            except Exception as e:
                logger.error(f"Error closing {db_type} session: {e}")

    def close_all(self):
        """Close all database connections."""
        for db_type, engine in self.engines.items():
            try:
                engine.dispose()
                logger.info(f"Closed {db_type} connections")
            except Exception as e:
                logger.error(f"Error closing {db_type} connections: {e}")


# Global database manager
db_manager = DatabaseManager()


@mcp.tool()
def get_server_status() -> Dict[str, Any]:
    """Get comprehensive server status including system resources and database connectivity."""
    try:
        status = {
            "status": "running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "server_type": "Energy Trading Database MCP Server",
            "available_databases": list(db_manager.config_cache.keys()),
        }
        
        # System information
        try:
            status["system"] = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:\\').percent,
            }
        except Exception as e:
            status["system"] = {"error": f"Could not get system info: {e}"}
        
        # Test database connections
        status["database_connectivity"] = {}
        for db_type in db_manager.config_cache.keys():
            try:
                session, actual_db_type = db_manager.get_connection(db_type)
                if session:
                    # Test simple query
                    result = session.execute(text("SELECT 1")).fetchone()
                    status["database_connectivity"][db_type] = {
                        "status": "connected",
                        "test_query": "passed" if result and result[0] == 1 else "failed"
                    }
                    db_manager.return_connection(session, actual_db_type)
                else:
                    status["database_connectivity"][db_type] = {"status": "failed", "error": "No connection"}
            except Exception as e:
                status["database_connectivity"][db_type] = {"status": "error", "error": str(e)}
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting server status: {e}")
        return {"status": "error", "error": str(e)}


@mcp.tool()
def list_tables(database: str = None) -> List[Dict[str, Any]]:
    """List all tables in the database with basic information."""
    try:
        session, db_type = db_manager.get_connection("schema", database)
        if not session:
            return [{"error": "Could not connect to database"}]
        
        try:
            # Query to get tables with row counts and sizes
            query = text("""
                SELECT 
                    schemaname,
                    tablename,
                    tableowner,
                    hasindexes,
                    hasrules,
                    hastriggers
                FROM pg_tables 
                WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                ORDER BY schemaname, tablename
            """)
            
            result = session.execute(query)
            tables = []
            
            for row in result:
                table_info = {
                    "schema": row.schemaname,
                    "table": row.tablename,
                    "owner": row.tableowner,
                    "has_indexes": row.hasindexes,
                    "has_rules": row.hasrules,
                    "has_triggers": row.hastriggers,
                    "full_name": f"{row.schemaname}.{row.tablename}"
                }
                
                # Try to get row count (may be slow for large tables)
                try:
                    count_query = text(f"SELECT COUNT(*) FROM {row.schemaname}.{row.tablename}")
                    count_result = session.execute(count_query).fetchone()
                    table_info["row_count"] = count_result[0] if count_result else 0
                except Exception:
                    table_info["row_count"] = "unknown"
                
                tables.append(table_info)
            
            return tables
            
        finally:
            db_manager.return_connection(session, db_type)
            
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        return [{"error": str(e)}]


@mcp.tool()
def get_table_info(table_name: str, schema_name: str = "public", database: str = None) -> Dict[str, Any]:
    """Get detailed information about a specific table including columns, data types, and sample data."""
    try:
        session, db_type = db_manager.get_connection("schema", database)
        if not session:
            return {"error": "Could not connect to database"}
        
        try:
            # Get column information
            columns_query = text("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale
                FROM information_schema.columns 
                WHERE table_schema = :schema_name AND table_name = :table_name
                ORDER BY ordinal_position
            """)
            
            columns_result = session.execute(columns_query, {
                "schema_name": schema_name,
                "table_name": table_name
            })
            
            columns = []
            for row in columns_result:
                column_info = {
                    "name": row.column_name,
                    "type": row.data_type,
                    "nullable": row.is_nullable == "YES",
                    "default": row.column_default,
                }
                
                if row.character_maximum_length:
                    column_info["max_length"] = row.character_maximum_length
                if row.numeric_precision:
                    column_info["precision"] = row.numeric_precision
                if row.numeric_scale:
                    column_info["scale"] = row.numeric_scale
                    
                columns.append(column_info)
            
            if not columns:
                return {"error": f"Table {schema_name}.{table_name} not found"}
            
            # Get sample data (first 5 rows)
            sample_query = text(f"SELECT * FROM {schema_name}.{table_name} LIMIT 5")
            sample_result = session.execute(sample_query)
            sample_data = [dict(row._mapping) for row in sample_result]
            
            # Get table stats
            stats_query = text(f"SELECT COUNT(*) as row_count FROM {schema_name}.{table_name}")
            stats_result = session.execute(stats_query).fetchone()
            row_count = stats_result[0] if stats_result else 0
            
            return {
                "schema": schema_name,
                "table": table_name,
                "columns": columns,
                "row_count": row_count,
                "sample_data": sample_data,
                "database_type": db_type
            }
            
        finally:
            db_manager.return_connection(session, db_type)
            
    except Exception as e:
        logger.error(f"Error getting table info for {schema_name}.{table_name}: {e}")
        return {"error": str(e)}


@mcp.tool()
def run_query(sql_query: str, task_type: str = "general", database: str = None) -> Dict[str, Any]:
    """Execute a SQL query and return results. Use task_type to determine database routing or specify database directly."""
    try:
        session, db_type = db_manager.get_connection(task_type, database)
        if not session:
            return {"error": "Could not connect to database"}
        
        try:
            start_time = datetime.now()
            result = session.execute(text(sql_query))
            end_time = datetime.now()
            
            execution_time = (end_time - start_time).total_seconds()
            
            # Handle different types of queries
            if result.returns_rows:
                # SELECT queries
                rows = result.fetchall()
                data = [dict(row._mapping) for row in rows]
                
                return {
                    "success": True,
                    "data": data,
                    "row_count": len(data),
                    "execution_time_seconds": execution_time,
                    "database_type": db_type,
                    "query": sql_query[:200] + "..." if len(sql_query) > 200 else sql_query
                }
            else:
                # INSERT, UPDATE, DELETE queries
                session.commit()
                rows_affected = result.rowcount
                
                return {
                    "success": True,
                    "rows_affected": rows_affected,
                    "execution_time_seconds": execution_time,
                    "database_type": db_type,
                    "query": sql_query[:200] + "..." if len(sql_query) > 200 else sql_query
                }
                
        finally:
            db_manager.return_connection(session, db_type)
            
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return {
            "success": False,
            "error": str(e),
            "query": sql_query[:200] + "..." if len(sql_query) > 200 else sql_query
        }


@mcp.tool()
def analyze_query_performance(sql_query: str, task_type: str = "analytics", database: str = None) -> Dict[str, Any]:
    """Analyze query performance using EXPLAIN ANALYZE."""
    try:
        session, db_type = db_manager.get_connection(task_type, database)
        if not session:
            return {"error": "Could not connect to database"}
        
        try:
            # Run EXPLAIN ANALYZE
            explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql_query}"
            result = session.execute(text(explain_query))
            explain_result = result.fetchone()[0]
            
            return {
                "success": True,
                "explain_result": explain_result,
                "database_type": db_type,
                "original_query": sql_query[:200] + "..." if len(sql_query) > 200 else sql_query
            }
            
        finally:
            db_manager.return_connection(session, db_type)
            
    except Exception as e:
        logger.error(f"Error analyzing query performance: {e}")
        return {
            "success": False,
            "error": str(e),
            "query": sql_query[:200] + "..." if len(sql_query) > 200 else sql_query
        }


@mcp.tool()
def get_market_data_summary(start_date: str = None, end_date: str = None, database: str = None) -> Dict[str, Any]:
    """Get a summary of market data from the database. Uses TimescaleDB for time-series queries."""
    try:
        session, db_type = db_manager.get_connection("market_data", database)
        if not session:
            return {"error": "Could not connect to database"}
        
        try:
            # Build dynamic query based on available parameters
            where_conditions = []
            params = {}
            
            if start_date:
                where_conditions.append("timestamp >= :start_date")
                params["start_date"] = start_date
                
            if end_date:
                where_conditions.append("timestamp <= :end_date")
                params["end_date"] = end_date
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            # Try to find market data tables (common names)
            tables_to_check = ["market_data", "prices", "trading_data", "spot_prices"]
            
            for table_name in tables_to_check:
                try:
                    query = text(f"""
                        SELECT 
                            COUNT(*) as record_count,
                            MIN(timestamp) as earliest_date,
                            MAX(timestamp) as latest_date,
                            COUNT(DISTINCT DATE(timestamp)) as trading_days
                        FROM {table_name}
                        {where_clause}
                    """)
                    
                    result = session.execute(query, params).fetchone()
                    
                    if result and result[0] > 0:
                        return {
                            "success": True,
                            "table_name": table_name,
                            "record_count": result[0],
                            "date_range": {
                                "earliest": str(result[1]) if result[1] else None,
                                "latest": str(result[2]) if result[2] else None,
                                "trading_days": result[3]
                            },
                            "database_type": db_type,
                            "filters": {
                                "start_date": start_date,
                                "end_date": end_date
                            }
                        }
                        
                except Exception:
                    continue  # Try next table
            
            return {"error": "No market data tables found with the expected schema"}
            
        finally:
            db_manager.return_connection(session, db_type)
            
    except Exception as e:
        logger.error(f"Error getting market data summary: {e}")
        return {"error": str(e)}


@mcp.tool()
def list_available_databases() -> Dict[str, Any]:
    """List all available database configurations that can be used with the database parameter."""
    try:
        databases = {}
        for db_name, config in db_manager.config_cache.items():
            databases[db_name] = {
                "database_type": config.get("dbtype", "unknown"),
                "host": config.get("host", "unknown"),
                "port": config.get("port", "unknown"),
                "database": config.get("database", "unknown"),
                "user": config.get("user", "unknown")
            }
        
        return {
            "success": True,
            "available_databases": databases,
            "total_count": len(databases),
            "usage": "Use the database name as the 'database' parameter in other tools (e.g., database='timescaledb')"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    logger.info("Starting Energy Trading Database MCP Server...")
    logger.info(f"Available database configs: {list(db_manager.config_cache.keys())}")
    
    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    finally:
        logger.info("Shutting down server...")
        db_manager.close_all()
        logger.info("Server shutdown complete")