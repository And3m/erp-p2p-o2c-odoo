-- Posted general ledger lines from Odoo 18 (PostgreSQL).
-- Odoo 18 stores account codes per company in account_account.code_store (jsonb),
-- so the code is read with the move's company id as the key.
SELECT m.name                                                   AS journal_id,
       ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY l.id)      AS line_no,
       l.date                                                   AS posting_date,
       a.code_store ->> m.company_id::text                      AS odoo_account_code,
       a.name ->> 'en_US'                                       AS odoo_account_name,
       l.debit,
       l.credit,
       j.type                                                   AS journal_type,
       j.code                                                   AS journal_code,
       COALESCE(m.ref, m.name)                                  AS doc_ref,
       COALESCE(l.name, '')                                     AS narration,
       st.code                                                  AS partner_state
FROM account_move_line l
JOIN account_move m         ON m.id = l.move_id
JOIN account_account a      ON a.id = l.account_id
JOIN account_journal j      ON j.id = m.journal_id
LEFT JOIN res_partner p     ON p.id = COALESCE(l.partner_id, m.partner_id)
LEFT JOIN res_country_state st ON st.id = p.state_id
WHERE m.state = 'posted'
ORDER BY l.date, m.id, l.id;
