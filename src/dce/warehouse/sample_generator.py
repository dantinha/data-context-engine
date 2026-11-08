"""Deterministic synthetic Olist data generator conforming to RN-01 through RN-07."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# 20 standard Olist categories (Portuguese -> English)
CATEGORY_PAIRS: list[tuple[str, str]] = [
    ("beleza_saude", "health_beauty"),
    ("informatica_acessorios", "computers_accessories"),
    ("cama_mesa_banho", "bed_bath_table"),
    ("esporte_lazer", "sports_leisure"),
    ("moveis_decoracao", "furniture_decor"),
    ("utilidades_domesticas", "housewares"),
    ("relogios_presentes", "watches_gifts"),
    ("telefonia", "telephony"),
    ("automotivo", "auto"),
    ("brinquedos", "toys"),
    ("cool_stuff", "cool_stuff"),
    ("ferramentas_jardim", "garden_tools"),
    ("perfumaria", "perfumery"),
    ("bebes", "baby"),
    ("eletronicos", "electronics"),
    ("papelaria", "stationery"),
    ("moda_bolsas_e_acessorios", "fashion_bags_accessories"),
    ("pet_shop", "pet_shop"),
    ("livros_interesse_geral", "books_general_interest"),
    ("construcao_ferramentas_construcao", "construction_tools_construction"),
]

# Brazilian cities and states
LOCATION_POOL: list[tuple[str, str, int]] = [
    ("sao paulo", "SP", 1000),
    ("campinas", "SP", 13000),
    ("santos", "SP", 11000),
    ("rio de janeiro", "RJ", 20000),
    ("niteroi", "RJ", 24000),
    ("belo horizonte", "MG", 30000),
    ("uberlandia", "MG", 38400),
    ("curitiba", "PR", 80000),
    ("londrina", "PR", 86000),
    ("porto alegre", "RS", 90000),
    ("caxias do sul", "RS", 95000),
    ("florianopolis", "SC", 88000),
    ("joinville", "SC", 89200),
    ("salvador", "BA", 40000),
    ("brasilia", "DF", 70000),
    ("recife", "PE", 50000),
    ("fortaleza", "CE", 60000),
]


def generate_olist_sample(
    orders_count: int = 2000,
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """Generate deterministic synthetic Olist datasets satisfying rules RN-01 through RN-07.

    Args:
        orders_count: Total number of orders to generate.
        seed: Random seed for deterministic reproducibility.

    Returns:
        Dictionary mapping table keys and canonical names to pandas DataFrames.
    """
    rng = np.random.default_rng(seed)

    # 1. Product Category Translation Table
    df_translation = pd.DataFrame(
        CATEGORY_PAIRS, columns=["product_category_name", "product_category_name_english"]
    )

    # 2. Products (~15% of orders_count, capped between 40 and 400)
    num_products = min(400, max(40, orders_count // 5))
    product_rows = []
    for p in range(num_products):
        product_id = f"prod_{p:05d}"
        # RN-06: introduce null category for the first few products to exercise fallback
        if p < 4:
            cat_name = None
        else:
            cat_name = CATEGORY_PAIRS[p % len(CATEGORY_PAIRS)][0]

        product_rows.append({
            "product_id": product_id,
            "product_category_name": cat_name,
            "product_name_lenght": int(rng.integers(30, 65)),
            "product_description_lenght": int(rng.integers(150, 1800)),
            "product_photos_qty": int(rng.integers(1, 6)),
            "product_weight_g": float(rng.integers(150, 4500)),
            "product_length_cm": float(rng.integers(15, 70)),
            "product_height_cm": float(rng.integers(10, 45)),
            "product_width_cm": float(rng.integers(12, 55)),
        })
    df_products = pd.DataFrame(product_rows)

    # 3. Sellers (~5% of orders_count, capped between 15 and 100)
    num_sellers = min(100, max(15, orders_count // 15))
    seller_rows = []
    for s in range(num_sellers):
        seller_id = f"seller_{s:04d}"
        city, state, zip_prefix = LOCATION_POOL[s % len(LOCATION_POOL)]
        seller_rows.append({
            "seller_id": seller_id,
            "seller_zip_code_prefix": zip_prefix,
            "seller_city": city,
            "seller_state": state,
        })
    df_sellers = pd.DataFrame(seller_rows)

    # 4. Customers and Orders
    # RN-01: Each order has unique customer_id, but some customers make multiple orders
    num_unique_customers = max(1, int(orders_count * 0.75))
    customer_unique_ids = [f"cust_uniq_{c:05d}" for c in range(num_unique_customers)]

    # Assign base location for each unique customer
    customer_base_locations = {
        cid: LOCATION_POOL[c % len(LOCATION_POOL)]
        for c, cid in enumerate(customer_unique_ids)
    }

    # Map order index to customer_unique_id
    order_to_unique_customer: list[str] = []
    for i in range(orders_count):
        if i < num_unique_customers:
            order_to_unique_customer.append(customer_unique_ids[i])
        else:
            # Repeat customer (indices cycling through first 20% of customers)
            repeat_idx = i % max(1, int(num_unique_customers * 0.20))
            order_to_unique_customer.append(customer_unique_ids[repeat_idx])

    # RN-02: Guarantee presence of delivered, canceled, unavailable, shipped, invoiced
    order_statuses: list[str] = []
    for i in range(orders_count):
        if i == 0:
            order_statuses.append("delivered")
        elif i == 1:
            order_statuses.append("canceled")
        elif i == 2:
            order_statuses.append("unavailable")
        elif i == 3:
            order_statuses.append("shipped")
        elif i == 4:
            order_statuses.append("invoiced")
        else:
            # If repeat order (i >= num_unique_customers), make it delivered to ensure delivered_orders > 1
            if i >= num_unique_customers:
                order_statuses.append("delivered")
            else:
                r = rng.random()
                if r < 0.85:
                    order_statuses.append("delivered")
                elif r < 0.90:
                    order_statuses.append("shipped")
                elif r < 0.94:
                    order_statuses.append("canceled")
                elif r < 0.97:
                    order_statuses.append("unavailable")
                else:
                    order_statuses.append("invoiced")

    base_datetime = datetime(2023, 1, 1, 8, 0, 0)
    orders_rows = []
    customers_rows = []
    items_rows = []
    payments_rows = []
    reviews_rows = []

    review_counter = 0

    for i in range(orders_count):
        order_id = f"ord_{i:06d}"
        customer_id = f"cust_ord_{i:06d}"
        uniq_id = order_to_unique_customer[i]
        status = order_statuses[i]

        # Location: usually customer's base location, rarely moved
        base_city, base_state, base_zip = customer_base_locations[uniq_id]
        if i >= num_unique_customers and (i % 7 == 0):
            # Customer moved for this order
            new_loc = LOCATION_POOL[(i + 3) % len(LOCATION_POOL)]
            cust_city, cust_state, cust_zip = new_loc
        else:
            cust_city, cust_state, cust_zip = base_city, base_state, base_zip

        customers_rows.append({
            "customer_id": customer_id,
            "customer_unique_id": uniq_id,
            "customer_zip_code_prefix": cust_zip,
            "customer_city": cust_city,
            "customer_state": cust_state,
        })

        # Timestamps
        time_offset_hours = int(i * (350 * 24 / max(1, orders_count))) + int(rng.integers(0, 12))
        order_purchase = base_datetime + timedelta(
            hours=time_offset_hours, minutes=int(rng.integers(0, 60))
        )
        estimated_delivery = order_purchase + timedelta(days=int(rng.integers(12, 28)))

        order_approved_at = None
        carrier_date = None
        delivered_date = None

        # RN-05: Delivery delays
        # We ensure orders where (i % 7 == 0) and status == 'delivered' are delayed
        is_delayed_order = (status == "delivered" and (i % 7 == 0))

        if status == "delivered":
            order_approved_at = order_purchase + timedelta(minutes=int(rng.integers(15, 720)))
            carrier_date = order_approved_at + timedelta(days=int(rng.integers(1, 3)))
            if is_delayed_order:
                # Delivered AFTER estimated date (1 to 9 days late)
                delivered_date = estimated_delivery + timedelta(
                    days=int(rng.integers(1, 9)),
                    hours=int(rng.integers(1, 12)),
                )
            else:
                # Delivered BEFORE estimated date
                max_days = max(1, (estimated_delivery - carrier_date).days - 1)
                delivered_date = carrier_date + timedelta(
                    days=int(rng.integers(1, min(max_days + 1, 6)))
                )
                if delivered_date > estimated_delivery:
                    delivered_date = estimated_delivery - timedelta(days=1)
        elif status == "shipped":
            order_approved_at = order_purchase + timedelta(minutes=int(rng.integers(15, 720)))
            carrier_date = order_approved_at + timedelta(days=int(rng.integers(1, 3)))
        elif status == "invoiced":
            order_approved_at = order_purchase + timedelta(minutes=int(rng.integers(15, 720)))
        elif status == "canceled" and rng.random() > 0.5:
            order_approved_at = order_purchase + timedelta(minutes=int(rng.integers(15, 180)))

        orders_rows.append({
            "order_id": order_id,
            "customer_id": customer_id,
            "order_status": status,
            "order_purchase_timestamp": order_purchase.strftime("%Y-%m-%d %H:%M:%S"),
            "order_approved_at": (
                order_approved_at.strftime("%Y-%m-%d %H:%M:%S") if order_approved_at else None
            ),
            "order_delivered_carrier_date": (
                carrier_date.strftime("%Y-%m-%d %H:%M:%S") if carrier_date else None
            ),
            "order_delivered_customer_date": (
                delivered_date.strftime("%Y-%m-%d %H:%M:%S") if delivered_date else None
            ),
            "order_estimated_delivery_date": estimated_delivery.strftime("%Y-%m-%d %H:%M:%S"),
        })

        # RN-03: Order Items (1 to 4 items)
        item_prob = rng.random()
        if item_prob < 0.75:
            num_items = 1
        elif item_prob < 0.92:
            num_items = 2
        elif item_prob < 0.98:
            num_items = 3
        else:
            num_items = 4

        order_items_total = 0.0
        for item_idx in range(1, num_items + 1):
            product_idx = int(rng.integers(0, num_products))
            seller_idx = int(rng.integers(0, num_sellers))
            price = round(float(rng.uniform(19.90, 480.0)), 2)
            freight = round(float(rng.uniform(9.90, 45.0)), 2)
            order_items_total += price + freight

            items_rows.append({
                "order_id": order_id,
                "order_item_id": item_idx,
                "product_id": f"prod_{product_idx:05d}",
                "seller_id": f"seller_{seller_idx:04d}",
                "shipping_limit_date": (order_purchase + timedelta(days=5)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "price": price,
                "freight_value": freight,
            })

        # RN-03 & RN-04: Order Payments (1 to 3 payments)
        total_payment_to_distribute = round(order_items_total, 2)
        pay_prob = rng.random()
        if pay_prob < 0.85:
            num_payments = 1
        elif pay_prob < 0.96:
            num_payments = 2
        else:
            num_payments = 3

        if num_payments == 1:
            p_type_val = rng.random()
            if p_type_val < 0.74:
                ptype = "credit_card"
                installments = int(rng.integers(1, 11))
            elif p_type_val < 0.88:
                ptype = "boleto"
                installments = 1
            elif p_type_val < 0.94:
                ptype = "voucher"
                installments = 1
            else:
                ptype = "debit_card"
                installments = 1

            payments_rows.append({
                "order_id": order_id,
                "payment_sequential": 1,
                "payment_type": ptype,
                "payment_installments": installments,
                "payment_value": total_payment_to_distribute,
            })
        elif num_payments == 2:
            # 1 voucher + 1 credit card
            voucher_val = round(min(25.0, total_payment_to_distribute * 0.4), 2)
            remainder = round(total_payment_to_distribute - voucher_val, 2)
            payments_rows.append({
                "order_id": order_id,
                "payment_sequential": 1,
                "payment_type": "voucher",
                "payment_installments": 1,
                "payment_value": voucher_val,
            })
            payments_rows.append({
                "order_id": order_id,
                "payment_sequential": 2,
                "payment_type": "credit_card",
                "payment_installments": int(rng.integers(1, 8)),
                "payment_value": remainder,
            })
        else:
            # 2 vouchers + 1 credit card
            v1 = round(min(15.0, total_payment_to_distribute * 0.2), 2)
            v2 = round(min(15.0, total_payment_to_distribute * 0.2), 2)
            remainder = round(total_payment_to_distribute - v1 - v2, 2)
            payments_rows.append({
                "order_id": order_id,
                "payment_sequential": 1,
                "payment_type": "voucher",
                "payment_installments": 1,
                "payment_value": v1,
            })
            payments_rows.append({
                "order_id": order_id,
                "payment_sequential": 2,
                "payment_type": "voucher",
                "payment_installments": 1,
                "payment_value": v2,
            })
            payments_rows.append({
                "order_id": order_id,
                "payment_sequential": 3,
                "payment_type": "credit_card",
                "payment_installments": int(rng.integers(1, 8)),
                "payment_value": remainder,
            })

        # Order Reviews (~92% of orders have reviews, ~2% have two reviews)
        rev_prob = rng.random()
        if rev_prob < 0.08:
            num_reviews = 0
        elif rev_prob < 0.98:
            num_reviews = 1
        else:
            num_reviews = 2

        for _ in range(num_reviews):
            review_counter += 1
            review_id = f"rev_{review_counter:06d}"

            # Score depends on delivery performance
            if is_delayed_order:
                score = 1 if rng.random() < 0.65 else 2
            elif status in ("canceled", "unavailable"):
                score = 1 if rng.random() < 0.80 else 2
            else:
                score_r = rng.random()
                if score_r < 0.05:
                    score = 1
                elif score_r < 0.10:
                    score = 2
                elif score_r < 0.20:
                    score = 3
                elif score_r < 0.45:
                    score = 4
                else:
                    score = 5

            ref_date = delivered_date if delivered_date else order_purchase
            creation_date = ref_date + timedelta(days=1)
            answer_date = creation_date + timedelta(hours=int(rng.integers(6, 48)))

            reviews_rows.append({
                "review_id": review_id,
                "order_id": order_id,
                "review_score": score,
                "review_comment_title": "Bom" if score >= 4 else ("Ruim" if score <= 2 else None),
                "review_comment_message": (
                    "Produto excelente e entrega rápida."
                    if score >= 4
                    else "Atrasou a entrega."
                ),
                "review_creation_date": creation_date.strftime("%Y-%m-%d %H:%M:%S"),
                "review_answer_timestamp": answer_date.strftime("%Y-%m-%d %H:%M:%S"),
            })

    # Geolocation table from unique zip prefixes
    unique_zips = {c["customer_zip_code_prefix"] for c in customers_rows} | {
        s["seller_zip_code_prefix"] for s in seller_rows
    }
    geo_rows = []
    for loc_zip in unique_zips:
        match_loc = next((l for l in LOCATION_POOL if l[2] == loc_zip), LOCATION_POOL[0])
        geo_rows.append({
            "geolocation_zip_code_prefix": loc_zip,
            "geolocation_lat": -23.5505,
            "geolocation_lng": -46.6333,
            "geolocation_city": match_loc[0],
            "geolocation_state": match_loc[1],
        })
    df_geo = pd.DataFrame(geo_rows)

    df_orders = pd.DataFrame(orders_rows)
    df_customers = pd.DataFrame(customers_rows)
    df_order_items = pd.DataFrame(items_rows)
    df_order_payments = pd.DataFrame(payments_rows)
    df_order_reviews = pd.DataFrame(reviews_rows)

    result = {
        "orders": df_orders,
        "order_items": df_order_items,
        "order_payments": df_order_payments,
        "order_reviews": df_order_reviews,
        "customers": df_customers,
        "sellers": df_sellers,
        "products": df_products,
        "category_translation": df_translation,
        "geolocation": df_geo,
        # Canonical Olist names
        "olist_orders_dataset": df_orders,
        "olist_order_items_dataset": df_order_items,
        "olist_order_payments_dataset": df_order_payments,
        "olist_order_reviews_dataset": df_order_reviews,
        "olist_customers_dataset": df_customers,
        "olist_sellers_dataset": df_sellers,
        "olist_products_dataset": df_products,
        "product_category_name_translation": df_translation,
        "olist_geolocation_dataset": df_geo,
    }
    return result
