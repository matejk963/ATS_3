from Database.mcp.test.mcp_query import run_mcp_query
from pprint import pprint
from collections import defaultdict

def get_sorted_pred_ids_for_author(author_name):
    query = "SELECT DISTINCT pred_id FROM experimental_predictors WHERE author = :author_name"
    params = {"author_name": author_name}
    result = run_mcp_query(query, params)
    pred_ids = [row['pred_id'] for row in result.get('data', result.get('result', [])) if 'pred_id' in row]
    
    # Group by prefix
    grouped_pred_ids = defaultdict(list)
    for pred_id in pred_ids:
        prefix = str(pred_id).split('_')[0]
        grouped_pred_ids[prefix].append(pred_id)
    
    # Sort within groups and then by prefix
    sorted_grouped_pred_ids = {}
    for prefix in sorted(grouped_pred_ids.keys()):
        sorted_grouped_pred_ids[prefix] = sorted(grouped_pred_ids[prefix])
        
    return sorted_grouped_pred_ids

if __name__ == "__main__":
    author = "MatejKrajcovic"
    grouped_ids = get_sorted_pred_ids_for_author(author)
    print(f"Pred_id values for author '{author}', grouped by prefix and sorted:")
    pprint(grouped_ids)
