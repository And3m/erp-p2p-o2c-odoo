-- Trial balance straight from Odoo's posted journal lines.
SELECT a.code_store ->> m.company_id::text AS account_code,
       a.name ->> 'en_US'                  AS account_name,
       a.account_type,
       ROUND(SUM(l.debit), 2)              AS total_debit,
       ROUND(SUM(l.credit), 2)             AS total_credit,
       ROUND(SUM(l.balance), 2)            AS balance
FROM account_move_line l
JOIN account_move m    ON m.id = l.move_id
JOIN account_account a ON a.id = l.account_id
WHERE m.state = 'posted'
GROUP BY 1, 2, 3
ORDER BY 1;
