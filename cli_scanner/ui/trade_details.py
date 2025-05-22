"""
Trade details display components.
"""

import curses
import logging
from .components import draw_btop_box
from .trade_graph import draw_pnl_graph

logger = logging.getLogger(__name__)

def draw_trade_visualizer(stdscr, box_data, selected_ticker, trade_data, stock_metrics, scanner):
    """Draw the trade visualizer box with iron fly visualization"""
    # Draw the container box
    draw_btop_box(
        stdscr, 
        box_data['y'], 
        box_data['x'], 
        box_data['height'], 
        box_data['width'], 
        "trade visualizer", 
        curses.color_pair(4),  # Cyan color for header
        box_num="4"
    )
    
    # If no ticker is selected, show a message
    if not selected_ticker:
        msg = "Select a ticker to view iron fly trade details"
        try:
            stdscr.addstr(
                box_data['y'] + box_data['height'] // 2,
                box_data['x'] + (box_data['width'] - len(msg)) // 2,
                msg,
                curses.color_pair(10)
            )
        except curses.error:
            pass
        return None
    
    # If we have a selected ticker but no trade data, fetch it
    if not trade_data:
        try:
            logger.info(f"Fetching iron fly data for {selected_ticker}")
            trade_data = scanner.calculate_iron_fly_strikes(selected_ticker)
        except Exception as e:
            logger.error(f"Error fetching iron fly data: {str(e)}")
            trade_data = {"error": str(e)}
    
    # If fetch failed or returned an error
    if not trade_data or "error" in trade_data:
        error_msg = f"Error calculating iron fly for {selected_ticker}: {trade_data.get('error', 'Unknown error')}" if trade_data else "Could not fetch trade data"
        try:
            stdscr.addstr(
                box_data['y'] + box_data['height'] // 2,
                box_data['x'] + (box_data['width'] - len(error_msg)) // 2,
                error_msg,
                curses.color_pair(3)  # Red for errors
            )
        except curses.error:
            pass
        return trade_data
    
    # Draw the trade visualization
    y_pos = box_data['y'] + 1
    x_pos = box_data['x'] + 2
    width = box_data['width'] - 4
    
    # Show ticker and expiration
    ticker_header = f"{selected_ticker} Iron Fly - Exp: {trade_data.get('expiration', 'N/A')}"
    try:
        stdscr.addstr(y_pos, x_pos, ticker_header, curses.color_pair(5) | curses.A_BOLD)
    except curses.error:
        pass
    
    y_pos += 1
    
    # Calculate space available for graph and data
    graph_height = min(box_data['height'] - 4, 10)  # Max 10 lines for graph
    graph_width = width // 2 - 4  # Half of the available width minus padding
    
    # Get iron fly parameters for graph
    try:
        current_price = float(stock_metrics[selected_ticker]['price'])
        long_put_strike = float(trade_data.get("long_put_strike", 0))
        short_put_strike = float(trade_data.get("short_put_strike", 0))
        short_call_strike = float(trade_data.get("short_call_strike", 0))
        long_call_strike = float(trade_data.get("long_call_strike", 0))
        net_credit = float(trade_data.get("net_credit", 0))
        max_profit = float(trade_data.get("max_profit", 0))
        max_loss = float(trade_data.get("max_risk", 0))
        
        # Draw the PnL graph
        draw_pnl_graph(
            stdscr,
            y_pos,
            x_pos,
            graph_height,
            graph_width,
            current_price,
            long_put_strike,
            short_put_strike,
            short_call_strike,
            long_call_strike,
            net_credit,
            max_profit,
            max_loss
        )
        
        # Position for trade details (to the right of the graph)
        details_x = x_pos + graph_width + 4
        details_y = y_pos
        
        # Show positions with appropriate colors
        positions = [
            {
                "name": "Long Put",
                "strike": trade_data.get("long_put_strike", "N/A"),
                "premium": trade_data.get("long_put_premium", "N/A"),
                "color": curses.color_pair(1)  # Green for long
            },
            {
                "name": "Short Put",
                "strike": trade_data.get("short_put_strike", "N/A"),
                "premium": trade_data.get("short_put_premium", "N/A"),
                "color": curses.color_pair(3)  # Red for short
            },
            {
                "name": "Short Call",
                "strike": trade_data.get("short_call_strike", "N/A"),
                "premium": trade_data.get("short_call_premium", "N/A"),
                "color": curses.color_pair(3)  # Red for short
            },
            {
                "name": "Long Call",
                "strike": trade_data.get("long_call_strike", "N/A"),
                "premium": trade_data.get("long_call_premium", "N/A"),
                "color": curses.color_pair(1)  # Green for long
            }
        ]
        
        # Display the positions next to the graph
        for position in positions:
            if details_y < box_data['y'] + box_data['height'] - 1:
                position_text = f"{position['name']}: Strike ${position['strike']}, Premium ${position['premium']}"
                try:
                    stdscr.addstr(details_y, details_x, position_text, position["color"])
                except curses.error:
                    pass
                details_y += 1
        
        details_y += 1
        
        # Show trade metrics
        metrics = [
            f"Net Credit: ${trade_data.get('net_credit', 'N/A')}",
            f"Max Profit: ${trade_data.get('max_profit', 'N/A')}",
            f"Max Risk: ${trade_data.get('max_risk', 'N/A')}",
            f"Break-even: ${trade_data.get('lower_breakeven', 'N/A')} - ${trade_data.get('upper_breakeven', 'N/A')}",
            f"Risk:Reward: {trade_data.get('risk_reward_ratio', 'N/A')}:1"
        ]
        
        for metric in metrics:
            if details_y < box_data['y'] + box_data['height'] - 1:
                try:
                    stdscr.addstr(details_y, details_x, metric, curses.color_pair(10))
                except curses.error:
                    pass
                details_y += 1
                
    except Exception as e:
        # Fallback to old display method if there's an error with the graph
        logger.error(f"Error drawing PnL graph: {str(e)}")
        
        y_pos += 1
        
        # Show positions with appropriate colors
        positions = [
            {
                "name": "Long Put",
                "strike": trade_data.get("long_put_strike", "N/A"),
                "premium": trade_data.get("long_put_premium", "N/A"),
                "color": curses.color_pair(1)  # Green for long
            },
            {
                "name": "Short Put",
                "strike": trade_data.get("short_put_strike", "N/A"),
                "premium": trade_data.get("short_put_premium", "N/A"),
                "color": curses.color_pair(3)  # Red for short
            },
            {
                "name": "Short Call",
                "strike": trade_data.get("short_call_strike", "N/A"),
                "premium": trade_data.get("short_call_premium", "N/A"),
                "color": curses.color_pair(3)  # Red for short
            },
            {
                "name": "Long Call",
                "strike": trade_data.get("long_call_strike", "N/A"),
                "premium": trade_data.get("long_call_premium", "N/A"),
                "color": curses.color_pair(1)  # Green for long
            }
        ]
        
        # Display the positions
        for position in positions:
            if y_pos < box_data['y'] + box_data['height'] - 1:
                position_text = f"{position['name']}: Strike ${position['strike']}, Premium ${position['premium']}"
                try:
                    stdscr.addstr(y_pos, x_pos, position_text, position["color"])
                except curses.error:
                    pass
                y_pos += 1
        
        y_pos += 1
        
        # Show trade metrics
        metrics = [
            f"Net Credit: ${trade_data.get('net_credit', 'N/A')}",
            f"Max Profit: ${trade_data.get('max_profit', 'N/A')}",
            f"Max Risk: ${trade_data.get('max_risk', 'N/A')}",
            f"Break-even: ${trade_data.get('lower_breakeven', 'N/A')} - ${trade_data.get('upper_breakeven', 'N/A')}",
            f"Risk:Reward: {trade_data.get('risk_reward_ratio', 'N/A')}:1"
        ]
        
        for metric in metrics:
            if y_pos < box_data['y'] + box_data['height'] - 1:
                try:
                    stdscr.addstr(y_pos, x_pos, metric, curses.color_pair(10))
                except curses.error:
                    pass
                y_pos += 1
    
    return trade_data
