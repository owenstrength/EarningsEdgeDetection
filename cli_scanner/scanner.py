#!/usr/bin/env python3
"""
CLI Scanner for earnings-based options opportunities.
Automatically determines dates based on current time and outputs recommended tickers.
"""
 
import argparse
import logging
import sys
import re
from datetime import datetime
 
from utils.logging_utils import setup_logging
from core.scanner import EarningsScanner
 
def main():
    parser = argparse.ArgumentParser(
        description="""
        Scans for recommended options plays based on upcoming earnings.
        If run before 4PM Eastern: Checks today's post-market and tomorrow's pre-market earnings
        If run after 4PM Eastern: Checks tomorrow's post-market and following day's pre-market earnings
        """
    )
    parser.add_argument(
        '--date', '-d',
        help='Optional date to check in MM/DD/YYYY format (e.g., 03/20/2025). '
             'If not provided, uses current date logic.',
        type=str
    )
    parser.add_argument(
        '--parallel', '-p',
        help='Enable parallel processing with specified number of workers',
        type=int,
        default=0
    )
    parser.add_argument(
        '--list', '-l',
        help='Show compact output with only ticker symbols and tiers',
        action='store_true'
    )
    parser.add_argument(
        '--iron-fly', '-i',
        help='Calculate and display recommended iron fly strikes',
        action='store_true'
    )
    parser.add_argument(
        '--analyze', '-a',
        help='Analyze a specific ticker symbol and display all metrics regardless of pass/fail status',
        type=str,
        metavar='TICKER'
    )
    parser.add_argument(
        '--use-finnhub', '-f',
        help=argparse.SUPPRESS,  # Hide from help
        action='store_true'
    )
    # Combined sources flag - new preferred approach
    parser.add_argument(
        '--all-sources', '-c',
        help='Use all available earnings data sources (Investing.com, Finnhub, DoltHub) and combine results',
        action='store_true'
    )
    
    # Keep these flags for backward compatibility
    parser.add_argument(
        '--use-dolthub', '-u',
        help=argparse.SUPPRESS,  # Hide from help
        action='store_true'
    )
    args = parser.parse_args()
 
    setup_logging(log_dir="logs")
    logger = logging.getLogger(__name__)
    
    input_date = None
    if args.date:
        try:
            input_date = args.date
            datetime.strptime(input_date, '%m/%d/%Y')  # Validate date format
            logger.info(f"Using provided date: {input_date}")
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            sys.exit(1)
    else:
        now = datetime.now()
        logger.info(f"No date provided. Using current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
 
    scanner = EarningsScanner()
 
    # Check if we're analyzing a specific ticker instead of running a full scan
    if args.analyze:
        ticker = args.analyze.strip().upper()
        print(f"\n=== ANALYZING {ticker} ===\n")
        
        # Analyze the ticker and get all metrics
        metrics = scanner.analyze_ticker(ticker)
        
        if 'error' in metrics:
            print(f"Error analyzing {ticker}: {metrics['error']}")
            return
        
        # Format the results for display
        print(f"SPY IV/RV: {metrics.get('spy_iv_rv', 'N/A'):.2f}")
        print(f"Current thresholds - Pass: {metrics.get('iv_rv_pass_threshold', 1.25):.2f}, "
              f"Near Miss: {metrics.get('iv_rv_near_miss_threshold', 1.0):.2f}\n")
        
        # Print status
        status = "PASS - "
        if metrics.get('pass', False):
            if metrics.get('tier', 0) == 1:
                status += "TIER 1"
            elif metrics.get('tier', 0) == 2:
                status += "TIER 2"
            else:
                status += "PASS"
        elif metrics.get('near_miss', False):
            status = "NEAR MISS"
        else:
            status = "FAIL"
        
        print(f"Status: {status}")
        print(f"Reason: {metrics.get('reason', 'N/A')}\n")
        
        # Print all available metrics
        print("CORE METRICS:")
        if 'price' in metrics:
            print(f"  Price: ${metrics['price']:.2f}")
        if 'volume' in metrics:
            print(f"  Volume: {metrics['volume']:,.0f}")
        if 'term_structure' in metrics:
            print(f"  Term Structure: {metrics['term_structure']:.4f}")
        if 'iv_rv_ratio' in metrics:
            print(f"  IV/RV Ratio: {metrics['iv_rv_ratio']:.2f}")
        if 'win_rate' in metrics and 'win_quarters' in metrics:
            print(f"  Winrate: {metrics['win_rate']:.1f}% over the last {metrics['win_quarters']} earnings")
        if 'float_ratio' in metrics:
            print(f"  Float/Market Cap: {metrics['float_ratio']:.4f}")
        
        # Print additional metrics if available
        print("\nADDITIONAL METRICS:")
        for key, value in metrics.items():
            # Skip metrics we already displayed or internal metrics
            if key in ['price', 'volume', 'term_structure', 'iv_rv_ratio', 'win_rate', 'win_quarters',
                       'pass', 'near_miss', 'tier', 'reason', 'iv_rv_pass_threshold', 
                       'iv_rv_near_miss_threshold', 'spy_iv_rv']:
                continue
                
            # Format numbers nicely
            if isinstance(value, float):
                print(f"  {key}: {value:.4f}")
            else:
                print(f"  {key}: {value}")
        
        # Calculate and display iron fly strikes if flag is set
        if args.iron_fly:
            print("\nIRON FLY STRATEGY:")
            iron_fly = scanner.calculate_iron_fly_strikes(ticker)
            if "error" not in iron_fly:
                print(f"  Expiration: {iron_fly['expiration']}")
                
                # Line 1: Short options and premium
                print(f"  SHORT: ${iron_fly['short_put_strike']} Put (${iron_fly['short_put_premium']}), ")
                print(f"         ${iron_fly['short_call_strike']} Call (${iron_fly['short_call_premium']})")
                print(f"         Total Credit: ${iron_fly['total_credit']}")
                
                # Line 2: Long options and premium
                print(f"  LONG:  ${iron_fly['long_put_strike']} Put (${iron_fly['long_put_premium']}), ")
                print(f"         ${iron_fly['long_call_strike']} Call (${iron_fly['long_call_premium']})")
                print(f"         Total Debit: ${iron_fly['total_debit']}")
                
                print(f"  Net Credit: ${iron_fly['net_credit']}")
                print(f"  Break-even Range: ${iron_fly['lower_breakeven']} to ${iron_fly['upper_breakeven']}")
                print(f"  Wings: ${iron_fly['put_wing_width']} Put Side, ${iron_fly['call_wing_width']} Call Side")
                print(f"  Max Profit: ${iron_fly['max_profit']}, Max Risk: ${iron_fly['max_risk']}")
                print(f"  Risk/Reward: 1:{iron_fly['risk_reward_ratio']}")
            else:
                print(f"  {iron_fly['error']}")
        return
        
    try:
        recommended, near_misses, stock_metrics = scanner.scan_earnings(
            input_date=input_date,
            workers=args.parallel,
            use_finnhub=args.use_finnhub,
            use_dolthub=args.use_dolthub,
            all_sources=args.all_sources
        )
        if recommended or near_misses:
            print("\n=== SCAN RESULTS ===")
            
            # Get tickers by tier
            tier1_tickers = [t for t in recommended if stock_metrics[t].get('tier', 1) == 1]
            tier2_tickers = [t for t in recommended if stock_metrics[t].get('tier', 1) == 2]
            
            # Compact output mode
            if args.list:
                print("\nTIER 1:", ", ".join(tier1_tickers) if tier1_tickers else "None")
                print("TIER 2:", ", ".join(tier2_tickers) if tier2_tickers else "None")
                print("NEAR MISSES:", ", ".join([t for t, _ in near_misses]) if near_misses else "None")
                
                # If iron fly flag is also specified
                if args.iron_fly:
                    print("\nIRON FLY RECOMMENDATIONS:")
                    # Process Tier 1 tickers
                    if tier1_tickers:
                        print("\n  TIER 1 TRADES:\n")
                        for i, ticker in enumerate(tier1_tickers):
                            if i > 0:
                                print()  # Add blank line between stocks
                            iron_fly = scanner.calculate_iron_fly_strikes(ticker)
                            if "error" not in iron_fly:
                                # Line 1: Short options and credit, Long options and debit
                                print(f"    {ticker} ({iron_fly['expiration']}):")
                                print(f"      Short ${iron_fly['short_put_strike']}P/${iron_fly['short_call_strike']}C for ${iron_fly['total_credit']} credit, "  
                                      f"Long ${iron_fly['long_put_strike']}P/${iron_fly['long_call_strike']}C for ${iron_fly['total_debit']} debit")
                                # Line 2: Break-evens and risk:reward
                                print(f"      Break-evens: ${iron_fly['lower_breakeven']}-${iron_fly['upper_breakeven']}, "  
                                      f"Risk/Reward: 1:{iron_fly['risk_reward_ratio']}")
                    # Process Tier 2 tickers
                    if tier2_tickers:
                        print("\n  TIER 2 TRADES:\n")
                        for i, ticker in enumerate(tier2_tickers):
                            if i > 0:
                                print()  # Add blank line between stocks
                            iron_fly = scanner.calculate_iron_fly_strikes(ticker)
                            if "error" not in iron_fly:
                                # Line 1: Short options and credit, Long options and debit
                                print(f"    {ticker} ({iron_fly['expiration']}):")
                                print(f"      Short ${iron_fly['short_put_strike']}P/${iron_fly['short_call_strike']}C for ${iron_fly['total_credit']} credit, "  
                                      f"Long ${iron_fly['long_put_strike']}P/${iron_fly['long_call_strike']}C for ${iron_fly['total_debit']} debit")
                                # Line 2: Break-evens and risk:reward
                                print(f"      Break-evens: ${iron_fly['lower_breakeven']}-${iron_fly['upper_breakeven']}, "  
                                      f"Risk/Reward: 1:{iron_fly['risk_reward_ratio']}")
            
            # Normal detailed output mode
            else:
                print("\nTIER 1 RECOMMENDED TRADES:")
                if tier1_tickers:
                    for ticker in tier1_tickers:
                        metrics = stock_metrics[ticker]
                        print(f"\n  {ticker}:")
                        print(f"    Price: ${metrics['price']:.2f}")
                        print(f"    Volume: {metrics['volume']:,.0f}")
                        print(f"    Winrate: {metrics['win_rate']:.1f}% over the last {metrics['win_quarters']} earnings")
                        print(f"    IV/RV Ratio: {metrics['iv_rv_ratio']:.2f}")
                        print(f"    Term Structure: {metrics['term_structure']:.3f}")
                        print(f"    Float/Market Cap: {metrics['float_ratio']:.4f}")

                        # Calculate and display iron fly strikes if flag is set
                        if args.iron_fly:
                            iron_fly = scanner.calculate_iron_fly_strikes(ticker)
                            if "error" not in iron_fly:
                                print("    --------------------")
                                print("    IRON FLY STRATEGY:")
                                print(f"      Expiration: {iron_fly['expiration']}")
                                
                                # Line 1: Short options and premium
                                print(f"      SHORT: ${iron_fly['short_put_strike']} Put (${iron_fly['short_put_premium']}), ")
                                print(f"             ${iron_fly['short_call_strike']} Call (${iron_fly['short_call_premium']})")
                                print(f"             Total Credit: ${iron_fly['total_credit']}")
                                
                                # Line 2: Long options and premium
                                print(f"      LONG:  ${iron_fly['long_put_strike']} Put (${iron_fly['long_put_premium']}), ")
                                print(f"             ${iron_fly['long_call_strike']} Call (${iron_fly['long_call_premium']})")
                                print(f"             Total Debit: ${iron_fly['total_debit']}")
                                
                                print(f"      Net Credit: ${iron_fly['net_credit']}")
                                print(f"      Break-even Range: ${iron_fly['lower_breakeven']} to ${iron_fly['upper_breakeven']}")
                                print(f"      Wings: ${iron_fly['put_wing_width']} Put Side, ${iron_fly['call_wing_width']} Call Side")
                                print(f"      Max Profit: ${iron_fly['max_profit']}, Max Risk: ${iron_fly['max_risk']}")
                                print(f"      Risk/Reward: 1:{iron_fly['risk_reward_ratio']}")
                else:
                    print("  None")
                
                print("\nTIER 2 RECOMMENDED TRADES:")
                if tier2_tickers:
                    for ticker in tier2_tickers:
                        metrics = stock_metrics[ticker]
                        print(f"\n  {ticker}:")
                        print(f"    Price: ${metrics['price']:.2f}")
                        print(f"    Volume: {metrics['volume']:,.0f}")
                        print(f"    Winrate: {metrics['win_rate']:.1f}% over the last {metrics['win_quarters']} earnings")
                        print(f"    IV/RV Ratio: {metrics['iv_rv_ratio']:.2f}")
                        print(f"    Term Structure: {metrics['term_structure']:.3f}")
                        print(f"    Float/Market Cap: {metrics['float_ratio']:.4f}")
                        
                        # Calculate and display iron fly strikes if flag is set
                        if args.iron_fly:
                            iron_fly = scanner.calculate_iron_fly_strikes(ticker)
                            if "error" not in iron_fly:
                                print("    --------------------")
                                print("    IRON FLY STRATEGY:")
                                print(f"      Expiration: {iron_fly['expiration']}")
                                
                                # Line 1: Short options and premium
                                print(f"      SHORT: ${iron_fly['short_put_strike']} Put (${iron_fly['short_put_premium']}), ")
                                print(f"             ${iron_fly['short_call_strike']} Call (${iron_fly['short_call_premium']})")
                                print(f"             Total Credit: ${iron_fly['total_credit']}")
                                
                                # Line 2: Long options and premium
                                print(f"      LONG:  ${iron_fly['long_put_strike']} Put (${iron_fly['long_put_premium']}), ")
                                print(f"             ${iron_fly['long_call_strike']} Call (${iron_fly['long_call_premium']})")
                                print(f"             Total Debit: ${iron_fly['total_debit']}")
                                
                                print(f"      Net Credit: ${iron_fly['net_credit']}")
                                print(f"      Break-even Range: ${iron_fly['lower_breakeven']} to ${iron_fly['upper_breakeven']}")
                                print(f"      Wings: ${iron_fly['put_wing_width']} Put Side, ${iron_fly['call_wing_width']} Call Side")
                                print(f"      Max Profit: ${iron_fly['max_profit']}, Max Risk: ${iron_fly['max_risk']}")
                                print(f"      Risk/Reward: 1:{iron_fly['risk_reward_ratio']}")
                else:
                    print("  None")
     
                print("\nNEAR MISSES:")
                if near_misses:
                    for ticker, reason in near_misses:
                        metrics = stock_metrics[ticker]
                        print(f"\n  {ticker}:")
                        print(f"    Failed: {reason}")
                        print(f"    Metrics:")
                        print(f"      Price: ${metrics['price']:.2f}")
                        print(f"      Volume: {metrics['volume']:,.0f}")
                        print(f"      Winrate: {metrics['win_rate']:.1f}% over the last {metrics['win_quarters']} earnings")
                        print(f"      IV/RV Ratio: {metrics['iv_rv_ratio']:.2f}")
                        print(f"      Term Structure: {metrics['term_structure']:.3f}")
                        print(f"    Float/Market Cap: {metrics['float_ratio']:.4f}")
                else:
                    print("  None")
            
            print("\n")
        else:
            logger.info("No recommended stocks found")
    except ValueError as e:
        logger.error(f"Error: {str(e)}")
 
if __name__ == "__main__":
    main()