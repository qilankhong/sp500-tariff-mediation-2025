------------------------INSTRUCTIONS---------------------------
1. Obtain Daily Price Data
Daily prices are required to compute event-window returns.
Step 1: Activate a virtual environment 
(no need to create an environment b/c already previously created in Pt 1)
	source .venv/bin/activate
Step 2: Install required packages
	pip install aiohttp pandas python-dotenv
Step 3: Verify your API Key:
	cat .env
Step 4: Run the script
	python sp500_daily_prices.py
What does success look like?
You should see output like:
1/203 CME
✅ saved CME
2/203 CMG
✅ saved CMG
3/203 CMI
✅ saved CMI
...
203/203 WAT
✅ saved WAT
✅ Finished. Saved data/sp500_daily_prices.csv with 125,697 rows

2. Obtain Daily Price Log Returns Data (assuming you have completed PTS 1, 2)
Step 1: Run the script
	python make_event_returns.py
You should see:
	✅ event_returns.csv created
	*and a preview*

3. Use event_returns.csv to run real_data_analysis_3/23/26.R

-----------------------------INFO---------------------------------

sp500_daily_prices.py
- output columns: [symbol, date, adjClose]
- fetches S&P 500 daily adjusted closing prices for 2025 from FMP
- current target range: 2025-01-01 -> 2025-12-31
- uses the ticker list from the existing CSV file rather than calling the restricted FMP S&P 500 constituent endpoint
- updated to run more slowly / sequentially because FMP was returning HTTP 429 rate-limit errors

event_returns.py
- computes daily log returns from adjClose:
  log_return = ln(adjClose_t / adjClose_t-1)

- tariff-related windows:

1. Initial tariff-driven decline
   - 2025-02-19 -> 2025-03-13
   - saved as: S1_Decline

2. Escalation collapse
   - 2025-03-25 -> 2025-04-08
   - saved as: S2_Escalation_Collapse

3. Policy shock jump
   - 2025-04-08 -> 2025-04-09
   - saved as: S3_Policy_Shock_Jump

4. Uncertainty-driven decline
   - 2025-04-09 -> 2025-04-21
   - saved as: S4_Uncertainty_Decline

5. Long-term adjustment
   - 2025-02-19 -> 2025-12-31
   - saved as: S5_Long_Term_Adjustment

- each event return is computed by summing daily log returns within the window for each stock
- output file: event_returns.csv
