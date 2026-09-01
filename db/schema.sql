PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL CHECK (source IN ('csv', 'api')),
    file_path TEXT,
    api_endpoint TEXT,
    data_type TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    rows_inserted INTEGER DEFAULT 0,
    rows_updated INTEGER DEFAULT 0,
    rows_skipped INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_run_id INTEGER NOT NULL REFERENCES import_runs(id),
    transaction_date TEXT,
    type TEXT NOT NULL,
    order_number TEXT NOT NULL DEFAULT '--',
    legacy_order_id TEXT,
    buyer_username TEXT,
    buyer_name TEXT,
    ship_to_city TEXT,
    ship_to_state TEXT,
    ship_to_zip TEXT,
    ship_to_country TEXT,
    net_amount REAL,
    payout_currency TEXT,
    payout_date TEXT,
    payout_id TEXT,
    payout_method TEXT,
    payout_status TEXT,
    reason_for_hold TEXT,
    item_id TEXT,
    transaction_id TEXT NOT NULL DEFAULT '',
    item_title TEXT,
    custom_label TEXT,
    quantity REAL,
    item_subtotal REAL,
    shipping_and_handling REAL,
    seller_collected_tax REAL,
    ebay_collected_tax REAL,
    final_value_fee_fixed REAL,
    final_value_fee_variable REAL,
    regulatory_operating_fee REAL,
    inad_fee REAL,
    below_standard_fee REAL,
    international_fee REAL,
    charity_donation REAL,
    deposit_processing_fee REAL,
    promoted_listing_fee REAL,
    gross_transaction_amount REAL,
    transaction_currency TEXT,
    exchange_rate TEXT,
    reference_id TEXT,
    description TEXT,
    raw_json TEXT,
    dedup_key TEXT NOT NULL,
    UNIQUE (dedup_key)
);

CREATE TABLE IF NOT EXISTS order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_run_id INTEGER NOT NULL REFERENCES import_runs(id),
    sales_record_number TEXT,
    order_number TEXT NOT NULL,
    buyer_username TEXT,
    buyer_name TEXT,
    item_number TEXT NOT NULL DEFAULT '',
    item_title TEXT,
    custom_label TEXT,
    sold_via_promoted_listings TEXT,
    quantity REAL,
    sold_for REAL,
    shipping_and_handling REAL,
    total_price REAL,
    sale_date TEXT,
    sale_date_parsed TEXT,
    transaction_id TEXT NOT NULL DEFAULT '',
    raw_json TEXT,
    UNIQUE (order_number, item_number, transaction_id)
);

CREATE TABLE IF NOT EXISTS order_earnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_run_id INTEGER NOT NULL REFERENCES import_runs(id),
    order_creation_date TEXT,
    order_number TEXT NOT NULL,
    item_id TEXT NOT NULL DEFAULT '',
    item_title TEXT,
    buyer_name TEXT,
    ship_to_city TEXT,
    ship_to_state TEXT,
    ship_to_zip TEXT,
    ship_to_country TEXT,
    transaction_currency TEXT,
    ebay_collected_tax REAL,
    item_price REAL,
    quantity REAL,
    item_subtotal REAL,
    shipping_and_handling REAL,
    seller_collected_tax REAL,
    discount REAL,
    payout_currency TEXT,
    gross_amount REAL,
    final_value_fee_fixed REAL,
    final_value_fee_variable REAL,
    below_standard_fee REAL,
    inad_fee REAL,
    international_fee REAL,
    deposit_processing_fee REAL,
    regulatory_operating_fee REAL,
    promoted_listing_fee REAL,
    charity_donation REAL,
    shipping_labels REAL,
    payment_dispute_fee REAL,
    expenses REAL,
    refunds REAL,
    order_earnings REAL,
    your_cost REAL,
    net_order_earnings REAL,
    raw_json TEXT,
    UNIQUE (order_number, item_id)
);

CREATE TABLE IF NOT EXISTS tax_invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_run_id INTEGER NOT NULL REFERENCES import_runs(id),
    invoice_month TEXT NOT NULL,
    line_date TEXT,
    description TEXT,
    memo TEXT,
    order_number TEXT NOT NULL DEFAULT '',
    item_number TEXT NOT NULL DEFAULT '',
    fee_group TEXT,
    fee_type TEXT NOT NULL DEFAULT '',
    currency TEXT,
    net_amount REAL,
    tax_pct TEXT,
    tax_amount REAL,
    total_amount REAL,
    charged_by_entity TEXT,
    raw_json TEXT,
    UNIQUE (invoice_month, line_date, order_number, item_number, fee_type, memo)
);

CREATE TABLE IF NOT EXISTS promoted_listing_fees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_run_id INTEGER NOT NULL REFERENCES import_runs(id),
    report_start TEXT NOT NULL,
    report_end TEXT NOT NULL,
    campaign_name TEXT,
    campaign_id TEXT,
    listing_id TEXT NOT NULL,
    title TEXT,
    listing_format TEXT,
    price REAL,
    quantity_available REAL,
    promoted_impressions REAL,
    promoted_clicks REAL,
    promoted_sold_qty REAL,
    organic_sold_qty REAL,
    total_sold_qty REAL,
    promoted_sales REAL,
    ad_fees REAL,
    return_on_ad_spend REAL,
    raw_json TEXT,
    UNIQUE (listing_id, report_start, report_end, campaign_id)
);

CREATE TABLE IF NOT EXISTS sync_state (
    data_type TEXT PRIMARY KEY,
    last_sync_at TEXT,
    last_sync_cursor TEXT
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_custom_label ON transactions(custom_label);
CREATE INDEX IF NOT EXISTS idx_transactions_order ON transactions(order_number);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);

CREATE INDEX IF NOT EXISTS idx_order_lines_sale_date ON order_lines(sale_date_parsed);
CREATE INDEX IF NOT EXISTS idx_order_lines_custom_label ON order_lines(custom_label);
CREATE INDEX IF NOT EXISTS idx_order_lines_order ON order_lines(order_number);

CREATE INDEX IF NOT EXISTS idx_order_earnings_date ON order_earnings(order_creation_date);
CREATE INDEX IF NOT EXISTS idx_order_earnings_order ON order_earnings(order_number);

CREATE INDEX IF NOT EXISTS idx_tax_invoice_month ON tax_invoice_lines(invoice_month);

CREATE INDEX IF NOT EXISTS idx_promoted_listing_dates ON promoted_listing_fees(report_start, report_end);
