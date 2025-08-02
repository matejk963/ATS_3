SELECT max(datetime) from public.trades t;


--drop table public.dataset_entries;
-- 1. Create the regular PostgreSQL table:
CREATE TABLE public.dataset_entries (
    datetime TIMESTAMP NOT NULL,
    nanotime FLOAT NOT NULL,
    tradeid VARCHAR(100) NOT NULL,        
    pred_name VARCHAR(256) NOT NULL,
    pred_id VARCHAR(100) NOT NULL REFERENCES public.predictors(pred_id),
    pred_value NUMERIC,   
    additional VARCHAR(256),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (datetime, nanotime, tradeid, pred_id, pred_value)  -- includes datetime
);

-- Convert to TimescaleDB hypertable:
SELECT create_hypertable('public.dataset_entries', 'datetime', if_not_exists => TRUE);

-- Additional indexes:
CREATE INDEX IF NOT EXISTS idx_dataset_entries_tradeid ON public.dataset_entries(tradeid);
CREATE INDEX IF NOT EXISTS idx_dataset_entries_pred_id ON public.dataset_entries(pred_id);


CREATE TABLE public.predictors (
    pred_id VARCHAR(100) PRIMARY KEY,   -- Predictor ID (string), adjust size as needed
    pred_name VARCHAR(255) NOT NULL,    -- Predictor name
    description TEXT,                   -- Optional detailed description
    location TEXT,                   -- Optional detailed description
    additional TEXT,                   -- Optional detailed description
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);



select * from public.trades limit 1000;

select * from public.trades where tradeid='5473476';


select * from public.predictors;

insert into public.predictors;



INSERT INTO public.predictors (pred_id, pred_name, description, location)
VALUES 
    ('ll_dem2_dem1_MACD_6_14', 'MACD_6_14_dem2', 'MACD_6_14 of dem2 using raw EEX trades, forward filling used on non-dem2 trades', 'EnergyTrading/Python/Strategies/LeadLagXGB/LLXGB_dem2_Predictor_calculations_for_datamart.ipynb'),
    ('ll_dem2_dem1_MACD_12_26', 'MACD_12_26_dem2', 'MACD_12_26 of dem2 using raw EEX trades, forward filling used on non-dem2 trades', 'EnergyTrading/Python/Strategies/LeadLagXGB/LLXGB_dem2_Predictor_calculations_for_datamart.ipynb'),
    ('ll_dem2_dem1_MACD_18_38', 'MACD_18_38_dem2', 'MACD_18_38 of dem2 using raw EEX trades, forward filling used on non-dem2 trades', 'EnergyTrading/Python/Strategies/LeadLagXGB/LLXGB_dem2_Predictor_calculations_for_datamart.ipynb'),
    ('ll_dem2_dem1_MACD_30_60', 'MACD_30_60_dem2', 'MACD_30_60 of dem2 using raw EEX trades, forward filling used on non-dem2 trades', 'EnergyTrading/Python/Strategies/LeadLagXGB/LLXGB_dem2_Predictor_calculations_for_datamart.ipynb'),
    ('ll_dem2_dem1_fair_price', 'fair_price_dem2', 'Fair price for dem2 based on dem1 as lead, exactly as calculated in leadlag-dem1-dem2 v6 production strategy; By design, values are only calculated on dem1 EEX trades, elsewhere forward filling used', 'EnergyTrading/Python/Strategies/LeadLagXGB/LLXGB_dem2_Predictor_calculations_for_datamart.ipynb')
ON CONFLICT (pred_id) DO NOTHING;



