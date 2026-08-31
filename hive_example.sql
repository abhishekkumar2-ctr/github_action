SET hive.exec.dynamic.partition = true;
SET hive.exec.dynamic.partition.mode = nonstrict;

INSERT OVERWRITE TABLE finance_analytics.daily_revenue
PARTITION (dt)
SELECT
    order_id,
    customer_id,
    product_name,
    SUM(order_amount) AS total_amount,
    COUNT(*) AS order_count,
    CASE
        WHEN SUM(order_amount) > 10000 THEN 'HIGH'
        WHEN SUM(order_amount) > 5000 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS revenue_category,
    from_unixtime(unix_timestamp(), 'yyyy-MM-dd HH:mm:ss') AS etl_timestamp,
    dt
FROM raw_db.orders
WHERE dt = '${hiveconf:run_date}'
    AND order_status = 'COMPLETED'
GROUP BY order_id, customer_id, product_name, dt
HAVING SUM(order_amount) > 0
ORDER BY total_amount DESC
LIMIT 1000;