from PIL import Image, ImageDraw, ImageFont
import io
import os

# Create directory for PNG logos if it doesn't exist
if not os.path.exists('static/png_logos'):
    os.makedirs('static/png_logos')

# Function to create a simple SP logo with various styles
def create_logo(style_num, size=(200, 200), bg_color=(0, 0, 0), text_color=(255, 255, 255)):
    # Create a new image with transparency
    img = Image.new('RGBA', size, bg_color + (0,))  # Transparent background
    draw = ImageDraw.Draw(img)
    
    # Get center coordinates
    width, height = size
    center_x, center_y = width // 2, height // 2
    
    # Different styles for different logos
    if style_num == 1:
        # Style 1: Circle with SP text
        # Draw outer circle
        draw.ellipse((10, 10, width-10, height-10), outline=text_color, width=3)
        # Draw inner circle
        draw.ellipse((20, 20, width-20, height-20), outline=text_color, width=1)
        
        # Draw text
        try:
            font = ImageFont.truetype("Arial.ttf", 80)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        text_width = draw.textlength("SP", font=font)
        text_x = center_x - text_width // 2
        text_y = center_y - 50  # Adjust vertical position
        draw.text((text_x, text_y), "SP", fill=text_color, font=font)
        
    elif style_num == 2:
        # Style 2: Square with SP text
        # Draw square
        draw.rectangle((20, 20, width-20, height-20), outline=text_color, width=3)
        
        # Draw text
        try:
            font = ImageFont.truetype("Arial.ttf", 80)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        text_width = draw.textlength("SP", font=font)
        text_x = center_x - text_width // 2
        text_y = center_y - 50  # Adjust vertical position
        draw.text((text_x, text_y), "SP", fill=text_color, font=font)
        
    elif style_num == 3:
        # Style 3: Hexagon with SP text
        # Draw hexagon
        hex_radius = min(width, height) // 2 - 20
        hex_points = []
        for i in range(6):
            angle_deg = 60 * i - 30
            angle_rad = math.pi / 180 * angle_deg
            x = center_x + hex_radius * math.cos(angle_rad)
            y = center_y + hex_radius * math.sin(angle_rad)
            hex_points.append((x, y))
        
        draw.line(hex_points + [hex_points[0]], fill=text_color, width=3)
        
        # Draw text
        try:
            font = ImageFont.truetype("Arial.ttf", 80)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        text_width = draw.textlength("SP", font=font)
        text_x = center_x - text_width // 2
        text_y = center_y - 50  # Adjust vertical position
        draw.text((text_x, text_y), "SP", fill=text_color, font=font)
        
    elif style_num == 4:
        # Style 4: Minimal with just large SP text
        try:
            font = ImageFont.truetype("Arial.ttf", 120)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        text_width = draw.textlength("SP", font=font)
        text_x = center_x - text_width // 2
        text_y = center_y - 70  # Adjust vertical position
        draw.text((text_x, text_y), "SP", fill=text_color, font=font)
        
    elif style_num == 5:
        # Style 5: S and P combined
        # Draw stylized "S"
        s_points = [(center_x - 40, center_y - 30), 
                    (center_x - 20, center_y - 50),
                    (center_x, center_y - 30),
                    (center_x, center_y),
                    (center_x - 20, center_y + 20),
                    (center_x, center_y + 50)]
        
        # Draw stylized "P"
        p_x_start = center_x + 10
        p_points = [(p_x_start, center_y - 50),
                    (p_x_start, center_y + 50),
                    (p_x_start, center_y - 50),
                    (p_x_start + 40, center_y - 30),
                    (p_x_start + 40, center_y),
                    (p_x_start, center_y)]
        
        draw.line(s_points, fill=text_color, width=5)
        draw.line(p_points, fill=text_color, width=5)
    
    # Save the image
    img.save(f'static/png_logos/logo_option{style_num}.png')
    print(f"Created logo_option{style_num}.png")

# Create 5 different logo styles
import math  # Import for hexagon calculation

for i in range(1, 6):
    create_logo(i)

print("All PNG logos created successfully!")