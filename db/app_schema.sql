-- Live store inventory and listings on TrueNAS MySQL 8.
-- Financial history stays in SQLite (db/schema.sql / ebay_store.db).

CREATE TABLE IF NOT EXISTS items (
    sku VARCHAR(64) NOT NULL PRIMARY KEY,
    title VARCHAR(512) NOT NULL,
    category VARCHAR(32) NOT NULL DEFAULT 'other',
    qty DECIMAL(10, 3) NOT NULL DEFAULT 1,
    cost DECIMAL(10, 2) NULL,
    ask_price DECIMAL(10, 2) NULL,
    location VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'on-hand',
    notes TEXT NULL,
    description TEXT NULL,
    condition_id VARCHAR(16) NULL,
    ebay_category_id VARCHAR(32) NULL,
    ebay_category_name VARCHAR(128) NULL,
    brand VARCHAR(128) NULL,
    item_specifics TEXT NULL,
    cogs_item_id VARCHAR(64) NULL,
    cogs_build_id VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_items_category (category),
    INDEX idx_items_status (status)
);

CREATE TABLE IF NOT EXISTS item_photos (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    source_url VARCHAR(1024) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_item_photos_sku (sku)
);

CREATE TABLE IF NOT EXISTS listings (
    ebay_item_id VARCHAR(32) NOT NULL PRIMARY KEY,
    sku VARCHAR(64) NULL,
    title VARCHAR(512) NOT NULL,
    price DECIMAL(10, 2) NULL,
    qty INT NOT NULL DEFAULT 0,
    stream VARCHAR(32) NOT NULL DEFAULT 'other',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    url VARCHAR(256) NULL,
    image_url VARCHAR(1024) NULL,
    ebay_category VARCHAR(128) NULL,
    watchers INT NULL,
    start_date DATE NULL,
    end_date DATE NULL,
    cogs_item_id VARCHAR(64) NULL,
    cogs_build_id VARCHAR(64) NULL,
    synced_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_listings_sku (sku),
    INDEX idx_listings_stream (stream),
    INDEX idx_listings_status (status)
);

CREATE TABLE IF NOT EXISTS app_meta (
    name VARCHAR(64) NOT NULL PRIMARY KEY,
    value VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    sku VARCHAR(64) NULL,
    ebay_item_id VARCHAR(32) NULL,
    sold_on DATE NULL,
    qty INT NOT NULL DEFAULT 1,
    sold_for DECIMAL(10, 2) NULL,
    cogs_item_id VARCHAR(64) NULL,
    cogs_build_id VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_order_line (order_id, ebay_item_id, sku),
    INDEX idx_orders_sold_on (sold_on)
);
