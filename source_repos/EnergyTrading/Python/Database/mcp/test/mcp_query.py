"""
MCP Query Tool (importable)

This module provides a function to run SQL queries against the MCP server and return results for use in other scripts or by an agent.
"""

import requests
import json
from pprint import pprint
from collections import defaultdict # Added for grouping
import pandas as pd # Import pandas

MCP_URL = "http://localhost:23456"

def run_mcp_query(query, params=None, url=MCP_URL):
    data = {
        "method": "query",
        "params": {
            "query": query,
            "params": params or {}
        }
    }
    print(f"[run_mcp_query] Preparing to send request to {url}") # New debug print
    print(f"[run_mcp_query] Request data: {json.dumps(data, indent=2)}") # New debug print
    try:
        print("[run_mcp_query] Attempting requests.post...") # New debug print
        response = requests.post(url, json=data, timeout=120) # Increased timeout to 120s
        print(f"[run_mcp_query] requests.post completed. Status code: {response.status_code}") # New debug print
        

        response.raise_for_status() # Raise HTTPError for bad responses (4XX or 5XX)
        
        print("[run_mcp_query] Attempting to decode JSON response (response.json())...") # New debug print
        json_response = response.json()
        print("[run_mcp_query] JSON response decoded successfully.") # New debug print
        
        # Check for application-level errors if your MCP server returns them in the JSON body
        if json_response.get("error"):
            print(f"MCP Server Error: {json_response['error']}")
            return pd.DataFrame() # Return empty DataFrame on server error

        # Extract data - adjust keys based on actual server response structure
        # Common patterns are a list directly, or a dict with a 'data' or 'result' key
        if isinstance(json_response, list):
            return pd.DataFrame(json_response)
        elif 'data' in json_response and isinstance(json_response['data'], list):
            return pd.DataFrame(json_response['data'])
        elif 'result' in json_response and isinstance(json_response['result'], list):
            return pd.DataFrame(json_response['result'])
        else:
            print(f"Unexpected JSON structure: {json_response}")
            return pd.DataFrame() # Return empty DataFrame if structure is not recognized

    except requests.exceptions.HTTPError as http_err:
        print(f"[run_mcp_query] HTTP error occurred: {http_err}") # Modified
        if response is not None:
            print(f"[run_mcp_query] Raw response text: {response.text}") # Added
        return pd.DataFrame()
    except requests.exceptions.ConnectionError as conn_err:
        print(f"[run_mcp_query] Connection error occurred: {conn_err}") # Modified
        return pd.DataFrame()
    except requests.exceptions.Timeout as timeout_err:
        print(f"[run_mcp_query] Timeout error occurred: {timeout_err}") # Modified
        return pd.DataFrame()
    except requests.exceptions.RequestException as req_err:
        print(f"[run_mcp_query] An error occurred during the request: {req_err}") # Modified
        return pd.DataFrame()
    except json.JSONDecodeError as json_err:
        print(f"[run_mcp_query] Error decoding JSON response: {json_err}") # Modified
        raw_text = response.text if 'response' in locals() and response is not None else "No response object or text available"
        print(f"[run_mcp_query] Raw response text: {raw_text}") # Modified
        return pd.DataFrame()
    except Exception as e:
        print(f"[run_mcp_query] An unexpected error occurred in run_mcp_query: {e}") # Modified
        print(f"[run_mcp_query] Query was: {query}") # Added
        if 'response' in locals() and response is not None:
            print(f"[run_mcp_query] Raw response text (if available): {response.text}") # Added
        return pd.DataFrame()

def get_sorted_pred_ids_for_author(author_name):
    query = 'SELECT DISTINCT pred_id FROM "public"."experimental_predictors" WHERE author = \'MatejKrajcovic\''
    result = run_mcp_query(query)
    
    # Correctly handle result as a DataFrame
    if isinstance(result, pd.DataFrame):
        if not result.empty and 'pred_id' in result.columns:
            pred_ids = result['pred_id'].dropna().astype(str).tolist()
        else:
            pred_ids = []
    else:
        pred_ids = []

    grouped_pred_ids = defaultdict(list)
    for pred_id in pred_ids:
        prefix = str(pred_id).split('_')[0]
        grouped_pred_ids[prefix].append(str(pred_id))
    
    # Sort pred_ids within each group and then sort groups by prefix
    sorted_grouped_pred_ids = {}
    for prefix in sorted(grouped_pred_ids.keys()):
        sorted_grouped_pred_ids[prefix] = sorted(grouped_pred_ids[prefix])
    
    return sorted_grouped_pred_ids

if __name__ == "__main__":
    author = "MatejKrajcovic"
    grouped_sorted_ids = get_sorted_pred_ids_for_author(author)
    
    if grouped_sorted_ids:
        print(f"Grouped and sorted pred_id values for author '{author}':")
        for prefix, ids in grouped_sorted_ids.items():
            print(f"  Group: {prefix}")
            for pred_id_val in ids:
                print(f"    - {pred_id_val}")
    else:
        print(f"No pred_id values found or error occurred for author '{author}'.")
