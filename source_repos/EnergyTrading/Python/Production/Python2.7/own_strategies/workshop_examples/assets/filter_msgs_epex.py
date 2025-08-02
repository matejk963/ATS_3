import json


def extract_feed_to_file(input_path, output_path, min_delivery_start, max_delivery_end, areas=(), product_ids=(),
                         min_timestamp=0):
    with open(input_path, "r") as f:
        content = (json.loads(line) for line in f)
        filtered_content = filter_feed_for_products(content, min_delivery_start, max_delivery_end, areas=areas,
                                                    product_ids=product_ids, min_timestamp=min_timestamp)

        with open(output_path, "w") as f:
            for line in filtered_content:
                f.write(json.dumps(line) + "\n")


def filter_feed_for_products(content, min_delivery_start, max_delivery_end, areas=(), product_ids=(), min_timestamp=0):
    filtered_content = []

    my_ids = set(product_ids)
    for c in content:
        if c["message_type"] in ("order_book", "public_trade"):
            if c["timestamp"] < min_timestamp:
                continue
            c["data"] = [d for d in c["data"] if d["product_id"] in my_ids]

        elif c["message_type"] == "product":
            new_data = [d for d in c["data"] if
                        d["delivery_start"] >= min_delivery_start and d["delivery_end"] <= max_delivery_end]
            for d in new_data:
                d["delivery_area_states"] = {k: v for k, v in d["delivery_area_states"].items() if k in areas}
                d["trading_phases"] = {k: v for k, v in d["trading_phases"].items() if k in areas}
                my_ids.add(d["product_id"])
            c["data"] = new_data

        if c["data"]:
            filtered_content.append(c)

    return filtered_content
