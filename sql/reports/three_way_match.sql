-- Three-way match: ordered vs received vs billed quantity and price for every PO line.
-- A line passes when received equals billed and the billed unit price equals the PO price.
SELECT po.name                           AS purchase_order,
       pt.name ->> 'en_US'               AS product,
       pol.product_qty                   AS qty_ordered,
       pol.qty_received,
       pol.qty_invoiced                  AS qty_billed,
       pol.price_unit                    AS po_price,
       ROUND(AVG(aml.price_unit), 2)     AS billed_price,
       CASE
           WHEN pol.qty_invoiced = 0                     THEN 'Awaiting bill'
           WHEN pol.qty_received <> pol.qty_invoiced     THEN 'Quantity mismatch'
           WHEN ROUND(AVG(aml.price_unit), 2) <> pol.price_unit THEN 'Price mismatch'
           ELSE 'Matched'
       END                               AS match_status
FROM purchase_order_line pol
JOIN purchase_order po     ON po.id = pol.order_id
JOIN product_product pp    ON pp.id = pol.product_id
JOIN product_template pt   ON pt.id = pp.product_tmpl_id
LEFT JOIN account_move_line aml ON aml.purchase_line_id = pol.id
LEFT JOIN account_move am       ON am.id = aml.move_id AND am.state = 'posted'
WHERE po.state IN ('purchase', 'done')
GROUP BY po.name, pt.name, pol.product_qty, pol.qty_received, pol.qty_invoiced, pol.price_unit
ORDER BY po.name, product;
