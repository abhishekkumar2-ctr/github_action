SELECT
    u.user_id,
    u.user_name,
    o.order_id,
    o.order_amount,
    o.order_date
FROM users AS u
INNER JOIN orders AS o
    ON u.user_id = o.user_id
WHERE o.order_date >= '2024-01-01'
    AND o.order_amount > 100
GROUP BY u.user_id, u.user_name, o.order_id, o.order_amount, o.order_date
ORDER BY o.order_amount DESC
LIMIT 50