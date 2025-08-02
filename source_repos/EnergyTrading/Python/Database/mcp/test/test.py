"""
Test script for the TimescaleDB MCP server.
This script connects to the MCP server and tests its endpoints.
"""

import sys
import os
import json
import requests
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError
from pprint import pprint

# Add parent directory to path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def test_server(url="http://localhost:23456"):
    """Test the MCP server endpoints"""
    print(f"Testing MCP server at {url}...")
    
    # Test 1: Get list of tables
    print("\nTest 1: Get list of tables")
    try:
        data = {
            "method": "get_tables",
            "params": {}
        }
        response = requests.post(url, json=data)
        if response.status_code == 200:
            tables = response.json()
            print("Success! Tables returned:")
            pprint(tables)
        else:
            print(f"Failed with status code {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: Get schema information
    print("\nTest 2: Get schema information")
    try:
        data = {
            "method": "get_schema",
            "params": {}
        }
        response = requests.post(url, json=data)
        if response.status_code == 200:
            schema = response.json()
            print("Success! Schema returned for tables:")
            print(list(schema.keys()))
            
            # Print details of the 'trades' table if it exists
            if 'trades' in schema:
                print("\nDetails of 'trades' table:")
                trade_cols = [col['name'] for col in schema['trades']['columns']]
                print(f"Columns: {trade_cols}")
                print(f"Is hypertable: {schema['trades'].get('is_hypertable', False)}")
                if schema['trades'].get('is_hypertable', False):
                    print(f"Time column: {schema['trades'].get('time_column', 'N/A')}")
        else:
            print(f"Failed with status code {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 3: Get sample data
    print("\nTest 3: Get sample data from 'trades' table")
    try:
        data = {
            "method": "sample_data",
            "params": {
                "table_name": "trades",
                "limit": 3
            }
        }
        response = requests.post(url, json=data)
        if response.status_code == 200:
            try:
                sample_data = response.json()
                print("Success! Sample data returned:")
                pprint(sample_data)
            except RequestsJSONDecodeError as je:
                print("DEBUG: Entered requests.exceptions.JSONDecodeError block.")
                print(f"Failed to decode JSON. Status: {response.status_code}. Error: {je}")
                print("Raw response text:")
                try:
                    print(response.text)
                except Exception as print_e:
                    print(f"DEBUG: Error printing response.text: {print_e}")
            except Exception as e_inner:
                print(f"DEBUG: Entered other inner Exception block: {type(e_inner).__name__}")
                print(f"Error after successful status code: {e_inner}")
                print("Raw response text (if available):")
                try:
                    print(response.text)
                except Exception as print_e:
                    print(f"DEBUG: Error printing response.text: {print_e}")
        else:
            print(f"Failed with status code {response.status_code}")
            print("Raw response text:")
            print(response.text)
    except Exception as e_outer:
        print(f"DEBUG: Entered outer Exception block: {type(e_outer).__name__}")
        print(f"Error: {e_outer}")

    # Test 4: Query experimental_predictors for specific author and sort pred_id
    print("\nTest 4: Query and sort pred_id for MatejKrajcovic")
    try:
        query_str = "SELECT DISTINCT pred_id FROM experimental_predictors WHERE author = :author_name"
        query_params = {"author_name": "MatejKrajcovic"}
        data = {
            "method": "query",
            "params": {
                "query": query_str,
                "params": query_params
            }
        }
        response = requests.post(url, json=data)
        if response.status_code == 200:
            try:
                query_result = response.json()
                # Extract pred_id list
                pred_ids = [row['pred_id'] for row in query_result.get('data', query_result.get('result', [])) if 'pred_id' in row]
                # Sort by the first substring before '_'
                pred_ids_sorted = sorted(pred_ids, key=lambda x: str(x).split('_')[0])
                print("Sorted pred_id values:")
                pprint(pred_ids_sorted)
            except RequestsJSONDecodeError as je:
                print(f"Failed to decode JSON. Status: {response.status_code}. Error: {je}")
                print("Raw response text:")
                print(response.text)
            except Exception as e_inner:
                print(f"Error processing query response: {e_inner}")
                print("Raw response text (if available):")
                print(response.text)
        else:
            print(f"Query failed with status code {response.status_code}")
            print("Raw response text:")
            print(response.text)
    except Exception as e:
        print(f"Error during Test 4: {e}")
    
    print("\nTests completed!")

if __name__ == "__main__":
    test_server()
