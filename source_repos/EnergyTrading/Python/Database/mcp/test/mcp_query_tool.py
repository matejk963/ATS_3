"""
MCP Query Tool

This script allows you to run arbitrary SQL queries against the TimescaleDB MCP server and get results in a convenient way.
"""

import sys
import os
import json
import requests
from pprint import pprint

# Add parent directory to path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

MCP_URL = "http://localhost:23456"

def run_mcp_query(query, params=None, url=MCP_URL):
    data = {
        "method": "query",
        "params": {
            "query": query,
            "params": params or {}
        }
    }
    response = requests.post(url, json=data)
    if response.status_code == 200:
        try:
            result = response.json()
            return result
        except Exception as e:
            print(f"Error decoding JSON: {e}")
            print("Raw response:", response.text)
            return None
    else:
        print(f"Query failed with status code {response.status_code}")
        print("Raw response text:", response.text)
        return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run a query against the MCP server.")
    parser.add_argument("query", type=str, help="SQL query to run (use :param for parameters)")
    parser.add_argument("--params", type=str, default=None, help="JSON string of parameters, e.g. '{\"author_name\": \"MatejKrajcovic\"}'")
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else None
    result = run_mcp_query(args.query, params)
    print("\nQuery result:")
    pprint(result)
