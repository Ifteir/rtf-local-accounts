RTF LOCAL ACCOUNTS WEBSITE
==========================

INSTALL / RUN (Windows)
1. Extract the ZIP to a normal folder, for example Desktop\RTF Accounts.
2. Install Python 3.10+ from https://www.python.org/downloads/
   During installation, tick "Add Python to PATH".
3. Double-click run_windows.bat.
4. Wait for Flask to install and start. Open http://127.0.0.1:5000
   in Chrome or Edge. The website is local to this PC.
5. Login:
   Username: admin
   Password: admin123
6. Immediately change the password in Settings.
   The app signs you out after a successful change; sign in using the new password.

FEATURES
- Separate Clients and Vendors.
- Search by person name, company name or phone.
- Add/edit client and vendor records; vendor opening balances are not entered on the form. Add vendor purchases and payments as transactions.
- Add client statements with product description, total amount, payment, optional discount and automatically calculated due; record later client payments, discounts and advance payments separately from the client ledger.
- Add vendor purchases, vendor payments, and dedicated Pay vendor due and Advance payment actions.
- Client and vendor history show transaction due changes, with date entry and display in day-month-year format. Print the current page or print/save a statement as PDF, headed by the company and signed-in username.
- Dashboard with counts and outstanding totals.
- SQLite database stored in accounts.db in this folder.

IMPORTANT ACCOUNTING NOTES
- A positive client balance means the client owes you.
- A positive vendor balance means you owe the vendor.
- The dashboard's vendor due list includes both vendors you owe and vendors who owe you back from advance payments.
- Client balance = opening balance + bills (less payments and discounts entered on each bill) + debit adjustments - separate payments and discounts - credit adjustments.
- Vendor balance = opening balance + purchases + debit adjustments - vendor payments - credit adjustments.
- Existing vendor opening balances remain in the account; do not also enter historical purchases for the same amounts.
- Keep regular backups: stop the app and copy accounts.db to a safe location.
- This app is intended for one local PC/user and is not internet hosted.
- The workbook's detailed historical ledgers are not automatically imported. Add balances carefully or request a tailored import after confirming workbook columns.
- Do not delete records after using the system unless you understand that deleting a party also deletes its transactions.

TROUBLESHOOTING
- If "py is not recognized", reinstall Python and enable PATH, or run python app.py after installing Flask.
- If port 5000 is busy, close the other local app using it.
- To stop the website, return to the black command window and press Ctrl+C.
