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
import io

# Import modules from scanner
from core.scanner import EarningsScanner
from utils.logging_utils import setup_logging

# Import UI components
from ui import (
    draw_btop_box,
    calculate_layout,
    draw_ticker_box,
    draw_trade_visualizer,
    handle_mouse_event
)

class TradeMonitor:
    def __init__(self, refresh_rate=300, use_all_sources=False):
        self.refresh_rate = refresh_rate  # seconds between updates
        self.use_all_sources = use_all_sources
        self.scanner = EarningsScanner()
        self.tier1_tickers = []
        self.tier2_tickers = []
        self.stock_metrics = {}
        self.last_update = None
        self.stop_event = threading.Event()
        self.logger = logging.getLogger(__name__)
        
        # Define which boxes are visible (BTOP-like toggles)
        self.visible_boxes = {
            '1': True,  # Status box
            '2': True,  # Tier 1 trades
            '3': True,  # Tier 2 trades
            '4': True,  # Trade visualizer
        }
        
        # Default height ratios for boxes
        self.height_ratios = {
            'status': 0.1,     # 10% for status
            'visualizer': 0.3, # 30% for trade visualizer
            'trades': 0.6,     # 60% for trades panels
        }
        
        # Selected ticker for trade visualization
        self.selected_ticker = None
        self.trade_data = None
        
    def fetch_data(self):
        """Fetch latest scanner data"""
        try:
            self.logger.info("Fetching scanner data...")
            
            # Capture scanner output to prevent it from messing up the UI
            with io.StringIO() as capture_buffer:
                original_stdout = sys.stdout
                original_stderr = sys.stderr
                
                # Only redirect if not already redirected elsewhere
                if sys.stdout == sys.__stdout__:
                    sys.stdout = capture_buffer
                    sys.stderr = capture_buffer
                    local_redirect = True
                else:
                    local_redirect = False
                
                try:
                    # Get scanner data
                    recommended, _, stock_metrics = self.scanner.scan_earnings(
                        all_sources=self.use_all_sources
                    )
                    
                    # Sort tickers by tier
                    self.tier1_tickers = [t for t in recommended if stock_metrics[t].get('tier', 1) == 1]
                    self.tier2_tickers = [t for t in recommended if stock_metrics[t].get('tier', 1) == 2]
                    self.stock_metrics = stock_metrics
                    
                finally:
                    # Always restore original stdout/stderr if we changed them locally
                    if local_redirect:
                        sys.stdout = original_stdout
                        sys.stderr = original_stderr
                        
                        # Log any captured output at debug level
                        captured_output = capture_buffer.getvalue()
                        if captured_output.strip():
                            self.logger.debug(f"Scanner output: {captured_output}")
            
            self.last_update = datetime.now()
            self.logger.info(f"Data updated. Found {len(self.tier1_tickers)} Tier 1 and {len(self.tier2_tickers)} Tier 2 trades")
            
        except Exception as e:
            self.logger.error(f"Error fetching data: {str(e)}")
    
    def format_time_remaining(self):
        """Format time until next refresh"""
        if not self.last_update:
            return "Updating... (this may take a while)"
        
        next_update = self.last_update + timedelta(seconds=self.refresh_rate)
        remaining = next_update - datetime.now()
        
        if remaining.total_seconds() <= 0:
            return "Updating..."
        
        minutes, seconds = divmod(int(remaining.total_seconds()), 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def update_countdown(self, stdscr, max_width):
        """Update just the countdown timer without redrawing the whole screen"""
        status_text = f"Last Update: {self.last_update.strftime('%Y-%m-%d %H:%M:%S') if self.last_update else 'Never'} | Next Update: {self.format_time_remaining()}"
        
        # Clear the previous status text by writing spaces
        blank_text = " " * len(status_text)
        try:
            # Center in the status panel
            stdscr.addstr(1, 1 + (max_width - len(blank_text)) // 2, blank_text)
            stdscr.addstr(1, 1 + (max_width - len(status_text)) // 2, status_text, curses.color_pair(10) | curses.A_BOLD)
        except curses.error:
            pass  # Handle potential out-of-bounds error

    def update_data_thread(self):
        """Background thread to update data periodically"""
        while not self.stop_event.is_set():
            self.fetch_data()
            # Sleep in small increments to allow clean shutdown
            for _ in range(self.refresh_rate):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

    def fetch_trade_data(self, ticker):
        """Fetch iron fly trade data for a specific ticker"""
        try:
            self.logger.info(f"Fetching iron fly data for {ticker}")
            
            # Use the same capture approach for trade data
            with io.StringIO() as capture_buffer:
                original_stdout = sys.stdout
                original_stderr = sys.stderr
                
                # Only redirect if not already redirected elsewhere
                if sys.stdout == sys.__stdout__:
                    sys.stdout = capture_buffer
                    sys.stderr = capture_buffer
                    local_redirect = True
                else:
                    local_redirect = False
                
                try:
                    # Fetch the trade data
                    trade_data = self.scanner.calculate_iron_fly_strikes(ticker)
                    self.trade_data = trade_data
                finally:
                    # Always restore original stdout/stderr if we changed them locally
                    if local_redirect:
                        sys.stdout = original_stdout
                        sys.stderr = original_stderr
                        
                        # Log any captured output at debug level
                        captured = capture_buffer.getvalue()
                        if captured.strip():
                            self.logger.debug(f"Trade data output: {captured}")
            
            return trade_data
        except Exception as e:
            self.logger.error(f"Error fetching iron fly data: {str(e)}")
            return {"error": str(e)}

    def run(self, stdscr):
        """Main display function using curses"""
        # Set up curses
        curses.start_color()
        curses.use_default_colors()
        curses.curs_set(0)  # Hide cursor
        stdscr.clear()
        stdscr.timeout(1000)  # Set getch timeout to 1 second for responsive UI
        
        # Define BTOP-like color scheme with TTY theme colors
        curses.init_pair(1, 2, -1)     # Green for Tier 1 (TTY green)
        curses.init_pair(2, 3, -1)     # Yellow for Tier 2 (TTY yellow)
        curses.init_pair(3, 1, -1)     # Red for errors (TTY red)
        curses.init_pair(4, 6, -1)     # Cyan for headers (TTY cyan)
        curses.init_pair(5, 7, -1)     # White for text (TTY white)
        curses.init_pair(6, 8, -1)     # Gray for borders (TTY dark gray)
        curses.init_pair(7, 5, -1)     # Magenta for accents (TTY magenta)
        curses.init_pair(8, 8, 0)      # Dark gray for shadows (TTY dark gray bg)
        curses.init_pair(9, 0, 0)      # Black for background fill (TTY black bg)
        curses.init_pair(10, 7, -1)    # Light gray for data text (TTY white)
        curses.init_pair(11, 4, -1)    # Blue for instructions (TTY blue)
        
        GREEN = curses.color_pair(1)
        YELLOW = curses.color_pair(2)
        RED = curses.color_pair(3)
        CYAN = curses.color_pair(4)
        WHITE = curses.color_pair(5)
        BORDER = curses.color_pair(6)
        MAGENTA = curses.color_pair(7)
        SHADOW = curses.color_pair(8)
        FILL = curses.color_pair(9)
        TEXT = curses.color_pair(10)
        BLUE = curses.color_pair(11)
        
        # Start data update thread
        update_thread = threading.Thread(target=self.update_data_thread)
        update_thread.daemon = True
        update_thread.start()
        
        # Track window size to detect resizes
        last_size = stdscr.getmaxyx()
        # Track if full redraw is needed
        full_redraw_needed = True
        # Track when data was last fetched to know when to redraw
        last_data_update = self.last_update
        
        try:
            while True:
                # Get terminal size
                max_y, max_x = stdscr.getmaxyx()
                
                # Check if terminal was resized or if this is first run
                if last_size != (max_y, max_x):
                    full_redraw_needed = True
                    last_size = (max_y, max_x)
                
                # Check if data was updated
                if last_data_update != self.last_update:
                    full_redraw_needed = True
                    last_data_update = self.last_update
                
                # Check for minimum size
                if max_y < 20 or max_x < 80:
                    stdscr.clear()
                    stdscr.addstr(0, 0, "Terminal too small. Please resize to at least 80x20.", curses.color_pair(3))
                    stdscr.refresh()
                    time.sleep(1)
                    continue
                
                # Do a full redraw if needed
                if full_redraw_needed:
                    # Clear screen with background color
                    stdscr.clear()
                    
                    # Calculate layout based on which boxes are visible
                    layout = calculate_layout(max_y, max_x, self.visible_boxes, self.height_ratios)
                    
                    # Draw status box if visible
                    if layout['status']['visible']:
                        status = layout['status']
                        draw_btop_box(
                            stdscr, 
                            status['y'], 
                            status['x'], 
                            status['height'], 
                            status['width'], 
                            "status", 
                            CYAN, 
                            box_num="1"
                        )
                        
                        # Update status display (progress bar or regular info)
                        self.update_countdown(stdscr, status['width'])
                    
                    # Draw trade visualizer if visible
                    if layout['visualizer']['visible']:
                        self.trade_data = draw_trade_visualizer(
                            stdscr, 
                            layout['visualizer'], 
                            self.selected_ticker, 
                            self.trade_data, 
                            self.stock_metrics, 
                            self.scanner
                        )
                    
                    # Draw Tier 1 container if visible
                    trades = layout['trades']
                    if trades['tier1']['visible']:
                        draw_btop_box(
                            stdscr, 
                            trades['y'], 
                            trades['tier1']['x'], 
                            trades['height'], 
                            trades['tier1']['width'], 
                            "tier 1 trades", 
                            GREEN, 
                            box_num="2"
                        )
                        
                        # Populate Tier 1 tickers
                        if self.tier1_tickers:
                            # Calculate columns based on available width
                            ticker_width = 38  # Width of each ticker box (36 + 2 padding)
                            columns = max(1, trades['tier1']['width'] // ticker_width)
                            
                            # Setup initial positions
                            column_positions = []
                            for col in range(columns):
                                column_positions.append({
                                    'x': trades['tier1']['x'] + 1 + (col * ticker_width),
                                    'y': trades['y'] + 1,
                                    'next_y': trades['y'] + 1
                                })
                            
                            # Place tickers in columns
                            for i, ticker in enumerate(self.tier1_tickers):
                                # Choose column (round-robin)
                                col_idx = i % columns
                                col = column_positions[col_idx]
                                
                                # Skip if we're out of vertical space
                                if col['next_y'] >= trades['y'] + trades['height'] - 2:
                                    continue
                                
                                metrics = self.stock_metrics[ticker]
                                ticker_height, _ = draw_ticker_box(
                                    stdscr, 
                                    col['next_y'], 
                                    col['x'], 
                                    ticker, 
                                    metrics, 
                                    GREEN, 
                                    max_y, 
                                    max_x, 
                                    ticker_width - 2
                                )
                                
                                # Update next y position for this column
                                col['next_y'] += ticker_height
                        else:
                            message = "No Tier 1 trades found"
                            stdscr.addstr(
                                trades['y'] + trades['height'] // 2, 
                                trades['tier1']['x'] + (trades['tier1']['width'] - len(message)) // 2, 
                                message, 
                                TEXT
                            )
                    
                    # Draw Tier 2 container if visible
                    if trades['tier2']['visible']:
                        draw_btop_box(
                            stdscr, 
                            trades['y'], 
                            trades['tier2']['x'], 
                            trades['height'], 
                            trades['tier2']['width'], 
                            "tier 2 trades", 
                            YELLOW, 
                            box_num="3"
                        )
                        
                        # Populate Tier 2 tickers
                        if self.tier2_tickers:
                            # Calculate columns based on available width
                            ticker_width = 38  # Width of each ticker box (36 + 2 padding)
                            columns = max(1, trades['tier2']['width'] // ticker_width)
                            
                            # Setup initial positions
                            column_positions = []
                            for col in range(columns):
                                column_positions.append({
                                    'x': trades['tier2']['x'] + 1 + (col * ticker_width),
                                    'y': trades['y'] + 1,
                                    'next_y': trades['y'] + 1
                                })
                            
                            # Place tickers in columns
                            for i, ticker in enumerate(self.tier2_tickers):
                                # Choose column (round-robin)
                                col_idx = i % columns
                                col = column_positions[col_idx]
                                
                                # Skip if we're out of vertical space
                                if col['next_y'] >= trades['y'] + trades['height'] - 2:
                                    continue
                                
                                metrics = self.stock_metrics[ticker]
                                ticker_height, _ = draw_ticker_box(
                                    stdscr, 
                                    col['next_y'], 
                                    col['x'], 
                                    ticker, 
                                    metrics, 
                                    YELLOW, 
                                    max_y, 
                                    max_x, 
                                    ticker_width - 2
                                )
                                
                                # Update next y position for this column
                                col['next_y'] += ticker_height
                        else:
                            message = "No Tier 2 trades found"
                            stdscr.addstr(
                                trades['y'] + trades['height'] // 2, 
                                trades['tier2']['x'] + (trades['tier2']['width'] - len(message)) // 2, 
                                message, 
                                TEXT
                            )
                    
                    # Reset the flag
                    full_redraw_needed = False
                else:
                    # Just update the countdown timer if status box is visible
                    if self.visible_boxes.get('1', True):
                        # Get the current layout for accurate positioning
                        layout = calculate_layout(max_y, max_x, self.visible_boxes, self.height_ratios)
                        status = layout['status']
                        
                        # Update status display with progress bar if active
                        self.update_countdown(stdscr, status['width'])
                
                # Refresh the screen
                stdscr.refresh()
                
                # Check for input
                key = stdscr.getch()
                if key == ord('q') or key == ord('Q'):
                    break
                elif key == ord('r') or key == ord('R'):
                    # Force refresh data
                    self.fetch_data()
                    full_redraw_needed = True
                elif key == curses.KEY_RESIZE:
                    # Terminal was resized
                    full_redraw_needed = True
                # Handle toggling boxes with number keys (1-4)
                elif key in [ord('1'), ord('2'), ord('3'), ord('4')]:
                    box_key = chr(key)
                    self.visible_boxes[box_key] = not self.visible_boxes[box_key]
                    full_redraw_needed = True
                # Handle mouse clicks
                elif key == curses.KEY_MOUSE:
                    try:
                        event = curses.getmouse()
                        
                        # Calculate layout for mouse position detection
                        layout = calculate_layout(max_y, max_x, self.visible_boxes, self.height_ratios)
                        
                        # Process the mouse event using our utility function
                        selected_ticker, tier = handle_mouse_event(
                            event, 
                            max_y, 
                            max_x, 
                            layout,
                            self.tier1_tickers,
                            self.tier2_tickers,
                            self.stock_metrics
                        )
                        
                        # Update the selected ticker if one was clicked
                        if selected_ticker:
                            self.selected_ticker = selected_ticker
                            self.trade_data = None  # Reset trade data to force refresh
                            full_redraw_needed = True
                            
                    except Exception as e:
                        # Do not display errors from mouse movements
                        # Only log non-normal mouse event errors with debug level
                        if str(e) != 'getmouse() returned ERR':
                            self.logger.debug(f"Mouse event: {e}")
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
    log_dir = "logs"
    setup_logging(log_dir=log_dir)
    logger = logging.getLogger(__name__)
    
    # Start the monitor
    monitor = TradeMonitor(
        refresh_rate=args.refresh,
        use_all_sources=not args.no_all_sources
    )
    
    try:
        # Initialize curses with mouse support
        curses.wrapper(lambda stdscr: (stdscr.keypad(1), curses.mousemask(curses.ALL_MOUSE_EVENTS), monitor.run(stdscr)))
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    except Exception as e:
        logger.error(f"Error running monitor: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())