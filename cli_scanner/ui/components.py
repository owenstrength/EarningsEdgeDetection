"""
Basic UI components like boxes and labels.
"""

import curses

def draw_btop_box(stdscr, y, x, h, w, title="", color=0, box_num=None):
    """Draw a BTOP-style box with rounded corners and optional box number"""
    max_y, max_x = stdscr.getmaxyx()
    
    # Box drawing characters with ASCII fallbacks
    try:
        # Try fancy box characters first
        tl, tr = '╭', '╮'  # top left, top right 
        bl, br = '╰', '╯'  # bottom left, bottom right
        h_line, v_line = '─', '│'  # horizontal, vertical
        
    except curses.error:
        # Fall back to ASCII characters
        tl, tr = '+', '+'
        bl, br = '+', '+'
        h_line, v_line = '-', '|'
        
    # Draw the rounded corners and borders with the specified color
    if y < max_y and x <= max_x:
        try:
            stdscr.addstr(y, x, tl, color)
        except curses.error:
            pass
    
    if y < max_y and x + w - 1 < max_x:
        try:
            stdscr.addstr(y, x + w - 1, tr, color)
        except curses.error:
            pass
    
    if y + h - 1 < max_y and x < max_x:
        try:
            stdscr.addstr(y + h - 1, x, bl, color)
        except curses.error:
            pass
    
    if y + h - 1 < max_y and x + w - 1 < max_x:
        try:
            stdscr.addstr(y + h - 1, x + w - 1, br, color)
        except curses.error:
            pass
    
    # Draw horizontal borders
    for j in range(x + 1, x + w - 1):
        if j < max_x:
            if y < max_y:
                try:
                    stdscr.addstr(y, j, h_line, color)
                except curses.error:
                    pass
            if y + h - 1 < max_y:
                try:
                    stdscr.addstr(y + h - 1, j, h_line, color)
                except curses.error:
                    pass
    
    # Draw vertical borders
    for i in range(y + 1, y + h - 1):
        if i < max_y:
            if x < max_x:
                try:
                    stdscr.addstr(i, x, v_line, color)
                except curses.error:
                    pass
            if x + w - 1 < max_x:
                try:
                    stdscr.addstr(i, x + w - 1, v_line, color)
                except curses.error:
                    pass
    
    # Add the title if provided
    if title:
        # If box_num provided, add to title like BTOP does
        if box_num:
            superscript_map = {
                '0': '⁰',
                '1': '¹',
                '2': '²',
                '3': '³',
                '4': '⁴',
                '5': '⁵',
                '6': '⁶',
                '7': '⁷',
                '8': '⁸',
                '9': '⁹'
            }
            superscript_box = ''.join(superscript_map.get(ch, ch) for ch in box_num)
            title_text = f" {superscript_box}{title} "
        else:
            title_text = f" {title} "
            
        if len(title_text) < w - 4 and y < max_y and x + 2 < max_x:
            try:
                stdscr.addstr(y, x + 2, title_text, color | curses.A_BOLD)
            except curses.error:
                pass
