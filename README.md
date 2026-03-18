# Production Incident Analyzer

**Automated Jira incident analytics pipeline with intelligent Excel reporting for enterprise production environments.**

Built for a large-scale automotive production context, this tool fetches incident data from Jira, applies domain-specific business logic, and generates multi-sheet Excel reports with aggregated metrics, trend analysis, and severity breakdowns — ready for stakeholder review.

---

## Overview

Production Incident Analyzer bridges the gap between raw Jira issue data and actionable incident analytics. Rather than exporting flat CSV dumps, it applies layered business rules — cross-month ticket expansion, working-hours-based duration calculations, priority-based system resolution, and curated summary tables — to produce reports that reflect how incidents actually impact operations.

### Key Capabilities

- **Jira REST API v3 integration** with automatic pagination, rate limiting, and exponential backoff
- **Configurable field mapping** system that adapts to any Jira custom field schema
- **Business hours engine** that calculates resolution times using real working hours (9:00-13:00, 14:00-18:00), excluding weekends and Italian national holidays via `workalendar`
- **Cross-month ticket expansion** — incidents spanning multiple months are attributed to each month they were open, with cumulative working-hour contributions
- **Cross-year safe grouping** — `MMM-YYYY` and `Qn-YYYY` formats with chronological sorting prevent year-boundary ambiguity
- **Multi-sheet Excel reports** with styled pivot tables, raw data, run metadata, and self-documenting filter descriptions per table
- **CLI and GUI** entry points, with support for caching, sample data input, and field discovery

---

## Architecture

```
Jira REST API (v3)
    |
    v
JiraClient ── fetch + paginate + retry (429 backoff)
    |
    v
DataTransformer ── flatten custom fields + parse datetimes + derive period keys
    |
    v
Aggregator ── apply business filters + compute metrics + build pivot tables
    |
    v
ExcelGenerator ── render multi-sheet workbook with styling and metadata
    |
    v
 .xlsx report
```

### Module Breakdown

| Module | Responsibility |
|---|---|
| `main.py` | CLI orchestration, argument parsing, caching logic |
| `src/config.py` | Environment-based configuration and validation |
| `src/jira_client.py` | Jira API client with pagination and retry logic |
| `src/data_transformer.py` | Field normalization, datetime parsing, computed columns |
| `src/aggregator.py` | Business filters, severity/phase/system aggregations, cross-month logic |
| `src/excel_generator.py` | Workbook creation, sheet styling, table descriptions |
| `src/business_hours.py` | Working hours/days calculator (respects lunch, weekends, holidays) |
| `src/holidays.py` | Italian holiday calendar with `workalendar` integration and fixed-date fallback |
| `mappings/*.json` | External configuration for field IDs, phases, severity ordering, system priority |

---

## Report Output

The generated Excel workbook includes:

| Sheet | Content |
|---|---|
| **About** | Run metadata — timestamp (Europe/Rome), Jira site, JQL query used |
| **Your Jira Issues** | Full transformed dataset with all fields |
| **Pivot Tables** | Issue counts, average resolution times, monthly severity summaries |
| **Riepilogo** | Analyst-oriented summary tables, each with documented filter/calculation rules |

Summary tables in the Riepilogo sheet include:

- Monthly incident counts by severity (with cross-month expansion)
- Blocker & Severe incidents by journey phase (quarterly)
- Dealer journey tracking with system-level splits
- Average working hours and working days by month
- Root cause analysis by quarter
- System/application analysis with priority-based resolution
- Monthly blocker closure tracking

---

## Tech Stack

| Technology | Purpose |
|---|---|
| **Python 3** | Core language |
| **Pandas** | Data manipulation, pivot tables, aggregation |
| **openpyxl** | Excel workbook generation with cell-level styling |
| **requests** | HTTP client for Jira REST API |
| **workalendar** | Italian national holiday calendar |
| **python-dotenv** | Environment variable management |
| **python-dateutil** | Flexible datetime parsing |
| **PyInstaller** | Standalone executable bundling |

---

## Usage

```bash
# Standard report generation (verbose)
python main.py -v

# Custom output path
python main.py -o reports/my_report.xlsx

# Use cached API data (for development)
python main.py --use-cache

# Save API response to cache
python main.py --save-cache

# Discover Jira custom field IDs
python main.py --discover-fields

# GUI mode
python gui_app.py
```

### Configuration

The tool reads from a `.env` file:

```env
JIRA_SITE=https://your-instance.atlassian.net
JIRA_USERNAME=your.email@example.com
JIRA_API_TOKEN=your_api_token
```

Field mappings, severity ordering, phase definitions, and system priority are all externalized in `mappings/*.json`, making the tool adaptable to different Jira configurations without code changes.

---

## License

This project is licensed under a **proprietary source-available license**. You may view the source code for reference and evaluation purposes only. Forking, copying, modifying, distributing, or using this code in any form — commercial or non-commercial — is not permitted without explicit written authorization.

See [LICENSE](LICENSE) for full terms.
