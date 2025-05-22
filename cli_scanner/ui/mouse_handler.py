"""
Mouse event handling utilities.
"""

import curses
import logging

logger = logging.getLogger(__name__)

def handle_mouse_event(event, max_y, max_x, layout, tier1_tickers, tier2_tickers, stock_metrics):
    """
    Process a mouse click event and determine what was clicked.
    
    Args:
        event: Mouse event tuple from curses.getmouse()
        max_y, max_x: Terminal dimensions
        layout: UI layout dictionary
        tier1_tickers, tier2_tickers: Lists of ticker symbols
        stock_metrics: Dictionary of ticker metrics
        
    Returns:
        tuple: (selected_ticker, tier) or (None, None) if no ticker was clicked
    """
    try:
        # Unpack mouse event
        _, mx, my, _, _ = event
        
        selected_ticker = None
        tier = None
        
        # Check if click was in Tier 1 area
        tier1 = layout['trades']['tier1']
        if tier1['visible']:
            if (tier1['x'] <= mx < tier1['x'] + tier1['width'] and
                layout['trades']['y'] <= my < layout['trades']['y'] + layout['trades']['height']):
                
                # Calculate which ticker was clicked
                ticker_width = 38  # Width of each ticker box (36 + 2 padding)
                columns = max(1, tier1['width'] // ticker_width)
                
                # Determine which column was clicked
                column_idx = min((mx - tier1['x']) // ticker_width, columns - 1)
                
                # Calculate potential ticker positions for this column
                tickers_in_column = []
                y_pos = layout['trades']['y'] + 1
                
                for ticker in tier1_tickers:
                    if ticker not in stock_metrics:
                        continue
                        
                    # Only consider tickers that would be in this column
                    if len(tickers_in_column) % columns == column_idx:
                        metrics = stock_metrics[ticker]
                        height = 4  # Base height
                        if 'float_ratio' in metrics:
                            height += 1
                        if 'expected_move_pct' in metrics:
                            height += 1
                        
                        # Check if click is within this ticker's box
                        if y_pos <= my < y_pos + height:
                            selected_ticker = ticker
                            tier = 1
                            logger.info(f"Selected ticker: {ticker} from Tier 1")
                            break
                        
                        # Update y position for next ticker in this column
                        y_pos += height
                    
                    # Track tickers in all columns to determine column position
                    tickers_in_column.append(ticker)
        
        # Check if click was in Tier 2 area
        tier2 = layout['trades']['tier2']
        if tier2['visible'] and not selected_ticker:  # Only check if we haven't found a ticker yet
            if (tier2['x'] <= mx < tier2['x'] + tier2['width'] and
                layout['trades']['y'] <= my < layout['trades']['y'] + layout['trades']['height']):
                
                # Similar logic for tier 2
                ticker_width = 30  # Width of each ticker box (28 + 2 padding)
                columns = max(1, tier2['width'] // ticker_width)
                
                # Determine which column was clicked
                column_idx = min((mx - tier2['x']) // ticker_width, columns - 1)
                
                # Calculate potential ticker positions for this column
                tickers_in_column = []
                y_pos = layout['trades']['y'] + 1
                
                for ticker in tier2_tickers:
                    if ticker not in stock_metrics:
                        continue
                        
                    # Only consider tickers that would be in this column
                    if len(tickers_in_column) % columns == column_idx:
                        metrics = stock_metrics[ticker]
                        height = 4  # Base height
                        if 'float_ratio' in metrics:
                            height += 1
                        if 'expected_move_pct' in metrics:
                            height += 1
                        
                        # Check if click is within this ticker's box
                        if y_pos <= my < y_pos + height:
                            selected_ticker = ticker
                            tier = 2
                            logger.info(f"Selected ticker: {ticker} from Tier 2")
                            break
                        
                        # Update y position for next ticker in this column
                        y_pos += height
                    
                    # Track tickers in all columns to determine column position
                    tickers_in_column.append(ticker)
        
        return selected_ticker, tier
        
    except Exception as e:
        logger.debug(f"Error processing mouse event: {e}")
        return None, None
