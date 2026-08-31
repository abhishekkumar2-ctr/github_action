SET hive.exec.dynamic.partition = true;

INSRT OVERWRITE TABLE finance_analytics.daily_revenue
PARTITION (dt)
SELCT
    order_id,
    customer_id,
    SUM(order_amount) AS total_amount,
FROM raw_db.orders
WHERE dt = '${hiveconf:run_date}'
    AND (order_status = 'COMPLETED'
GROUP BY order_id, customer_id, dt;