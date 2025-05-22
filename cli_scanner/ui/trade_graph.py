"""
Graph rendering components for visualizing iron fly P&L.
"""

import curses
import logging

logger = logging.getLogger(__name__)

def calculate_iron_fly_pnl(price, short_put_strike, short_call_strike, long_put_strike, long_call_strike, net_credit):
    """Calculate the P&L of an iron fly at a given price"""
    try:
        # Validate inputs to prevent calculation errors
        if not all(isinstance(x, (int, float)) for x in 
                [price, short_put_strike, short_call_strike, long_put_strike, long_call_strike, net_credit]):
            return 0
        
        if price <= 0 or short_put_strike <= 0 or short_call_strike <= 0 or long_put_strike <= 0 or long_call_strike <= 0:
            return 0
        
        # Ensure strikes are in the correct order
        if not (long_put_strike <= short_put_strike <= short_call_strike <= long_call_strike):
            # Attempt to correct the order if possible
            strikes = sorted([long_put_strike, short_put_strike, short_call_strike, long_call_strike])
            long_put_strike, short_put_strike, short_call_strike, long_call_strike = strikes
        
        # Calculate width of spreads
        put_width = short_put_strike - long_put_strike
        call_width = long_call_strike - short_call_strike
        
        # For an iron fly:
        # - Max profit at price = short strikes (typically ATM)
        # - Loss increases as price moves away from short strikes
        # - Loss capped by the long strikes
        
        if price <= long_put_strike:
            # Below the long put strike - max loss
            pnl = net_credit - put_width
        elif price < short_put_strike:
            # Between long put and short put - partial loss
            pnl = net_credit - (short_put_strike - price)
        elif price <= short_call_strike:
            # Between short put and short call - max profit
            pnl = net_credit
        elif price < long_call_strike:
            # Between short call and long call - partial loss
            pnl = net_credit - (price - short_call_strike)
        else:
            # Above the long call strike - max loss
            pnl = net_credit - call_width
        
        return pnl
    except Exception as e:
        logger.error(f"Error calculating PnL: {str(e)}")
        return 0

def draw_pnl_graph(stdscr, y, x, height, width, current_price, long_put_strike, 
                 short_put_strike, short_call_strike, long_call_strike, 
                 net_credit, max_profit, max_loss):
    """Draw a text-based P&L graph for the iron fly strategy"""
    try:
        # Draw the graph frame
        # Top border
        stdscr.addstr(y, x, "┌" + "─" * (width - 2) + "┐", curses.color_pair(6))
        
        # Side borders and fill content area
        for i in range(1, height - 1):
            stdscr.addstr(y + i, x, "│" + " " * (width - 2) + "│", curses.color_pair(6))
        
        # Bottom border
        stdscr.addstr(y + height - 1, x, "└" + "─" * (width - 2) + "┘", curses.color_pair(6))
        
        # Y-axis label (P&L)
        if x > 5:
            stdscr.addstr(y, x - 5, "P&L", curses.color_pair(10))
        
        # X-axis label (Price)
        x_label = "Price"
        stdscr.addstr(y + height - 1, x + (width // 2) - (len(x_label) // 2), x_label, curses.color_pair(10))
        
        # Calculate price range for x-axis - ensure we have a meaningful range
        min_price = min(long_put_strike, short_put_strike) * 0.9
        max_price = max(short_call_strike, long_call_strike) * 1.1
        
        # Safety check for price range
        if min_price >= max_price or min_price <= 0:
            min_price = current_price * 0.8
            max_price = current_price * 1.2
        
        price_range = max_price - min_price
        
        # Calculate P&L range for y-axis
        # Ensure we have valid values for min_pnl and max_pnl
        if max_loss <= 0:
            max_loss = 1.0  # Default non-zero value
        if max_profit <= 0:
            max_profit = net_credit  # Default to net credit
        
        min_pnl = -max_loss
        max_pnl = max_profit
        
        # Ensure we have a meaningful PnL range
        if min_pnl >= max_pnl:
            min_pnl = -net_credit * 2
            max_pnl = net_credit * 1.2
        
        pnl_range = max_pnl - min_pnl
        
        # Draw the zero P&L line
        if min_pnl < 0 < max_pnl:
            zero_y = int(y + height - 2 - ((0 - min_pnl) / pnl_range) * (height - 3))
            if y < zero_y < y + height - 1:
                try:
                    stdscr.addstr(zero_y, x + 1, "─" * (width - 2), curses.color_pair(6))
                except curses.error:
                    pass
        
        # Sample price points across the width of the graph
        num_samples = width - 4
        
        # Draw the price points on x-axis (vertical lines only, no labels)
        price_points = [
            long_put_strike,
            short_put_strike,
            current_price,
            short_call_strike,
            long_call_strike
        ]
        
        # Draw vertical lines at important price points
        for price in price_points:
            # Skip if price is outside our graph range
            if price < min_price or price > max_price:
                continue
            
            # Calculate x position
            try:
                x_pos = int(x + 1 + ((price - min_price) / price_range) * (width - 4))
            except (ZeroDivisionError, ValueError):
                continue
            
            # Ensure x_pos is within bounds
            if x < x_pos < x + width - 1:
                # Draw a vertical line at strike prices
                for i in range(1, height - 1):
                    try:
                        if price in [long_put_strike, long_call_strike]:
                            stdscr.addstr(y + i, x_pos, "│", curses.color_pair(1))  # Green for long positions
                        elif price in [short_put_strike, short_call_strike]:
                            stdscr.addstr(y + i, x_pos, "│", curses.color_pair(3))  # Red for short positions
                        else:
                            # Current price
                            stdscr.addstr(y + i, x_pos, "┊", curses.color_pair(5) | curses.A_BOLD)
                    except curses.error:
                        pass
        
        # Pre-calculate all PnL values for smoother drawing
        sample_prices = []
        sample_pnls = []
        
        for i in range(num_samples):
            price = min_price + (i / (num_samples - 1)) * price_range
            sample_prices.append(price)
            pnl = calculate_iron_fly_pnl(price, short_put_strike, short_call_strike, 
                                              long_put_strike, long_call_strike, net_credit)
            sample_pnls.append(pnl)
        
        # Draw the P&L curve
        prev_y_pnl = None
        for i, (price, pnl) in enumerate(zip(sample_prices, sample_pnls)):
            # Calculate the y position
            y_pnl = None
            try:
                y_pnl = int(y + height - 2 - ((pnl - min_pnl) / pnl_range) * (height - 3))
            except (ZeroDivisionError, ValueError):
                continue
            
            # Ensure y_pnl is within bounds
            if y < y_pnl < y + height - 1 and x + i + 2 < x + width - 1:
                try:
                    char = "•"
                    
                    # Draw a line to connect points if possible
                    if prev_y_pnl is not None and i > 0:
                        # If points are far apart, connect them with a line
                        if abs(prev_y_pnl - y_pnl) > 1:
                            step = 1 if prev_y_pnl < y_pnl else -1
                            for line_y in range(prev_y_pnl + step, y_pnl, step):
                                if y < line_y < y + height - 1:
                                    # Ensure we're not overwriting a vertical strike line
                                    if not any(abs(x + i + 1 - int(x + 1 + ((p - min_price) / price_range) * (width - 4))) < 2 for p in price_points):
                                        stdscr.addstr(line_y, x + i + 1, "┊", curses.color_pair(10))
                    
                    # Color based on profit/loss
                    if pnl > 0:
                        stdscr.addstr(y_pnl, x + i + 2, char, curses.color_pair(1))  # Green for profit
                    elif pnl < 0:
                        stdscr.addstr(y_pnl, x + i + 2, char, curses.color_pair(3))  # Red for loss
                    else:
                        stdscr.addstr(y_pnl, x + i + 2, char, curses.color_pair(10))  # White for breakeven
                    
                    prev_y_pnl = y_pnl
                except curses.error:
                    pass
        
        # Draw P&L values on y-axis (only at min, 0, and max)
        pnl_values = [min_pnl, 0, max_pnl]
        for pnl in pnl_values:
            # Skip if PnL is outside our visible range
            if pnl < min_pnl or pnl > max_pnl:
                continue
            
            try:
                y_pos = int(y + height - 2 - ((pnl - min_pnl) / pnl_range) * (height - 3))
            except (ZeroDivisionError, ValueError):
                continue
            
            if y < y_pos < y + height - 1 and x > 7:
                try:
                    pnl_label = f"${pnl:.2f}"
                    stdscr.addstr(y_pos, x - len(pnl_label) - 1, pnl_label, curses.color_pair(10))
                except curses.error:
                    pass
            
    except Exception as e:
        # Log any errors but don't crash
        logger.error(f"Error drawing graph: {str(e)}")
