"""
MCP Query Example: Sorted pred_id for MatejKrajcovic

This script demonstrates using the importable MCP query tool to fetch and sort pred_id values for a specific author.
"""

from mcp_query import run_mcp_query
from pprint import pprint

def get_sorted_pred_ids_for_author(author_name):
    query = "SELECT DISTINCT pred_id FROM experimental_predictors WHERE author = :author_name"
    params = {"author_name": author_name}
    result = run_mcp_query(query, params)
    if not result or 'error' in result:
        print("Error or no result:", result)
        return
    # Extract pred_id list
    rows = result.get('data', result.get('result', []))
    pred_ids = [row['pred_id'] for row in rows if 'pred_id' in row]
    pred_ids_sorted = sorted(pred_ids, key=lambda x: str(x).split('_')[0])
    print("Sorted pred_id values:")
    pprint(pred_ids_sorted)

if __name__ == "__main__":
    get_sorted_pred_ids_for_author("MatejKrajcovic")
