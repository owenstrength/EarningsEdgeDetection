#!/usr/bin/env python3
"""
Real-time earnings trade monitor for CLI scanner.
Displays Tier 1 and Tier 2 trades with enhanced terminal graphics.
Updates data automatically every few minutes.
"""

import curses
import time
import threading
import sys
import os
import argparse
import logging
from datetime import datetime, timedelta

# Import modules from scanner
from core.scanner import EarningsScanner
from utils.logging_utils import setup_logging

class TradeMonitor:
    def __init__(self, refresh_rate=300, use_all_sources=True):
        self.refresh_rate = refresh_rate  # seconds between updates
        self.use_all_sources = use_all_sources
        self.scanner = EarningsScanner()
        self.tier1_tickers = []
        self.tier2_tickers = []
        self.near_misses = []
        self.stock_metrics = {}
        self.last_update = None
        self.stop_event = threading.Event()
        self.logger = logging.getLogger(__name__)
        
    def fetch_data(self):
        """Fetch latest scanner data"""
        try:
            self.logger.info("Fetching scanner data...")
            recommended, near_misses, stock_metrics = self.scanner.scan_earnings(
                all_sources=self.use_all_sources
            )
            
            # Sort tickers by tier
            self.tier1_tickers = [t for t in recommended if stock_metrics[t].get('tier', 1) == 1]
            self.tier2_tickers = [t for t in recommended if stock_metrics[t].get('tier', 1) == 2]
            self.near_misses = near_misses
            self.stock_metrics = stock_metrics
            self.last_update = datetime.now()
            self.logger.info(f"Data updated. Found {len(self.tier1_tickers)} Tier 1 and {len(self.tier2_tickers)} Tier 2 trades")
        except Exception as e:
            self.logger.error(f"Error fetching data: {str(e)}")

    def format_time_remaining(self):
        """Format time until next refresh"""
        if not self.last_update:
            return "Updating..."
        
        next_update = self.last_update + timedelta(seconds=self.refresh_rate)
        remaining = next_update - datetime.now()
        
        if remaining.total_seconds() <= 0:
            return "Updating..."
        
        minutes, seconds = divmod(int(remaining.total_seconds()), 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def update_data_thread(self):
        """Background thread to update data periodically"""
        while not self.stop_event.is_set():
            self.fetch_data()
            # Sleep in small increments to allow clean shutdown
            for _ in range(self.refresh_rate):
                if self.stop_event.is_set():
                    break
                time.sleep(1)
    
    def draw_borders(self, stdscr, start_y, start_x, height, width):
        """Draw a box border with top, bottom, and left sides only"""
        # Get terminal dimensions
        max_y, max_x = stdscr.getmaxyx()
        
        # Draw top and bottom borders
        for j in range(start_x, start_x + width):
            if j < max_x - 1:
                stdscr.addch(start_y, j, curses.ACS_HLINE)
                if start_y + height - 1 < max_y - 1:
                    stdscr.addch(start_y + height - 1, j, curses.ACS_HLINE)
        
        # Draw left border only
        for i in range(start_y, start_y + height - 1):
            if i < max_y - 1:
                stdscr.addch(i, start_x, curses.ACS_VLINE)
        
        # Draw corners (only on the left side)
        if start_y < max_y - 1 and start_x < max_x - 1:
            stdscr.addch(start_y, start_x, curses.ACS_ULCORNER)
        
        if start_y + height - 1 < max_y - 1 and start_x < max_x - 1:
            stdscr.addch(start_y + height - 1, start_x, curses.ACS_LLCORNER)
        
        # Draw right side corners for top and bottom borders only
        if start_y < max_y - 1 and start_x + width - 1 < max_x - 1:
            stdscr.addch(start_y, start_x + width - 1, curses.ACS_URCORNER)
        
        if start_y + height - 1 < max_y - 1 and start_x + width - 1 < max_x - 1:
            stdscr.addch(start_y + height - 1, start_x + width - 1, curses.ACS_LRCORNER)
    
    def draw_header(self, stdscr, y, x, width, title):
        """Draw a header with title"""
        header = f" {title} "
        pos = x + (width - len(header)) // 2
        stdscr.addstr(y, x, "─" * width, curses.A_BOLD)
        stdscr.addstr(y, pos, header, curses.A_BOLD)
    
    def run(self, stdscr):
        """Main display function using curses"""
        # Set up curses
        curses.start_color()
        curses.use_default_colors()
        curses.curs_set(0)  # Hide cursor
        stdscr.clear()
        stdscr.timeout(1000)  # Set getch timeout to 1 second for responsive UI
        
        # Define color pairs
        curses.init_pair(1, curses.COLOR_GREEN, -1)  # Green for Tier 1
        curses.init_pair(2, curses.COLOR_YELLOW, -1)  # Yellow for Tier 2
        curses.init_pair(3, curses.COLOR_RED, -1)  # Red for Near misses
        curses.init_pair(4, curses.COLOR_CYAN, -1)  # Cyan for headers
        curses.init_pair(5, curses.COLOR_WHITE, -1)  # White for normal text
        
        GREEN = curses.color_pair(1)
        YELLOW = curses.color_pair(2)
        RED = curses.color_pair(3)
        CYAN = curses.color_pair(4)
        WHITE = curses.color_pair(5)
        
        # Start data update thread
        update_thread = threading.Thread(target=self.update_data_thread)
        update_thread.daemon = True
        update_thread.start()
        
        try:
            while True:
                # Get terminal size
                max_y, max_x = stdscr.getmaxyx()
                
                # Check for minimum size
                if max_y < 20 or max_x < 70:
                    stdscr.clear()
                    stdscr.addstr(0, 0, "Terminal too small. Please resize.")
                    stdscr.refresh()
                    time.sleep(1)
                    continue
                
                # Clear screen
                stdscr.clear()
                
                # Draw main border (adjust to avoid bottom-right corner)
                self.draw_borders(stdscr, 0, 0, max_y, max_x)
                
                # Draw title
                title = "EARNINGS TRADES MONITOR"
                stdscr.addstr(1, (max_x - len(title)) // 2, title, curses.A_BOLD | CYAN)
                
                # Draw update status
                status_text = f"Last updated: {self.last_update.strftime('%Y-%m-%d %H:%M:%S') if self.last_update else 'Never'} | Next update in: {self.format_time_remaining()}"
                stdscr.addstr(2, (max_x - len(status_text)) // 2, status_text)
                
                # Divider
                stdscr.addstr(3, 1, "─" * (max_x - 2))
                
                # Calculate column widths
                col_width = (max_x - 3) // 2
                
                # Draw Tier 1 column
                self.draw_header(stdscr, 4, 1, col_width, "TIER 1 TRADES")
                y_pos = 5
                if self.tier1_tickers:
                    for ticker in self.tier1_tickers:
                        if y_pos >= max_y - 2:
                            break
                        
                        metrics = self.stock_metrics[ticker]
                        
                        # Display ticker with box
                        ticker_box = f"[ {ticker} ]"
                        stdscr.addstr(y_pos, 2, ticker_box, GREEN | curses.A_BOLD)
                        
                        # Display metrics
                        y_pos += 1
                        if y_pos < max_y - 2:
                            price_vol = f"  Price: ${metrics['price']:.2f} | Volume: {metrics['volume']:,.0f}"
                            stdscr.addstr(y_pos, 2, price_vol)
                        
                        y_pos += 1
                        if y_pos < max_y - 2:
                            winrate = f"  Winrate: {metrics['win_rate']:.1f}% over {metrics['win_quarters']} earnings"
                            stdscr.addstr(y_pos, 2, winrate)
                        
                        y_pos += 1
                        if y_pos < max_y - 2:
                            iv_rv = f"  IV/RV: {metrics['iv_rv_ratio']:.2f} | Term Structure: {metrics['term_structure']:.3f}"
                            stdscr.addstr(y_pos, 2, iv_rv)
                        
                        # add float ratio information
                        y_pos += 1
                        if y_pos < max_y - 2 and 'float_ratio' in metrics:
                            float_ratio = metrics['float_ratio']
                            float_info = f"  Float Ratio: {float_ratio*100:.2f}%"
                            stdscr.addstr(y_pos, col2_x + 1, float_info)

                        # Add expected move information
                        y_pos += 1
                        if y_pos < max_y - 2 and 'expected_move_pct' in metrics:
                            current_price = metrics['price']
                            em_pct = metrics['expected_move_pct']
                            em_dollars = metrics.get('expected_move_dollars', current_price * em_pct / 100)
                            
                            # Calculate expected price range
                            lower_price = current_price - em_dollars
                            upper_price = current_price + em_dollars
                            
                            em_info = f"  Expected Move: {em_pct:.1f}% (${lower_price:.2f}-${upper_price:.2f})"
                            stdscr.addstr(y_pos, 2, em_info)
                        
                        y_pos += 2  # Space between tickers
                else:
                    msg = "No Tier 1 trades found"
                    stdscr.addstr(y_pos, 2 + max(0, (col_width - len(msg)) // 2), msg)
                
                # Draw Tier 2 column
                col2_x = col_width + 2
                self.draw_header(stdscr, 4, col2_x, col_width, "TIER 2 TRADES")
                y_pos = 5
                if self.tier2_tickers:
                    for ticker in self.tier2_tickers:
                        if y_pos >= max_y - 2:
                            break
                        
                        metrics = self.stock_metrics[ticker]
                        
                        # Display ticker with box
                        ticker_box = f"[ {ticker} ]"
                        stdscr.addstr(y_pos, col2_x + 1, ticker_box, YELLOW | curses.A_BOLD)
                        
                        # Display metrics
                        y_pos += 1
                        if y_pos < max_y - 2:
                            price_vol = f"  Price: ${metrics['price']:.2f} | Volume: {metrics['volume']:,.0f}"
                            stdscr.addstr(y_pos, col2_x + 1, price_vol)
                        
                        y_pos += 1
                        if y_pos < max_y - 2:
                            winrate = f"  Winrate: {metrics['win_rate']:.1f}% over {metrics['win_quarters']} earnings"
                            stdscr.addstr(y_pos, col2_x + 1, winrate)
                        
                        y_pos += 1
                        if y_pos < max_y - 2:
                            iv_rv = f"  IV/RV: {metrics['iv_rv_ratio']:.2f} | Term Structure: {metrics['term_structure']:.3f}"
                            stdscr.addstr(y_pos, col2_x + 1, iv_rv)
                        
                        # add float ratio information
                        y_pos += 1
                        if y_pos < max_y - 2 and 'float_ratio' in metrics:
                            float_ratio = metrics['float_ratio']
                            float_info = f"  Float Ratio: {float_ratio*100:.2f}%"
                            stdscr.addstr(y_pos, col2_x + 1, float_info)

                        # Add expected move information
                        y_pos += 1
                        if y_pos < max_y - 2 and 'expected_move_pct' in metrics:
                            current_price = metrics['price']
                            em_pct = metrics['expected_move_pct']
                            em_dollars = metrics.get('expected_move_dollars', current_price * em_pct / 100)
                            
                            # Calculate expected price range
                            lower_price = current_price - em_dollars
                            upper_price = current_price + em_dollars
                            
                            em_info = f"  Expected Move: {em_pct:.1f}% (${lower_price:.2f}-${upper_price:.2f})"
                            stdscr.addstr(y_pos, col2_x + 1, em_info)
                        
                        y_pos += 2  # Space between tickers
                else:
                    msg = "No Tier 2 trades found"
                    stdscr.addstr(y_pos, col2_x + 1 + max(0, (col_width - len(msg)) // 2), msg)
                
                # Instructions at bottom - ensure we don't write to the last column
                instructions = "Press 'q' to quit, 'r' to refresh data"
                if max_x > len(instructions) + 2:  # Make sure there's room
                    safe_x = min((max_x - len(instructions)) // 2, max_x - len(instructions) - 1)
                    safe_y = max_y - 1 if max_y > 1 else 0
                    stdscr.addstr(safe_y, safe_x, instructions)
                
                # Refresh the screen
                stdscr.refresh()
                
                # Check for input
                key = stdscr.getch()
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    # Force refresh data
                    self.fetch_data()
        
        finally:
            # Clean up
            self.stop_event.set()
            update_thread.join(timeout=2)

def main():
    parser = argparse.ArgumentParser(
        description="Real-time earnings trades monitor with enhanced terminal graphics."
    )
    parser.add_argument(
        '--refresh', '-r',
        help='Refresh rate in seconds (default: 300)',
        type=int,
        default=300
    )
    parser.add_argument(
        '--no-all-sources',
        help='Disable using all earnings data sources',
        action='store_true'
    )
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_dir="logs")
    logger = logging.getLogger(__name__)
    
    # Start the monitor
    monitor = TradeMonitor(
        refresh_rate=args.refresh,
        use_all_sources=not args.no_all_sources
    )
    
    try:
        # Initialize and run curses application
        curses.wrapper(monitor.run)
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    except Exception as e:
        logger.error(f"Error running monitor: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())