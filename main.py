#!/usr/bin/env python3
"""
AI-Assisted Bug Analysis Workflow - Main Entry Point

Retrieves Jira tickets, transforms data, and generates Excel reports.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config, ConfigError
from src.jira_client import JiraClient, JiraAPIError
from src.data_transformer import DataTransformer
from src.aggregator import Aggregator
from src.excel_generator import ExcelGenerator


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate Excel reports from Jira PI project issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Run with default settings
  python main.py -v                 # Verbose output
  python main.py -o report.xlsx     # Specify output file
  python main.py --use-cache        # Use cached data from previous run
  python main.py --discover-fields  # Just discover and show field mappings
"""
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output file path (default: output/PI-report-YYYY-MM-DD.xlsx)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Use cached JSON data from previous API calls (for development)"
    )
    
    parser.add_argument(
        "--save-cache",
        action="store_true",
        help="Save API response to cache file for later use"
    )
    
    parser.add_argument(
        "--discover-fields",
        action="store_true",
        help="Just discover and display Jira custom field mappings"
    )
    
    parser.add_argument(
        "--sample-data",
        type=str,
        help="Use a local JSON file as input instead of calling API"
    )
    
    return parser.parse_args()


def log(message: str, verbose_only: bool = False, verbose: bool = False):
    """Print a log message."""
    if verbose_only and not verbose:
        return
    print(message)


def discover_fields():
    """Discover and display Jira field mappings."""
    print("\n" + "=" * 60)
    print("JIRA FIELD DISCOVERY")
    print("=" * 60 + "\n")
    
    client = JiraClient()
    discovery_path = Path("mappings/discovered_fields.json")
    result = client.discover_custom_fields(save_to_file=discovery_path)
    
    print("Key fields found:")
    print("-" * 40)
    
    for name, info in result["discovered_fields"].items():
        print(f"\n{name}:")
        print(f"  ID: {info['id']}")
        print(f"  Name: {info['name']}")
        print(f"  Type: {info['type']}")
    
    print(f"\n\nFull discovery saved to: {discovery_path}")
    print(f"Total custom fields in Jira: {len(result['all_custom_fields'])}")


def run_from_sample(sample_path: str, output_path: str = None, verbose: bool = False):
    """Run report generation from a sample JSON file."""
    import json
    
    log(f"Loading sample data from: {sample_path}", verbose=verbose)
    
    with open(sample_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    issues = data.get("issues", [])
    log(f"Loaded {len(issues)} issues from sample file", verbose=verbose)
    
    return generate_report(issues, output_path, verbose)


def run_from_api(use_cache: bool = False, save_cache: bool = False, 
                 output_path: str = None, verbose: bool = False):
    """Run report generation by fetching data from Jira API."""
    cache_path = Path("output/api_cache.json")
    
    if use_cache and cache_path.exists():
        import json
        log(f"Loading cached data from: {cache_path}", verbose=verbose)
        with open(cache_path, 'r', encoding='utf-8') as f:
            issues = json.load(f)
        log(f"Loaded {len(issues)} issues from cache", verbose=verbose)
    else:
        log("Fetching issues from Jira API...", verbose=verbose)
        client = JiraClient()
        
        # Get field list from mappings
        from src.data_transformer import load_field_mappings
        mappings = load_field_mappings()
        fields = mappings.get("api_fields_to_request", [])
        
        issues = client.get_all_issues(fields=fields if fields else None)
        log(f"Fetched {len(issues)} issues from Jira", verbose=verbose)
        
        if save_cache:
            import json
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(issues, f, indent=2, default=str)
            log(f"Saved cache to: {cache_path}", verbose=verbose)
    
    return generate_report(issues, output_path, verbose)


def generate_report(issues: list, output_path: str = None, verbose: bool = False) -> Path:
    """Generate Excel report from issue list."""
    if not issues:
        print("No issues to process!")
        return None
    
    log("\nTransforming data...", verbose=verbose)
    transformer = DataTransformer()
    df = transformer.transform_issues(issues)
    
    log(f"  Transformed {len(df)} issues", verbose_only=True, verbose=verbose)
    log(f"  Columns: {list(df.columns)}", verbose_only=True, verbose=verbose)
    
    log("Generating aggregations...", verbose=verbose)
    aggregator = Aggregator(df)
    
    log("Creating Excel report...", verbose=verbose)
    generator = ExcelGenerator(df, aggregator)
    
    if output_path:
        output_path = Path(output_path)
    
    result_path = generator.generate(output_path)
    
    return result_path


def main():
    """Main entry point."""
    args = parse_args()
    
    print("\n" + "=" * 60)
    print("  AI-Assisted Bug Analysis Workflow")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    try:
        # Validate configuration first
        config = get_config()
        log(f"\nJira Site: {config.jira_site}", verbose_only=True, verbose=args.verbose)
        log(f"Project: {config.jira_project}", verbose_only=True, verbose=args.verbose)
        
        # Handle field discovery mode
        if args.discover_fields:
            discover_fields()
            return 0
        
        # Run report generation
        if args.sample_data:
            result_path = run_from_sample(
                args.sample_data,
                args.output,
                args.verbose
            )
        else:
            result_path = run_from_api(
                use_cache=args.use_cache,
                save_cache=args.save_cache,
                output_path=args.output,
                verbose=args.verbose
            )
        
        if result_path:
            print("\n" + "=" * 60)
            print("  SUCCESS!")
            print("=" * 60)
            print(f"\n✓ Report generated: {result_path}")
            print(f"✓ Output directory: {result_path.parent}")
            print()
            return 0
        else:
            print("\n✗ No report generated")
            return 1
    
    except ConfigError as e:
        print(f"\n✗ Configuration Error: {e}")
        print("\nMake sure you have created a .env file with:")
        print("  JIRA_SITE=https://your-site.atlassian.net")
        print("  JIRA_USERNAME=your.email@example.com")
        print("  JIRA_API_TOKEN=your_api_token")
        return 1
    
    except JiraAPIError as e:
        print(f"\n✗ Jira API Error: {e}")
        return 1
    
    except FileNotFoundError as e:
        print(f"\n✗ File not found: {e}")
        return 1
    
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
