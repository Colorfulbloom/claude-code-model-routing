# Default history range: what banks and dashboards do (2026-11-08)

Question from the owner: "what do banks do?" for the default history range once stored data goes past 30 days.

## Answer

Banks don't publish a default range. Their sites show the newest activity first and let you scroll or search back, with a short transaction list (about 12 to 24 months) and a long statement archive (6 to 7 years). Analytics and billing dashboards that state a default pick a short recent window (Stripe financial reports default to the prior month) and put longer ranges one click away.

Recommendation (inference): keep the default at the last 30 days, which is also Claude Code's transcript retention default, and offer presets of 7 days, 30 days, 90 days, 12 months and All history, plus a custom range. Say on screen which limit applies to All history ("since the dashboard started keeping history on <date>"), the way banks separate the transaction list from statements.

## Evidence

| Product | Default range | Presets offered | Max history | Source (quoted line) |
|---|---|---|---|---|
| Capital One checking and savings | Not stated. The app shows recent transactions first with "view all" (fetch summary, not a quote) | None listed | Transaction list 2 years, statements 7 years | https://www.capitalone.com/help-center/checking-savings/transaction-history/ "Your past transactions list will show the past two years of account activity on the website." and "your statements will include the past seven years of transaction history." (both fetched by the lead) |
| HSBC UK | Not stated | Statements by month, or year then month. Transactions by date range, amount, keyword | Statements 6 years | https://www.hsbc.co.uk/help/banking-made-easy/online-statements/ "You can view old statements up to 6 years back in online or mobile banking." |
| Monzo | Not stated | Statement date range; PDF, CSV or QIF | Not stated | https://monzo.com/ie/help/using-monzo/help-statements "Choose your date range and download format (PDF, CSV or QIF)." |
| Bank of America credit cards | Not stated | None listed | 12 months of detailed transactions | https://www.bankofamerica.com/credit-cards/credit-card-payments-statements-faq/ "Request up to 12 months of detailed transaction information" |
| Stripe financial reports | Prior month | Previous months, month to date, custom dates | Not stated | https://docs.stripe.com/reports/options "When loading the page, the reports default to displaying data for the prior month. You can select previous months, current month-to-date, or customize the date range to specific dates." (fetched by the lead) |
| Stripe Dashboard home charts | Not stated | Preset or custom, plus a comparison period | Not stated | https://support.stripe.com/questions/dashboard-home-page-charts-for-business-insights "Select a preset or custom date range from the first dropdown menu." |
| Google Analytics 4 | Not stated on the date picker page | Names "Last 7 days" and "Last 12 months"; compare to previous period or previous year | Explorations 2 or 14 months of event data | https://support.google.com/analytics/answer/13412290 (picker), https://support.google.com/analytics/answer/7667196 (retention) |
| Plausible | Not stated | Today, yesterday, last 24 hours, last 7, 28, 30 and 91 days, month to date, last month, year to date, last 6 and 12 months, all time, custom | All time | https://plausible.io/docs/keyboard-shortcuts |
| Anthropic Console usage and cost | Not stated | A month, narrowed to a day | Not stated | https://support.claude.com/en/articles/9534590-cost-and-usage-reporting-in-console "Choose the month you're interested in (or narrow to a specific month/day)." |
| OpenAI usage dashboard | Not stated | "Month to date" plus a custom picker | Not stated | https://help.openai.com/en/articles/20001072-how-do-i-export-monthly-usage-details-from-the-api-usage-dashboard (search snippet only, page refused the fetch) |

Rows without "fetched by the lead" come from the scout's fetches on November 8 and were not re-read.

## Patterns (inference)

- Written defaults are rare. The ones found are fixed past periods (prior month) or month to date.
- Presets cluster at 7, 28 or 30, 90 or 91 days, 12 months, month to date, year to date and all time. Plausible shows the fullest list.
- Long-history products name which limit applies. Banks split the transaction list from statements, and GA4 states the explorations cap.
- Claude Code deletes transcripts after `cleanupPeriodDays` (default 30, 25-verifier-gap-research.md), so anything past 30 days exists only in the dashboard database. A 30-day default shows the same window a fresh install can show.

## UNVERIFIED

- Chase, Wells Fargo, Citi, Ally and Revolut: official help pages returned 404 or 403, or were not searched.
- The "Last 28 days" default often cited for GA4 standard reports appears only in secondary sources and Looker Studio docs, not in a GA4 help page the scout or lead opened. Two URLs given in a first scout draft (plausible.io/docs/dashboard-date-range and support.google.com/analytics/answer/10079470) returned 404 when the lead fetched them, so they are not used.
- Vercel, Amplitude, Cloudflare, Mixpanel and GitHub Insights defaults: no official source found.
