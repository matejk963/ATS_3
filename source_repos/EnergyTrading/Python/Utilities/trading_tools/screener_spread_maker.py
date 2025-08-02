import numpy as np
import itertools
import pandas as pd

def get_valid_indices(N, allowed_offsets):
    """
    Create an N x N index grid and return (i, j) indices where:
      - Only the lower half (including the diagonal) is considered (i >= j).
      - The offset (i - j) is in allowed_offsets.
      
    :param N: Number of periods (matrix dimension).
    :param allowed_offsets: Allowed offsets (e.g. [1, 2] or [0, 1]).
    :return: Two numpy arrays (i_indices, j_indices) of valid indices.
    """
    i = np.arange(N).reshape(-1, 1)   # shape (N,1)
    j = np.arange(N).reshape(1, -1)     # shape (1,N)
    offsets = i - j
    mask = (i >= j) & np.isin(offsets, allowed_offsets)
    valid_i, valid_j = np.where(mask)
    return valid_i, valid_j

def is_subperiod(small, large):
    """
    Determine if the period 'small' is considered a subperiod of 'large'.
    
    In the default case, full containment is required:
        large[0] <= small[0] and small[1] <= large[1]
    
    However, if 'small' is a week (i.e. duration <= 7 days) and 'large' is a month
    (i.e. duration roughly between 28 and 31 days), then we consider 'small' a subperiod
    of 'large' if the majority of the days in 'small' fall within 'large'.
    For a 7‑day week, that means at least 4 days.
    
    :param small: Tuple (start_dt, end_dt) for the small period.
    :param large: Tuple (start_dt, end_dt) for the large period.
    :return: True if 'small' is a subperiod of 'large' under the above rules, else False.
    """
    # Compute duration of small and large in days.
    small_duration = (small[1] - small[0]).days + 1
    large_duration = (large[1] - large[0]).days + 1

    # Compute the overlapping days between small and large.
    overlap_start = max(small[0], large[0])
    overlap_end = min(small[1], large[1])
    overlap_days = (overlap_end - overlap_start).days + 1 if overlap_end >= overlap_start else 0

    # If small is a week (7 days or less) and large is a typical month (28 to 31 days),
    # consider small a subperiod of large if the overlap is at least a majority of small.
    if small_duration <= 7 and 28 <= large_duration <= 31:
        # For a 7-day week, majority is at least 4 days.
        return overlap_days >= (small_duration // 2 + 1)
    
    # Otherwise, use the standard full-containment rule.
    return large[0] <= small[0] and small[1] <= large[1]


def build_spreads_for_screener(start_dates, end_dates, markets, delivery_types,
                                week_threshold=7,
                                month_threshold=31,
                                quarter_threshold=93,
                                same_allowed_offsets = [1, 2],
                                diff_allowed_offsets = [0, 1]):
    """
    1. Create market/deltyp pairs
    2. Convert separate start and end date lists into period tuples.
    3. Classify each period by its length into one of these buckets:
         'week'   : period length <= week_threshold days
         'month'  : period length <= month_threshold days
         'quarter': period length <= quarter_threshold days
         'year'   : otherwise
    4. For each bucket:
         - Sort the periods by start date (oldest to newest).
         - For each combination of left and right market/delivery pairs (from md_pairs),
           create an N x N "matrix" of period pairs (where N is the number of periods in the bucket).
         - Select only the cells (using allowed offsets) as follows:
             * If the MD pair is identical, keep offsets [1, 2].
             * If the MD pair is different, keep offsets [0, 1].
         - Each valid cell gives a tuple with the market, delivery, start, and end dates along with the contract type.
    5. Additionally, for the same market/delivery pairs, add cross‑bucket combinations where one period
       is a subperiod of another (e.g. a week contained in a month, a month contained in a quarter, etc.).
    6. Return one combined list of all valid spreads.
    
    Each final spread is a tuple:
      (
        (market_left, del_left, start_left, end_left, contract_type),
        (market_right, del_right, start_right, end_right, contract_type)
      )
    """
    md_pairs = [(m, d) for m in markets for d in delivery_types]

    # Filter out non liquid contracts that will not be traded
    contracts_out = [('cz', 'peak'), ('hu', 'peak'), ('sk', 'peak'),
                     ('at', 'peak'), ('es', 'peak')]
    
    md_pairs = [a for a in md_pairs if a not in contracts_out]

    if len(start_dates) != len(end_dates):
        raise ValueError("start_dates and end_dates must have the same length.")

    # 1. Convert dates to period tuples
    all_periods = []
    for s, e in zip(start_dates,
                    end_dates):
        s_dt = pd.to_datetime(s).normalize()
        e_dt = pd.to_datetime(e).normalize()
        all_periods.append((s_dt, e_dt))
    all_periods = list(pd.DataFrame(all_periods).drop_duplicates(keep='first').itertuples(index=False, name=None))
    
    # 2. Classify periods into buckets based on duration
    contract_buckets = {'week': [], 'month': [], 'quarter': [], 'year': []}
    for (s_dt, e_dt) in all_periods:
        delta_days = (e_dt - s_dt).days + 1
        if delta_days <= week_threshold:
            contract_buckets['week'].append((s_dt, e_dt))
        elif delta_days <= month_threshold:
            contract_buckets['month'].append((s_dt, e_dt))
        elif delta_days <= quarter_threshold:
            contract_buckets['quarter'].append((s_dt, e_dt))
        else:
            contract_buckets['year'].append((s_dt, e_dt))
    
    # 3. Build intra-bucket spreads using generic matrix approach.
    # Allowed offsets:
    #   - If MD pair is the same: [1, 2] (skip main diagonal, use second and third diagonals)
    #   - If MD pair is different: [0, 1] (include main diagonal and first diagonal)
    
    final_spreads = []
    
    # Intra-bucket spreads
    for contract_type, periods in contract_buckets.items():
        if not periods:
            continue
        # Sort periods by start date (oldest first)
        periods = sorted(periods, key=lambda p: p[0])
        N = len(periods)
        
        # For each combination of market/delivery pairs for left and right
        for md_left, md_right in itertools.product(md_pairs, repeat=2):
            allowed = same_allowed_offsets if md_left == md_right else diff_allowed_offsets
            valid_i, valid_j = get_valid_indices(N, allowed)
            for i, j in zip(valid_i, valid_j):
                final_spreads.append((
                    (md_left[0], md_left[1], periods[i][0], periods[i][1], contract_type),
                    (md_right[0], md_right[1], periods[j][0], periods[j][1], contract_type)
                ))
    
    # 4. Add cross-bucket spreads for subperiod relationships (only for same MD pairs)
    # Define the hierarchy (from smaller to larger period)
    hierarchy = ['week', 'month', 'quarter', 'year']
    # For each adjacent bucket pair in the hierarchy, add combinations if the small period is contained in the large period.
    for idx in range(len(hierarchy) - 1):
        small_bucket = hierarchy[idx]
        large_bucket = hierarchy[idx+1]
        periods_small = contract_buckets[small_bucket]
        periods_large = contract_buckets[large_bucket]
        if not periods_small or not periods_large:
            continue
        # Sort both lists by start date
        periods_small = sorted(periods_small, key=lambda p: p[0])
        periods_large = sorted(periods_large, key=lambda p: p[0])
        # For each same market/delivery pair
        for md in md_pairs:
            # Only add cross-bucket spreads if the md pair is the same.
            for p_small in periods_small:
                for p_large in periods_large:
                    if is_subperiod(p_small, p_large):
                        final_spreads.append((
                            (md[0], md[1], p_small[0], p_small[1], small_bucket),
                            (md[0], md[1], p_large[0], p_large[1], large_bucket)
                        ))
    
    # Optionally, sort final_spreads by left start date then right start date.
    final_spreads = sorted(final_spreads, key=lambda spread: (spread[0][2], spread[1][2]))
    
    return final_spreads

# ---------------------------
# Example usage
# ---------------------------
if __name__ == "__main__":
    # Example start and end dates
    start_dates = [
        '2025-03-31',
        '2025-05-01', 
        # '2025-07-01', 
        # '2025-04-01',  
        # '2025-07-01', 
        # '2025-03-31', 
        # '2026-01-01',
        # '2026-04-01'  
    ]
    end_dates = [
        '2025-04-06',
        '2025-05-31',
        # '2025-07-31',
        # '2025-06-30',
        # '2025-09-30',
        # '2025-04-06',
        # '2026-12-31',
        # '2026-06-30'
    ]
    
    # Example market/delivery pairs
    markets = ['de']
    delivery_types = ['base', 'peak']
    
    
    spreads = build_spreads_for_screener(start_dates, end_dates, markets, delivery_types)
    
    print("Total valid spreads:", len(spreads))
    for spread in spreads[:10]:
        print(spread)
