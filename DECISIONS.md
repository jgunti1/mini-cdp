## Data quality findings

### subscribers.csv
- **Finding:** 8 rows are blank in every column
  **Rule:** This row is skipped, but the record is recorded as skipped.
  **Why:** Nothing we can do about this lack of information. If we have future information of a lot of blank rows, we will be able ot track it easier. 

  - **Finding:** 0 exact duplicates. 63 hidden by capitilzation. 22 more have leading and trailing space. 85 duplicate rows in total, 2902 unique subscribers.
  **Rule:** Strip leading and trailing space, and lowercase.
  **Why:** So we are not duplicating people.

  - **Finding:** No rows with duplicate entries varying in status or dates, but handling in case. 
  **Rule:** merge duplicates
  -- Signup date: Earliest Date
  -- Last Open Date: Latest Date
  -- Status: Unsubscribed if any row says so. 
  -- Acquistion source: Keep the source from the row with the earliest signup date. 
  **Why:** so we don't spam people and so we have the most up to date information. Earliest sign up date is for when they actually joined. 

 - **Finding:** 2 rows with invalid emails entries. 
  **Rule:** Send to a rejected table.
  **Why:** DOn't want to try sending invalid emails information.

- **Finding:** 2900 valid subscribers. 