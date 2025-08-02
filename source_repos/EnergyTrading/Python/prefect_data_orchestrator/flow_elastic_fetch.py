import sys,os
import traceback
from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact
from elasticsearch import Elasticsearch
import json
from datetime import datetime
import pandas as pd
import os


def fetch_data(index_name, es, given_date):
    # Define a query. Here, we fetch all documents from the index
    query = {
        "sort": [
            {
            "_score": {
                "order": "desc"
            }
            }
        ],
        "track_total_hits": False,
        "fields": [
            {
            "field": "*",
            "include_unmapped": "true"
            },
            {
            "field": "timestamp",
            "format": "strict_date_optional_time"
            }
        ],
        "size": 50000,
        "version": False,
        "script_fields": {},
        "stored_fields": [
            "*"
        ],
        "runtime_mappings": {},
        "_source": False,
        "query": {
            "bool": {
            "must": [],
            "filter": [
                    {
                        "range": {
                            "timestamp": {
                                "gte": given_date,
                                "lt": given_date + "||+1d",
                                "format": "strict_date_optional_time"
                            }
                        }
                    }
                ],
            "should": [],
            "must_not": []
            }
        },
        "highlight": {
            "pre_tags": [
            "@kibana-highlighted-field@"
            ],
            "post_tags": [
            "@/kibana-highlighted-field@"
            ],
            "fields": {
            "*": {}
            },
            "fragment_size": 2147483647
        }
        }

    # Use the search method to fetch the data
    return es.search(index=index_name, body=query)['hits']['hits']


@task(log_prints=True, retries=3, retry_delay_seconds=5)
def elastic_fetch_single(algo_id):
    logger = get_run_logger()
    try:
        es = Elasticsearch(hosts="https://127.0.0.1:5601",
                    basic_auth=('elastic', '20hf7*QYhS8aoE7uYJxK'),
                    verify_certs=False)
    except Exception as e:
        logger.error(f"Elasticsearch connection error: {e}")
        return "No data"
    
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    # Example usage
    index_name = f'algo_prod_{algo_id}'
    # Replace with your actual environment
    try:
        df = pd.DataFrame(fetch_data(index_name, es, now))
        df['timestamp'] = df['fields'].apply(lambda d: d['timestamp'][0])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        file_path = f'../app/kibana_daily_dump/{algo_id}_{now}.json'

        # Save DataFrame to JSON
        df.to_json(file_path, orient='records')

        # Get file size
        file_size = os.path.getsize(file_path)
        return file_size
    except Exception as e:
        logger.error(f"fetch data elastic error: {e}")
        return "No data"

@flow
def elastic_fetch(algo_id_list):
    logger = get_run_logger()
    result = {c: "No data" for c in algo_id_list}
    try:
        for algo_id in algo_id_list:
            result[algo_id] = elastic_fetch_single(algo_id)

        # Format dictionary items for HTML content
    except Exception as e:
        logger.error(e)

    markdown_report = f"""
| Country        | status |
|:--------------|-------:|
"""

    for key, value in result.items():
        markdown_report += f"| {key} | {value} |\n"

    create_markdown_artifact(
        key="elastic-fetch-report",
        markdown=markdown_report,
        description="Elastic fetch result report",
    )
    # Connection to Elasticsearch
