#!/usr/bin/env bash
# Create a fresh Odoo 18 database for the walkthrough:
#   company in Bengaluru, Karnataka, India (INR), Indian chart of accounts with GST,
#   and the Accounting, Purchase, Sales, and Inventory apps. No demo data.
#
# Usage: scripts/setup_odoo_db.sh <path-to-odoo-bin> <odoo.conf> [db_name]
set -euo pipefail
ODOO_BIN=$1
CONF=$2
DB=${3:-erp_demo}

python3 "$ODOO_BIN" -c "$CONF" -d "$DB" -i base --without-demo=all --stop-after-init

python3 "$ODOO_BIN" shell -c "$CONF" -d "$DB" --no-http <<'EOF'
india = env.ref('base.in')
env.ref('base.INR').active = True
env.company.write({
    'name': 'Deccan Consumer Distributors Pvt Ltd',
    'country_id': india.id,
    'state_id': env['res.country.state'].search([('code', '=', 'KA'), ('country_id', '=', india.id)], limit=1).id,
    'city': 'Bengaluru',
    'currency_id': env.ref('base.INR').id,
})
env.cr.commit()
EOF

python3 "$ODOO_BIN" -c "$CONF" -d "$DB" -i account,l10n_in,purchase,sale_management,stock \
    --without-demo=all --stop-after-init
echo "Database $DB ready. Start Odoo and run scripts/run_walkthrough.py"
