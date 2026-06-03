---
name: scrape_and_format_csv
version: 1.0
task_class: web_scraping
status: VALIDATED
trigger: "scrape * to csv"
worker: coder
requires_tools:
  - web
  - file_ops
  - code_exec
not_for:
  - "scraping login-protected pages"
  - "real-time streaming data"
test_input: "scrape table from https://example.com/data"
test_expected_contains:
  - "csv"
  - "headers"
  - "rows"
created: 2026-06-02
source: autolearn
supersedes: null
---

# Scrape Web Page and Format as CSV
## Steps
1. Use `fetch_url` to download the target page HTML
2. Use `code_exec` to run BeautifulSoup parsing
3. Use `write_file` to save the output CSV

## Known Pitfalls
- Some sites block automated requests → use headers with User-Agent
- Tables with merged cells need special handling
