"""
Ticker display components for the trade monitor.
"""

import curses
from .components import draw_btop_box

def draw_ticker_box(stdscr, y, x, ticker, metrics, color, max_y, max_x, width=40):
    """Draw a box containing ticker information in BTOP style"""
    # Use a narrower width for ticker boxes (28 instead of 40)
    ticker_width = 36
    
    height = 5
    if 'float_ratio' in metrics:
        height += 1
    if 'expected_move_pct' in metrics:
        height += 1
    
    # Draw the main ticker box
    draw_btop_box(stdscr, y, x, height, ticker_width, ticker, color)
    
    # Display metrics with padding - reduce padding
    y_pos = y + 1
    
    if y_pos < max_y - 1:
        price_vol = f"Price: ${metrics['price']:.2f} | Vol: {metrics['volume']:,.0f}"
        # Truncate if too long for the box
        if len(price_vol) > ticker_width - 2:
            price_vol = price_vol[:ticker_width - 5] + "..."
        stdscr.addstr(y_pos, x + 1, price_vol, curses.color_pair(10))
    
    y_pos += 1
    if y_pos < max_y - 1:
        iv_rv = f"IV/RV: {metrics['iv_rv_ratio']:.2f} | Term: {metrics['term_structure']:.3f}"
        if len(iv_rv) > ticker_width - 2:
            iv_rv = iv_rv[:ticker_width - 5] + "..."
        stdscr.addstr(y_pos, x + 1, iv_rv, curses.color_pair(10))
    
    y_pos += 1
    if y_pos < max_y - 1:
        winrate = f"Winrate: {metrics['win_rate']:.1f}% over {metrics['win_quarters']} earnings"
        if len(winrate) > ticker_width - 2:
            winrate = winrate[:ticker_width - 5] + "..."
        stdscr.addstr(y_pos, x + 1, winrate, curses.color_pair(10))
    
    # Add expected move information - more compact
    y_pos += 1
    if y_pos < max_y - 1 and 'expected_move_pct' in metrics:
        current_price = metrics['price']
        em_pct = metrics['expected_move_pct']
        em_dollars = metrics.get('expected_move_dollars', current_price * em_pct / 100)
        
        # Calculate expected price range
        lower_price = current_price - em_dollars
        upper_price = current_price + em_dollars
        
        em_info = f"EM: {em_pct:.1f}% (${lower_price:.2f}-${upper_price:.2f})"
        if len(em_info) > ticker_width - 2:
            em_info = em_info[:ticker_width - 5] + "..."
        stdscr.addstr(y_pos, x + 1, em_info, curses.color_pair(10))
    
    # Return the height of this ticker box for positioning the next one
    # and the width for multi-column layout
    return height, ticker_width
