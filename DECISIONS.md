## Data quality findings

### subscribers.csv
- **Finding:** 8 rows are blank in every column
  **Rule:** This row is skipped, but the record is recorded as skipped.
  **Why:** Nothing we can do about this lack of information. If we have future information of a lot of blank rows, we will be able ot track it easier. 

  - **Finding:** 0 exact duplicates. 63 hidden by capitilzation. 22 more have leading and trailing space. 85 duplicate rows in total, 2902 unique subscribers.
  **Rule:** Strip leading and trailing space, and lowercase.
  **Why:** So we are not duplicating people.