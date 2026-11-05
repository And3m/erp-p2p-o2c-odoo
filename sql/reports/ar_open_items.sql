-- Customer open items with days past due as of today.
SELECT m.name                                  AS invoice_no,
       p.name                                  AS customer,
       m.invoice_date,
       m.invoice_date_due                      AS due_date,
       m.amount_total,
       m.amount_residual                       AS open_amount,
       m.payment_state,
       GREATEST(CURRENT_DATE - m.invoice_date_due, 0) AS days_past_due
FROM account_move m
JOIN res_partner p ON p.id = m.commercial_partner_id
WHERE m.move_type = 'out_invoice'
  AND m.state = 'posted'
  AND m.amount_residual > 0
ORDER BY days_past_due DESC, open_amount DESC;
