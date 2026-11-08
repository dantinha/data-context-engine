"""DuckDB warehouse builder for DCE (raw -> staging -> marts)."""

from pathlib import Path

import duckdb

from dce.warehouse.sample_generator import generate_olist_sample


def build_warehouse(
    db_path: Path | str = Path("data/warehouse.duckdb"),
    sample_orders_count: int = 2000,
    seed: int = 42,
) -> Path:
    """Build local DuckDB warehouse with raw, staging, and marts layers.

    Args:
        db_path: Filesystem path to the .duckdb database file.
        sample_orders_count: Number of sample orders to generate.
        seed: Random seed for deterministic generation.

    Returns:
        Path to the populated database file.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing db file if any to ensure clean rebuild
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass

    datasets = generate_olist_sample(orders_count=sample_orders_count, seed=seed)

    con = duckdb.connect(str(path))

    # 1. Create schemas
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    con.execute("CREATE SCHEMA IF NOT EXISTS marts;")

    # 2. Populate raw schema tables
    raw_tables = {
        "raw.olist_orders_dataset": datasets["orders"],
        "raw.olist_order_items_dataset": datasets["order_items"],
        "raw.olist_order_payments_dataset": datasets["order_payments"],
        "raw.olist_order_reviews_dataset": datasets["order_reviews"],
        "raw.olist_customers_dataset": datasets["customers"],
        "raw.olist_sellers_dataset": datasets["sellers"],
        "raw.olist_products_dataset": datasets["products"],
        "raw.product_category_name_translation": datasets["category_translation"],
        "raw.olist_geolocation_dataset": datasets["geolocation"],
    }

    for table_name, df in raw_tables.items():
        con.register("_temp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_df;")
        con.unregister("_temp_df")

    # 3. Create staging views / tables
    con.execute("""
    CREATE OR REPLACE VIEW staging.stg_orders AS
    SELECT
        o.order_id,
        o.customer_id,
        c.customer_unique_id,
        o.order_status,
        CAST(o.order_purchase_timestamp AS TIMESTAMP) AS order_purchase_timestamp,
        CAST(o.order_purchase_timestamp AS DATE) AS order_purchase_date,
        CAST(o.order_approved_at AS TIMESTAMP) AS order_approved_at,
        CAST(o.order_delivered_carrier_date AS TIMESTAMP) AS order_delivered_carrier_date,
        CAST(o.order_delivered_customer_date AS TIMESTAMP) AS order_delivered_customer_date,
        CAST(o.order_estimated_delivery_date AS TIMESTAMP) AS order_estimated_delivery_date,
        (o.order_status = 'delivered') AS is_delivered,
        (o.order_status = 'canceled') AS is_canceled
    FROM raw.olist_orders_dataset o
    LEFT JOIN raw.olist_customers_dataset c ON o.customer_id = c.customer_id;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW staging.stg_order_items AS
    SELECT
        order_id,
        CAST(order_item_id AS INTEGER) AS order_item_id,
        product_id,
        seller_id,
        CAST(shipping_limit_date AS TIMESTAMP) AS shipping_limit_date,
        CAST(price AS DECIMAL(10, 2)) AS price,
        CAST(freight_value AS DECIMAL(10, 2)) AS freight_value,
        CAST(price + freight_value AS DECIMAL(10, 2)) AS total_item_value
    FROM raw.olist_order_items_dataset;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW staging.stg_order_payments AS
    SELECT
        order_id,
        CAST(payment_sequential AS INTEGER) AS payment_sequential,
        payment_type,
        CAST(payment_installments AS INTEGER) AS payment_installments,
        CAST(payment_value AS DECIMAL(10, 2)) AS payment_value
    FROM raw.olist_order_payments_dataset;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW staging.stg_order_reviews AS
    SELECT
        review_id,
        order_id,
        CAST(review_score AS INTEGER) AS review_score,
        review_comment_title,
        review_comment_message,
        CAST(review_creation_date AS TIMESTAMP) AS review_creation_date,
        CAST(review_answer_timestamp AS TIMESTAMP) AS review_answer_timestamp
    FROM raw.olist_order_reviews_dataset;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW staging.stg_customers AS
    SELECT
        customer_id,
        customer_unique_id,
        CAST(customer_zip_code_prefix AS INTEGER) AS customer_zip_code_prefix,
        customer_city,
        customer_state
    FROM raw.olist_customers_dataset;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW staging.stg_sellers AS
    SELECT
        seller_id,
        CAST(seller_zip_code_prefix AS INTEGER) AS seller_zip_code_prefix,
        seller_city,
        seller_state
    FROM raw.olist_sellers_dataset;
    """)

    con.execute("""
    CREATE OR REPLACE VIEW staging.stg_products AS
    SELECT
        p.product_id,
        COALESCE(p.product_category_name, 'nao_informado') AS category_name_pt,
        COALESCE(t.product_category_name_english, 'not_informed') AS category_name_en,
        CAST(p.product_weight_g AS DOUBLE) AS product_weight_g,
        CAST(p.product_length_cm AS DOUBLE) AS product_length_cm,
        CAST(p.product_height_cm AS DOUBLE) AS product_height_cm,
        CAST(p.product_width_cm AS DOUBLE) AS product_width_cm
    FROM raw.olist_products_dataset p
    LEFT JOIN raw.product_category_name_translation t
        ON p.product_category_name = t.product_category_name;
    """)

    # 4. Create marts tables
    # 4.1 marts.fct_orders (1 row per order_id, PK order_id)
    con.execute("""
    CREATE OR REPLACE TABLE marts.fct_orders AS
    WITH agg_items AS (
        SELECT
            order_id,
            COUNT(order_item_id) AS items_count,
            SUM(price) AS total_items_price,
            SUM(freight_value) AS total_freight_value,
            SUM(price + freight_value) AS total_order_value
        FROM staging.stg_order_items
        GROUP BY order_id
    ),
    agg_payments AS (
        SELECT
            order_id,
            SUM(payment_value) AS total_payment_value,
            MAX(payment_installments) AS payment_installments_max,
            ARG_MAX(payment_type, payment_value) AS primary_payment_type
        FROM staging.stg_order_payments
        GROUP BY order_id
    ),
    agg_reviews AS (
        SELECT
            order_id,
            AVG(review_score) AS avg_review_score
        FROM staging.stg_order_reviews
        GROUP BY order_id
    )
    SELECT
        o.order_id,
        o.customer_id,
        o.customer_unique_id,
        o.order_status,
        o.order_purchase_timestamp,
        o.order_purchase_date,
        o.order_approved_at,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,
        COALESCE(i.items_count, 0) AS items_count,
        CAST(COALESCE(i.total_items_price, 0.0) AS DECIMAL(10, 2)) AS total_items_price,
        CAST(COALESCE(i.total_freight_value, 0.0) AS DECIMAL(10, 2)) AS total_freight_value,
        CAST(COALESCE(i.total_order_value, 0.0) AS DECIMAL(10, 2)) AS total_order_value,
        CAST(COALESCE(p.total_payment_value, 0.0) AS DECIMAL(10, 2)) AS total_payment_value,
        COALESCE(p.payment_installments_max, 1) AS payment_installments_max,
        p.primary_payment_type,
        CAST(r.avg_review_score AS DOUBLE) AS review_score,
        o.is_delivered,
        o.is_canceled,
        (o.order_status = 'delivered' AND CAST(o.order_delivered_customer_date AS DATE) > CAST(o.order_estimated_delivery_date AS DATE)) AS is_delayed,
        CASE
            WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
            THEN DATE_DIFF('day', CAST(o.order_purchase_timestamp AS DATE), CAST(o.order_delivered_customer_date AS DATE))
            ELSE NULL
        END AS delivery_days,
        CASE
            WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
            THEN CASE
                WHEN CAST(o.order_delivered_customer_date AS DATE) > CAST(o.order_estimated_delivery_date AS DATE)
                THEN DATE_DIFF('day', CAST(o.order_estimated_delivery_date AS DATE), CAST(o.order_delivered_customer_date AS DATE))
                ELSE 0
            END
            ELSE NULL
        END AS delay_days
    FROM staging.stg_orders o
    LEFT JOIN agg_items i ON o.order_id = i.order_id
    LEFT JOIN agg_payments p ON o.order_id = p.order_id
    LEFT JOIN agg_reviews r ON o.order_id = r.order_id;
    """)

    # 4.2 marts.fct_order_items (1 row per order_id + order_item_id)
    con.execute("""
    CREATE OR REPLACE TABLE marts.fct_order_items AS
    WITH agg_reviews AS (
        SELECT order_id, AVG(review_score) AS avg_review_score
        FROM staging.stg_order_reviews
        GROUP BY order_id
    )
    SELECT
        oi.order_id,
        oi.order_item_id,
        oi.product_id,
        oi.seller_id,
        o.customer_unique_id,
        o.order_status,
        o.is_delivered,
        o.order_purchase_timestamp,
        o.order_purchase_date,
        oi.price,
        oi.freight_value,
        oi.total_item_value,
        CAST(r.avg_review_score AS DOUBLE) AS review_score
    FROM staging.stg_order_items oi
    JOIN staging.stg_orders o ON oi.order_id = o.order_id
    LEFT JOIN agg_reviews r ON oi.order_id = r.order_id;
    """)

    # 4.3 marts.fct_order_payments (1 row per order_id + payment_sequential)
    con.execute("""
    CREATE OR REPLACE TABLE marts.fct_order_payments AS
    SELECT
        p.order_id,
        p.payment_sequential,
        o.order_status,
        o.order_purchase_date,
        p.payment_type,
        p.payment_installments,
        p.payment_value
    FROM staging.stg_order_payments p
    JOIN staging.stg_orders o ON p.order_id = o.order_id;
    """)

    # 4.4 marts.dim_customers (1 row per customer_unique_id, PK customer_unique_id)
    con.execute("""
    CREATE OR REPLACE TABLE marts.dim_customers AS
    SELECT
        fo.customer_unique_id,
        ARG_MAX(sc.customer_city, fo.order_purchase_timestamp) AS customer_city,
        ARG_MAX(sc.customer_state, fo.order_purchase_timestamp) AS customer_state,
        MIN(fo.order_purchase_date) AS first_order_date,
        MAX(fo.order_purchase_date) AS last_order_date,
        COUNT(DISTINCT fo.order_id) AS total_orders,
        COUNT(DISTINCT CASE WHEN fo.order_status = 'delivered' THEN fo.order_id END) AS delivered_orders,
        CAST(COALESCE(SUM(CASE WHEN fo.order_status = 'delivered' THEN fo.total_payment_value ELSE 0.0 END), 0.0) AS DECIMAL(12, 2)) AS lifetime_value,
        CAST(
            CASE
                WHEN COUNT(DISTINCT CASE WHEN fo.order_status = 'delivered' THEN fo.order_id END) > 0
                THEN ROUND(COALESCE(SUM(CASE WHEN fo.order_status = 'delivered' THEN fo.total_payment_value ELSE 0.0 END), 0.0) / COUNT(DISTINCT CASE WHEN fo.order_status = 'delivered' THEN fo.order_id END), 2)
                ELSE 0.0
            END
            AS DECIMAL(12, 2)
        ) AS avg_ticket,
        (COUNT(DISTINCT CASE WHEN fo.order_status = 'delivered' THEN fo.order_id END) > 1) AS is_repeat_customer
    FROM marts.fct_orders fo
    JOIN staging.stg_customers sc ON fo.customer_id = sc.customer_id
    GROUP BY fo.customer_unique_id;
    """)

    # 4.5 marts.dim_products (1 row per product_id, PK product_id)
    con.execute("""
    CREATE OR REPLACE TABLE marts.dim_products AS
    SELECT
        product_id,
        category_name_pt,
        category_name_en,
        product_weight_g,
        product_length_cm,
        product_height_cm,
        product_width_cm
    FROM staging.stg_products;
    """)

    # 4.6 marts.dim_sellers (1 row per seller_id, PK seller_id)
    con.execute("""
    CREATE OR REPLACE TABLE marts.dim_sellers AS
    SELECT
        s.seller_id,
        s.seller_city,
        s.seller_state,
        COUNT(DISTINCT CASE WHEN oi.order_status = 'delivered' THEN oi.order_id END) AS total_orders_sold,
        COUNT(CASE WHEN oi.order_status = 'delivered' THEN oi.order_item_id END) AS total_items_sold,
        CAST(COALESCE(SUM(CASE WHEN oi.order_status = 'delivered' THEN oi.price ELSE 0.0 END), 0.0) AS DECIMAL(12, 2)) AS total_revenue_generated,
        CAST(ROUND(AVG(oi.review_score), 2) AS DOUBLE) AS avg_review_score
    FROM staging.stg_sellers s
    LEFT JOIN marts.fct_order_items oi ON s.seller_id = oi.seller_id
    GROUP BY s.seller_id, s.seller_city, s.seller_state;
    """)

    con.close()
    return path
