from elasticsearch import Elasticsearch
import json
from datetime import datetime

# Initialize the Elasticsearch client
def inject_index(data, env):
    es = Elasticsearch(hosts="https://192.168.10.91:5009",
                        basic_auth=('elastic', '20hf7*QYhS8aoE7uYJxK'),
                        verify_certs=False)

    data['timestamp'] = datetime.now()
    data.update({
        "mappings": {
            "properties": {
                "timestamp": { "type": "date" }
            }
    }})

    # Call the function with your data
    response = es.index(index=f'algo_{env}_'+data['strategy_id'], document=data)
