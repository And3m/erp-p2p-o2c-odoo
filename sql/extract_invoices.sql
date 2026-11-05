-- Posted customer invoices and vendor bills, with the partner and due date.
SELECT m.name                    AS invoice_no,
       m.move_type,                                  -- out_invoice (AR) or in_invoice (AP)
       p.id                      AS partner_id,
       p.name                    AS partner_name,
       p.city                    AS partner_city,
       st.code                   AS partner_state,
       m.invoice_date,
       m.invoice_date_due        AS due_date,
       m.amount_untaxed          AS net_amount,
       m.amount_tax              AS gst_amount,
       m.amount_total            AS total_amount,
       m.amount_residual         AS open_amount,
       m.payment_state
FROM account_move m
JOIN res_partner p             ON p.id = m.commercial_partner_id
LEFT JOIN res_country_state st ON st.id = p.state_id
WHERE m.state = 'posted'
  AND m.move_type IN ('out_invoice', 'in_invoice')
ORDER BY m.invoice_date, m.id;
