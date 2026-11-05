-- Receipts and payments applied to each invoice, from Odoo's reconciliation table.
-- account_partial_reconcile links the receivable or payable line of the invoice to the
-- matching line of the payment, with the amount applied.
SELECT inv.name                  AS invoice_no,
       inv.move_type,
       pay.name                  AS settlement_no,
       pay.date                  AS settlement_date,
       apr.amount
FROM account_partial_reconcile apr
JOIN account_move_line dl ON dl.id = apr.debit_move_id
JOIN account_move_line cl ON cl.id = apr.credit_move_id
JOIN account_move inv     ON inv.id = CASE WHEN dl.move_id IN (SELECT id FROM account_move
                                                               WHERE move_type = 'out_invoice')
                                           THEN dl.move_id ELSE cl.move_id END
JOIN account_move pay     ON pay.id = CASE WHEN inv.id = dl.move_id THEN cl.move_id ELSE dl.move_id END
WHERE inv.move_type IN ('out_invoice', 'in_invoice')
  AND inv.state = 'posted'
ORDER BY pay.date, inv.name;
