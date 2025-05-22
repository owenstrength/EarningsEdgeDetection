"""
Layout calculations for the trade monitor UI.
"""

def calculate_layout(max_y, max_x, visible_boxes, height_ratios):
    """Calculate box dimensions based on which boxes are visible"""
    layout = {}
    
    # Start with fixed positions - reduce status box height
    status_y = 0  
    status_height = 3
    content_start_y = status_y + status_height if visible_boxes.get('1', True) else 0
    available_height = max_y - content_start_y # Reserve 1 line for instructions
    
    # Calculate how many content boxes are visible (excluding status)
    visible_content_boxes = 0
    trades_visible = False
    visualizer_visible = visible_boxes.get('4', True)
    
    if visible_boxes.get('2', True) or visible_boxes.get('3', True):
        visible_content_boxes += 1
        trades_visible = True
    
    # Set status box dimensions with reduced height
    layout['status'] = {
        'visible': visible_boxes.get('1', True),
        'y': status_y,
        'x': 0,  # Start from the leftmost edge
        'height': status_height,
        'width': max_x
    }
    
    # Calculate visualizer height if visible
    visualizer_height = 0
    if visualizer_visible:
        visualizer_height = int(available_height * height_ratios['visualizer'])
        visualizer_height = max(visualizer_height, 8)  # Minimum height for visualizer
    
    # Set trade visualizer dimensions
    layout['visualizer'] = {
        'visible': visualizer_visible,
        'y': content_start_y,
        'x': 0,
        'height': visualizer_height,
        'width': max_x
    }
    
    # Adjust start position for trades
    trades_start_y = content_start_y
    if visualizer_visible:
        trades_start_y += visualizer_height
    
    # Set trades area dimensions
    trades_height = 0
    if trades_visible:
        trades_height = available_height - visualizer_height if visualizer_visible else available_height
    
    # Make sure heights are at least 6 (minimum for a trades box)
    if trades_height > 0:
        trades_height = max(trades_height, 6)
    
    # Calculate column layout for trade boxes - reduce spacing
    col_width = (max_x) // 2  # Reduce the space between columns
    col1_x = 0  # Start from left edge
    col2_x = col_width  # Reduce gap between columns
    
    # Store trades area dimensions
    layout['trades'] = {
        'y': trades_start_y,
        'height': trades_height,
        'tier1': {
            'visible': visible_boxes.get('2', True),
            'x': col1_x,
            'width': col_width if visible_boxes.get('3', True) else max_x
        },
        'tier2': {
            'visible': visible_boxes.get('3', True),
            'x': col2_x,
            'width': col_width if visible_boxes.get('2', True) else max_x
        }
    }
    
    # If only one trade box is visible, it should span the full width
    if not visible_boxes.get('2', True) and visible_boxes.get('3', True):
        layout['trades']['tier2']['x'] = col1_x
        layout['trades']['tier2']['width'] = max_x
    elif visible_boxes.get('2', True) and not visible_boxes.get('3', True):
        layout['trades']['tier1']['width'] = max_x
    
    return layout
