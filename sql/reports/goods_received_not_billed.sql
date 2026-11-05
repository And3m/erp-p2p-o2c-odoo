-- Goods received not yet billed (GRNI): purchase order lines where the quantity received
-- is higher than the quantity billed. The value is what should be accrued at month end,
-- and it equals the balance left on the Stock Interim (Received) account.
SELECT po.name                                         AS purchase_order,
       v.name                                          AS vendor,
       pt.name ->> 'en_US'                             AS product,
       pol.qty_received,
       pol.qty_invoiced,
       pol.qty_received - pol.qty_invoiced             AS qty_not_billed,
       pol.price_unit,
       ROUND((pol.qty_received - pol.qty_invoiced) * pol.price_unit, 2) AS value_not_billed
FROM purchase_order_line pol
JOIN purchase_order po     ON po.id = pol.order_id
JOIN res_partner v         ON v.id = po.partner_id
JOIN product_product pp    ON pp.id = pol.product_id
JOIN product_template pt   ON pt.id = pp.product_tmpl_id
WHERE po.state IN ('purchase', 'done')
  AND pol.qty_received > pol.qty_invoiced
ORDER BY po.name;
