# interest.co.nz mortgage-rate notes

Public source:

```text
https://www.interest.co.nz/borrowing
```

The page contains an HTML table with id `interest_financial_datatable`. Headers observed:

- Institution
- Product
- Variable floating
- 6 months
- 1 year
- 2 years
- 3 years
- 4 years
- 5 years

Rows include standard and special/LVR products. Some special-line rows use `colspan` and text such as `18 months = 4.99`; the CLI captures those in a `special_lines` field associated with the current institution/product context.

Boundary: read-only advertised table parser. Does not submit mortgage applications, request quotes, or imply eligibility.
