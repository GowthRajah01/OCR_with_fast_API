# schemas.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

class IncomeStatement(BaseModel):
    revenue: Optional[str] = Field(description="Turnover in £'000")
    cost_of_sales: Optional[str] = Field(description="Cost of sales in £'000")
    gross_profit: Optional[str] = Field(description="Gross profit in £'000")
    distribution_costs: Optional[str] = Field(description="Distribution costs in £'000")
    administrative_expenses: Optional[str] = Field(description="Administrative expenses in £'000")
    operating_profit: Optional[str] = Field(description="Operating (loss)/profit in £'000")
    finance_costs_net: Optional[str] = Field(description="Finance costs (net) in £'000")
    other_income: Optional[str] = Field(description="Other income in £'000")
    profit_before_tax: Optional[str] = Field(description="(Loss)/Profit before taxation in £'000")
    tax_charge_credit: Optional[str] = Field(description="Tax (charge)/credit in £'000")
    profit_for_year: Optional[str] = Field(description="(Loss)/Profit for the financial year in £'000")

class BalanceSheet(BaseModel):
    fixed_assets_tangible: Optional[str] = Field(description="Tangible assets in £'000")
    fixed_assets_investments: Optional[str] = Field(description="Investments in £'000")
    total_fixed_assets: Optional[str] = Field(description="Total Fixed Assets in £'000")

    current_assets_stocks: Optional[str] = Field(description="Stocks in £'000")
    current_assets_debtors: Optional[str] = Field(description="Debtors in £'000")
    current_assets_cash_at_bank_and_in_hand: Optional[str] = Field(description="Cash at bank and in hand in £'000")
    current_assets: Optional[str] = Field(description="Total Current Assets in £'000")

    current_liabilities: Optional[str] = Field(description="Creditors: Amounts falling due within one year in £'000")

    net_current_assets: Optional[str] = Field(description="Net Current Assets in £'000")
    total_assets_less_current_liabilities: Optional[str] = Field(description="Total assets less current liabilities in £'000")

    net_assets: Optional[str] = Field(description="Net Assets in £'000")

    equity_called_up_share_capital: Optional[str] = Field(description="Called-up share capital in £'000")
    equity_profit_and_loss_account: Optional[str] = Field(description="Profit and loss account (within equity) in £'000")
    equity: Optional[str] = Field(description="Shareholders' Funds (Equity) in £'000")

    total_assets: Optional[str] = Field(description="Overall Total Assets (Total Fixed Assets + Total Current Assets) in £'000")

class FinancialData(BaseModel):
    company_name: Optional[str]
    year_end_date: Optional[str]
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet
