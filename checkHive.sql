with SO_SI as (
Select sales_orders.So_number, sales_invoices.invoice_number, (sales_invoices.created_at + interval '330 min')::date invoice_date,
(sales_orders.created_at + interval '330 min')::date So_date,
Tenants.name Tenant, 
sales_invoices.total_net_amount SI_net_amount,
branches.name Branch

from sales_invoices  
left join sales_orders on sales_orders.id = sales_invoices.sales_order_id and sales_orders.deleted_at is null
left join hospitals on sales_orders.buyer_party_id = hospitals.id and hospitals.deleted_at is null
left join branches on sales_orders.branch_id = branches.id and branches.deleted_at is null
left join tenants on tenants.id = sales_invoices.tenant_id 

where sales_invoices.deleted_at is null
and ( ((sales_invoices.created_at + interval '330 min')::date > '2023-12-31')
or ((sales_orders.created_at + interval '330 min')::date > '2023-12-31')
)
and sales_orders.status not in('draft','cancelled')
and sales_invoices.status not in('draft','cancelled')

and hospitals.internal_entity is false
and (branches.name not ilike '%Test%' or branches.name not ilike '%DEFAULT%')

and Tenants.id not in (2,4,6)

order by 4 desc
),


PTR as (
select "Metric",
sum("D-1")"D-1",
sum("D-2")"D-2",
sum("D-8")"D-8",
sum("MTD-0")"MTD-0",
sum("MTD-1")"MTD-1",
sum("M-1")"M-1" ,
sum("W-1")"W-1",
sum("W-2")"W-2",1 as order_colmn
from(
select case when Tenant is not null then 'PTR Sales' end as "Metric","D-1",
"D-2",
"D-8",
"MTD-0",
"MTD-1","M-1", 
"W-1",
"W-2"
from(
select Tenant, 
SUM(CASE WHEN invoice_date = (current_date - INTERVAL '1 day') THEN SI_net_amount ELSE 0 END) AS "D-1",
SUM(CASE WHEN invoice_date = (current_date - INTERVAL '2 days') THEN SI_net_amount ELSE 0 END) AS "D-2",
SUM(CASE WHEN invoice_date = (current_date - INTERVAL '8 days') THEN SI_net_amount ELSE 0 END) AS "D-8",

SUM(
  CASE 
    WHEN EXTRACT(DAY FROM current_date) = 1 THEN
 
      CASE 
        WHEN invoice_date >= date_trunc('month', current_date) - INTERVAL '1 month' 
             AND invoice_date < date_trunc('month', current_date) 
        THEN SI_net_amount 
        ELSE 0 
      END
    ELSE
    
      CASE 
        WHEN invoice_date >= date_trunc('month', current_date) 
             AND invoice_date < current_date 
        THEN SI_net_amount 
        ELSE 0 
      END
  END
) AS "MTD-0",    

SUM(
  CASE 
    WHEN EXTRACT(DAY FROM current_date) = 1 THEN
      
      CASE 
        WHEN invoice_date >= date_trunc('month', current_date) - INTERVAL '2 months' 
             AND invoice_date < date_trunc('month', current_date) - INTERVAL '1 month'
        THEN SI_net_amount 
        ELSE 0 
      END
    ELSE
     
      CASE 
        WHEN invoice_date >= date_trunc('month', current_date) - INTERVAL '1 month' 
             AND invoice_date < date_trunc('month', current_date) - INTERVAL '1 month' + (current_date - date_trunc('month', current_date))
        THEN SI_net_amount 
        ELSE 0 
      END
  END
) AS "MTD-1",


SUM(CASE WHEN invoice_date >= date_trunc('month', current_date) - INTERVAL '1 month' AND invoice_date < date_trunc('month', current_date) THEN SI_net_amount ELSE 0 END) AS "M-1",
SUM(CASE WHEN invoice_date >= (current_date - INTERVAL '7 days') AND invoice_date <= (current_date - INTERVAL '1 days') THEN SI_net_amount ELSE 0 END) AS "W-1",
SUM(CASE WHEN invoice_date >= (current_date - INTERVAL '14 days') AND invoice_date <= (current_date - INTERVAL '8 days') THEN SI_net_amount ELSE 0 END) AS "W-2"


from SO_SI
group by 1
)SI
)SI2
group by 1
),

orders as (
select "Metric",
sum("D-1")"D-1",
sum("D-2")"D-2",
sum("D-8")"D-8",
sum("MTD-0")"MTD-0",
sum("MTD-1")"MTD-1",
sum("M-1")"M-1" ,
sum("W-1")"W-1",
sum("W-2")"W-2",2 as order_colmn
from(
select case when Tenant is not null then 'Orders' end as "Metric","D-1",
"D-2",
"D-8",
"MTD-0",
"MTD-1","M-1", "W-1",
"W-2"
from(
select Tenant,
count(distinct CASE WHEN So_date = (current_date - INTERVAL '1 day') THEN so_number ELSE null END) AS "D-1",
count(distinct CASE WHEN So_date = (current_date - INTERVAL '2 days') THEN so_number ELSE null END) AS "D-2",
count(distinct CASE WHEN So_date = (current_date - INTERVAL '8 days') THEN so_number ELSE null END) AS "D-8",

count( distinct
  CASE 
    WHEN EXTRACT(DAY FROM current_date) = 1 THEN
     
      CASE 
        WHEN So_date >= date_trunc('month', current_date) - INTERVAL '1 month' 
             AND So_date < date_trunc('month', current_date) 
        THEN so_number 
        ELSE null 
      END
    ELSE
      
      CASE 
        WHEN So_date >= date_trunc('month', current_date) 
             AND So_date < current_date 
        THEN so_number 
        ELSE null 
      END
  END
) AS "MTD-0",    

count( distinct
  CASE 
    WHEN EXTRACT(DAY FROM current_date) = 1 THEN
      
      CASE 
        WHEN So_date >= date_trunc('month', current_date) - INTERVAL '2 months' 
             AND So_date < date_trunc('month', current_date) - INTERVAL '1 month'
        THEN so_number 
        ELSE null 
      END
    ELSE
     
      CASE 
        WHEN So_date >= date_trunc('month', current_date) - INTERVAL '1 month' 
             AND So_date < date_trunc('month', current_date) - INTERVAL '1 month' + (current_date - date_trunc('month', current_date))
        THEN so_number 
        ELSE null 
      END
  END
) AS "MTD-1",


count(distinct CASE WHEN So_date >= date_trunc('month', current_date) - INTERVAL '1 month' AND So_date < date_trunc('month', current_date) THEN so_number ELSE null END) AS "M-1",
count(distinct CASE WHEN So_date >= (current_date - INTERVAL '7 days') AND So_date <= (current_date - INTERVAL '1 days') THEN so_number ELSE null END) AS "W-1",
count(distinct CASE WHEN So_date >= (current_date - INTERVAL '14 days') AND So_date <= (current_date - INTERVAL '8 days') THEN so_number ELSE null END) AS "W-2"
from SO_SI
group by 1
)SI
)SI2
group by 1
),


Ordered_AOV AS (
    SELECT
        'Ordered AOV' AS "Metric",
        (CASE WHEN o."D-1" = 0 THEN NULL ELSE p."D-1" / o."D-1" END) AS "D-1",
        (CASE WHEN o."D-2" = 0 THEN NULL ELSE p."D-2" / o."D-2" END) AS "D-2",
        (CASE WHEN o."D-8" = 0 THEN NULL ELSE p."D-8" / o."D-8" END) AS "D-8",
        (CASE WHEN o."MTD-0" = 0 THEN NULL ELSE p."MTD-0" / o."MTD-0" END) AS "MTD-0",
        (CASE WHEN o."MTD-1" = 0 THEN NULL ELSE p."MTD-1" / o."MTD-1" END) AS "MTD-1",
        (CASE WHEN o."M-1" = 0 THEN NULL ELSE p."M-1" / o."M-1" END) AS "M-1",
        (CASE WHEN o."W-1" = 0 THEN NULL ELSE p."W-1" / o."W-1" END) AS "W-1",
        (CASE WHEN o."W-2" = 0 THEN NULL ELSE p."W-2" / o."W-2" END) AS "W-2",
        
        3 as order_colmn
    FROM
        PTR p
    CROSS JOIN
        orders o
),


Return As (
select "Metric",
sum("D-1")"D-1",
sum("D-2")"D-2",
sum("D-8")"D-8",
sum("MTD-0")"MTD-0",
sum("MTD-1")"MTD-1",
sum("M-1")"M-1" ,
sum("W-1")"W-1",
sum("W-2")"W-2",
4 as order_colmn
from(
select case when Tenant is not null then 'Total Sales Return' end as "Metric","D-1",
"D-2",
"D-8",
"MTD-0",
"MTD-1", "M-1","W-1","W-2"
from(
select Tenant,
SUM(CASE WHEN Sr_date = (current_date - INTERVAL '1 day') THEN SR_net_amount ELSE 0 END) AS "D-1",
SUM(CASE WHEN Sr_date = (current_date - INTERVAL '2 days') THEN SR_net_amount ELSE 0 END) AS "D-2",
SUM(CASE WHEN Sr_date = (current_date - INTERVAL '8 days') THEN SR_net_amount ELSE 0 END) AS "D-8",


SUM(
  CASE 
    WHEN EXTRACT(DAY FROM current_date) = 1 THEN
      
      CASE 
        WHEN Sr_date >= date_trunc('month', current_date) - INTERVAL '1 month' 
             AND Sr_date < date_trunc('month', current_date) 
        THEN SR_net_amount 
        ELSE 0 
      END
    ELSE
      
      CASE 
        WHEN Sr_date >= date_trunc('month', current_date) 
             AND Sr_date < current_date 
        THEN SR_net_amount 
        ELSE 0 
      END
  END
) AS "MTD-0",    

SUM(
  CASE 
    WHEN EXTRACT(DAY FROM current_date) = 1 THEN
      
      CASE 
        WHEN Sr_date >= date_trunc('month', current_date) - INTERVAL '2 months' 
             AND Sr_date < date_trunc('month', current_date) - INTERVAL '1 month'
        THEN SR_net_amount 
        ELSE 0 
      END
    ELSE
     
      CASE 
        WHEN Sr_date >= date_trunc('month', current_date) - INTERVAL '1 month' 
             AND Sr_date < date_trunc('month', current_date) - INTERVAL '1 month' + (current_date - date_trunc('month', current_date))
        THEN SR_net_amount 
        ELSE 0 
      END
  END
) AS "MTD-1",


SUM(CASE WHEN Sr_date >= date_trunc('month', current_date) - INTERVAL '1 month' AND Sr_date < date_trunc('month', current_date) THEN SR_net_amount ELSE 0 END) AS "M-1",
SUM(CASE WHEN Sr_date >= (current_date - INTERVAL '7 days') AND Sr_date <= (current_date - INTERVAL '1 days') THEN SR_net_amount ELSE 0 END) AS "W-1",
SUM(CASE WHEN Sr_date >= (current_date - INTERVAL '14 days') AND Sr_date <= (current_date - INTERVAL '8 days') THEN SR_net_amount ELSE 0 END) AS "W-2"

from (
Select distinct sales_returns.return_number SR_number,
(sales_returns.created_at + interval '330 min')::date Sr_date,
Tenants.name Tenant, 
sales_returns.total_net_amount SR_net_amount,
branches.name Branch
from sales_returns 
left join branches on sales_returns.branch_id = branches.id and branches.deleted_at is null
left join tenants on tenants.id = sales_returns.tenant_id 

where sales_returns.deleted_at is null
and (sales_returns.created_at + interval '330 min')::date > '2023-12-31'
and sales_returns.status not in('draft','cancelled')
and (branches.name not ilike '%Test%' or branches.name not ilike '%DEFAULT%')
and Tenants.id not in (2,4,6)
order by 2 
)SR
group by 1
)SR2
)SR3 Group by 1
),

GMV as (
select "Metric",
sum("D-1")"D-1",
sum("D-2")"D-2",
sum("D-8")"D-8",
sum("MTD-0")"MTD-0",
sum("MTD-1")"MTD-1",
sum("M-1")"M-1",
sum("W-1")"W-1",
sum("W-2")"W-2",
5 as order_colmn
from(
select case when Tenant ilike '%akna%'  then 'Akna GMV' 
 when Tenant ilike '%impex%'  then 'Impex GMV'
 when Tenant ilike '%Shreeji%'  then 'Shreeji GMV'
when Tenant ilike '%Vardhman%' then 'Vardhman GMV'
end as "Metric","D-1",
"D-2",
"D-8",
"MTD-0",
"MTD-1","M-1","W-1","W-2"
from(

select Tenant,
SUM(CASE WHEN Invoice_date = (current_date - INTERVAL '1 day') THEN SI_net_amount ELSE 0 END) AS "D-1",
SUM(CASE WHEN Invoice_date = (current_date - INTERVAL '2 days') THEN SI_net_amount ELSE 0 END) AS "D-2",
SUM(CASE WHEN Invoice_date = (current_date - INTERVAL '8 days') THEN SI_net_amount ELSE 0 END) AS "D-8",

SUM(
  CASE 
    WHEN EXTRACT(DAY FROM current_date) = 1 THEN
      
      CASE 
        WHEN invoice_date >= date_trunc('month', current_date) - INTERVAL '1 month' 
             AND invoice_date < date_trunc('month', current_date) 
        THEN SI_net_amount 
        ELSE 0 
      END
    ELSE
     
      CASE 
        WHEN invoice_date >= date_trunc('month', current_date) 
             AND invoice_date < current_date 
        THEN SI_net_amount 
        ELSE 0 
      END
  END
) AS "MTD-0",    

SUM(
  CASE 
    WHEN EXTRACT(DAY FROM current_date) = 1 THEN
      
      CASE 
        WHEN invoice_date >= date_trunc('month', current_date) - INTERVAL '2 months' 
             AND invoice_date < date_trunc('month', current_date) - INTERVAL '1 month'
        THEN SI_net_amount 
        ELSE 0 
      END
    ELSE
      
      CASE 
        WHEN invoice_date >= date_trunc('month', current_date) - INTERVAL '1 month' 
             AND invoice_date < date_trunc('month', current_date) - INTERVAL '1 month' + (current_date - date_trunc('month', current_date))
        THEN SI_net_amount 
        ELSE 0 
      END
  END
) AS "MTD-1",


SUM(CASE WHEN Invoice_date >= date_trunc('month', current_date) - INTERVAL '1 month' AND Invoice_date < date_trunc('month', current_date) THEN SI_net_amount ELSE 0 END) AS "M-1",
SUM(CASE WHEN Invoice_date >= (current_date - INTERVAL '7 days') AND Invoice_date <= (current_date - INTERVAL '1 days') THEN SI_net_amount ELSE 0 END) AS "W-1",
SUM(CASE WHEN Invoice_date >= (current_date - INTERVAL '14 days') AND Invoice_date <= (current_date - INTERVAL '8 days') THEN SI_net_amount ELSE 0 END) AS "W-2"

from SO_SI
group by 1
)T
)T1
group by 1
order by 1 asc
),

Formatted as (
select "Metric",
case when "Metric" in ('PTR Sales','Total Sales Return','Akna GMV', 'Impex GMV','Shreeji GMV','Vardhman GMV')
then "D-1" / 1000000 else ROUND("D-1") end as "D-1",

case when "Metric" in ('PTR Sales','Total Sales Return','Akna GMV', 'Impex GMV','Shreeji GMV','Vardhman GMV')
then "D-2" / 1000000 else ROUND("D-2") end as "D-2",

case when "Metric" in ('PTR Sales','Total Sales Return','Akna GMV', 'Impex GMV','Shreeji GMV','Vardhman GMV')
then "D-8" / 1000000 else ROUND("D-8") end as "D-8",

case when "Metric" in ('PTR Sales','Total Sales Return','Akna GMV', 'Impex GMV','Shreeji GMV','Vardhman GMV')
then "W-1" / 1000000 else ROUND("W-1") end as "W-1",

case when "Metric" in ('PTR Sales','Total Sales Return','Akna GMV', 'Impex GMV','Shreeji GMV','Vardhman GMV')
then "W-2" / 1000000 else ROUND("W-2") end as "W-2",

case when "Metric" in ('PTR Sales','Total Sales Return','Akna GMV', 'Impex GMV','Shreeji GMV','Vardhman GMV')
then "MTD-0" / 1000000 else ROUND("MTD-0") end as "MTD",

case when "Metric" in ('PTR Sales','Total Sales Return','Akna GMV', 'Impex GMV','Shreeji GMV','Vardhman GMV')
then "MTD-1" / 1000000 else ROUND("MTD-1") end as "LMTD",

case when "Metric" in ('PTR Sales','Total Sales Return','Akna GMV', 'Impex GMV','Shreeji GMV','Vardhman GMV')
then "M-1" / 1000000 else ROUND("M-1") end as "LM"

from(
select * from PTR
union 
select * from orders
union
select * from Ordered_AOV
union  
select * from Return
union 
select * from GMV
)x
ORDER BY order_colmn
),

Adjustment AS (
    SELECT "D-1", "D-2", "D-8","W-1",
"W-2","MTD", "LMTD","LM"  FROM Formatted WHERE "Metric" = 'Total Sales Return'
),

UpdatedTable AS (
    SELECT
        t."Metric",
        CASE WHEN t."Metric" = 'PTR Sales' THEN t."D-1" - a."D-1" ELSE t."D-1" END AS "D-1",
        CASE WHEN t."Metric" = 'PTR Sales' THEN t."D-2" - a."D-2" ELSE t."D-2" END AS "D-2",
        CASE WHEN t."Metric" = 'PTR Sales' THEN t."D-8" - a."D-8" ELSE t."D-8" END AS "D-8",
        CASE WHEN t."Metric" = 'PTR Sales' THEN t."W-1" - a."W-1" ELSE t."W-1" END AS "W-1",
        CASE WHEN t."Metric" = 'PTR Sales' THEN t."W-2" - a."W-2" ELSE t."W-2" END AS "W-2",
        CASE WHEN t."Metric" = 'PTR Sales' THEN t."MTD" - a."MTD" ELSE t."MTD" END AS "MTD",
        CASE WHEN t."Metric" = 'PTR Sales' THEN t."LMTD" - a."LMTD" ELSE t."LMTD" END AS "LMTD",
        CASE WHEN t."Metric" = 'PTR Sales' THEN t."LM" - a."LM" ELSE t."LM" END AS "LM"
    FROM Formatted t, Adjustment a
)
SELECT *, current_date as "Latest Updated at" FROM UpdatedTable;