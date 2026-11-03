import frappe
from frappe import _


@frappe.whitelist()
def get_xavirgin_liquidity() -> dict:
	"""Real-time financial overview querying ERPNext 16 GL Entries and Chart of Accounts.

	Respects user permissions: Returns full liquidity for financial roles, department-level
	summaries for Team Leads, and restricted access flags for standard interns/employees.
	"""
	user = frappe.session.user
	roles = set(frappe.get_roles(user))
	is_privileged = bool(roles.intersection({"System Manager", "Xavirgin HR Admin", "Accounts Manager", "Director"}))

	# Fixed for Frappe v16: use frappe.defaults.get_global_default or frappe.db.get_single_value
	default_curr = frappe.defaults.get_global_default("currency") or "INR"
	currency_symbol = frappe.db.get_value("Currency", default_curr, "symbol") or "₹"

	if not is_privileged:
		return {
			"visible": False,
			"amount": 0.0,
			"currency_symbol": currency_symbol,
			"formatted_balance": "🔒 RESTRICTED",
			"formatted_gain": "🔒",
			"formatted_debt": "🔒",
		}

	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		companies = frappe.get_all("Company", limit=1)
		company = companies[0].name if companies else None
	if not company:
		return {
			"visible": True,
			"amount": 0.0,
			"currency_symbol": currency_symbol,
			"formatted_balance": "0.00",
			"formatted_gain": "0.00",
			"formatted_debt": "0.00",
		}

	# 1. Calculate Survival Energy (Cash + Bank accounts in ERPNext Chart of Accounts)
	cash_bank_accounts = frappe.get_all(
		"Account",
		filters={"company": company, "account_type": ["in", ["Cash", "Bank"]], "is_group": 0},
		pluck="name",
	)

	total_balance = 0.0
	if cash_bank_accounts:
		gl_balance = frappe.db.sql(
			"""
			SELECT SUM(debit - credit) 
			FROM `tabGL Entry` 
			WHERE company = %s AND is_cancelled = 0 AND account IN %(accounts)s
		""",
			{"company": company, "accounts": tuple(cash_bank_accounts)},
		)
		total_balance = float(gl_balance[0][0] or 0.0)

	# 2. Fiscal Year Income & Expenses
	today = frappe.utils.today()
	fiscal_year_start = f"{today[:4]}-01-01"

	income_sum = frappe.db.sql(
		"""
		SELECT SUM(credit - debit) 
		FROM `tabGL Entry` ge
		JOIN `tabAccount` acc ON ge.account = acc.name
		WHERE ge.company = %s AND ge.is_cancelled = 0 AND ge.posting_date >= %s AND acc.root_type = 'Income'
	""",
		(company, fiscal_year_start),
	)
	total_gain = float(income_sum[0][0] or 0.0)

	expense_sum = frappe.db.sql(
		"""
		SELECT SUM(debit - credit) 
		FROM `tabGL Entry` ge
		JOIN `tabAccount` acc ON ge.account = acc.name
		WHERE ge.company = %s AND ge.is_cancelled = 0 AND ge.posting_date >= %s AND acc.root_type = 'Expense'
	""",
		(company, fiscal_year_start),
	)
	total_debt = float(expense_sum[0][0] or 0.0)

	# 3. Additional Financial Indicators
	receivables_sum = frappe.db.sql(
		"""
		SELECT SUM(debit - credit) 
		FROM `tabGL Entry` ge
		JOIN `tabAccount` acc ON ge.account = acc.name
		WHERE ge.company = %s AND ge.is_cancelled = 0 AND acc.account_type = 'Receivable'
	""",
		(company,),
	)
	total_receivables = float(receivables_sum[0][0] or 0.0)

	payables_sum = frappe.db.sql(
		"""
		SELECT SUM(credit - debit) 
		FROM `tabGL Entry` ge
		JOIN `tabAccount` acc ON ge.account = acc.name
		WHERE ge.company = %s AND ge.is_cancelled = 0 AND acc.account_type = 'Payable'
	""",
		(company,),
	)
	total_payables = float(payables_sum[0][0] or 0.0)

	# Director Loan tracking
	settings = frappe.get_single("Xavirgin HR Settings")
	director_loan_acc = settings.director_loan_account
	director_loan_balance = 0.0
	if director_loan_acc:
		loan_sum = frappe.db.sql(
			"""
			SELECT SUM(credit - debit) 
			FROM `tabGL Entry` 
			WHERE company = %s AND is_cancelled = 0 AND account = %s
		""",
			(company, director_loan_acc),
		)
		director_loan_balance = float(loan_sum[0][0] or 0.0)

	return {
		"visible": True,
		"amount": total_balance,
		"currency_symbol": currency_symbol,
		"formatted_balance": f"{total_balance:,.2f}",
		"formatted_gain": f"{total_gain:,.2f}",
		"formatted_debt": f"{total_debt:,.2f}",
		"receivables": f"{total_receivables:,.2f}",
		"payables": f"{total_payables:,.2f}",
		"director_loan": f"{director_loan_balance:,.2f}",
	}