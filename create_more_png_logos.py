from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os
import math
import random

# Create directory for PNG logos if it doesn't exist
if not os.path.exists('static/png_logos'):
    os.makedirs('static/png_logos')

# Function to create advanced SP logos with various styles
def create_advanced_logo(style_num, size=(200, 200)):
    # Create a new image with black background
    img = Image.new('RGBA', size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    
    # Get center coordinates
    width, height = size
    center_x, center_y = width // 2, height // 2
    
    # Default color is white
    white = (255, 255, 255, 255)
    
    if style_num == 6:
        # Style 6: Tech-inspired minimalist design
        # Draw outer border
        draw.rectangle((10, 10, width-10, height-10), outline=white, width=2)
        
        # Draw circuit-like patterns
        for i in range(10):
            x1 = random.randint(10, width-10)
            y1 = 10
            x2 = random.randint(10, width-10)
            y2 = height-10
            draw.line((x1, y1, x2, y2), fill=white, width=1)
        
        # Draw diagonal circuit lines
        for i in range(6):
            draw.line((10 + i*30, 10, width-10, 10 + i*30), fill=white, width=1)
            draw.line((10, 10 + i*30, 10 + i*30, height-10), fill=white, width=1)
        
        # Draw S and P letters with tech font style
        try:
            font = ImageFont.truetype("Arial.ttf", 80)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        draw.text((center_x-40, center_y-40), "S", fill=white, font=font)
        draw.text((center_x, center_y-40), "P", fill=white, font=font)
        
    elif style_num == 7:
        # Style 7: Circular target design
        # Draw concentric circles
        for i in range(5, 0, -1):
            radius = 20 + i*20
            draw.ellipse((center_x-radius, center_y-radius, 
                         center_x+radius, center_y+radius), 
                         outline=white, width=2)
        
        # Draw crosshair
        draw.line((center_x-90, center_y, center_x+90, center_y), fill=white, width=1)
        draw.line((center_x, center_y-90, center_x, center_y+90), fill=white, width=1)
        
        # Draw S and P letters
        try:
            font = ImageFont.truetype("Arial.ttf", 60)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        draw.text((center_x-35, center_y-35), "S", fill=white, font=font)
        draw.text((center_x, center_y-35), "P", fill=white, font=font)
        
    elif style_num == 8:
        # Style 8: Abstract geometric design
        # Draw triangles
        draw.polygon([(center_x, 20), (20, height-20), (width-20, height-20)], 
                      outline=white, width=2)
        
        # Draw square
        square_size = 120
        draw.rectangle((center_x-square_size//2, center_y-square_size//2, 
                       center_x+square_size//2, center_y+square_size//2), 
                       outline=white, width=2)
        
        # Draw circle
        circle_size = 80
        draw.ellipse((center_x-circle_size//2, center_y-circle_size//2, 
                     center_x+circle_size//2, center_y+circle_size//2), 
                     outline=white, width=2)
        
        # Draw S and P letters
        try:
            font = ImageFont.truetype("Arial.ttf", 50)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        draw.text((center_x-30, center_y-25), "S", fill=white, font=font)
        draw.text((center_x, center_y-25), "P", fill=white, font=font)
        
    elif style_num == 9:
        # Style 9: Futuristic minimalist design
        # Draw rectangular frame
        frame_width = 140
        frame_height = 100
        draw.rectangle((center_x-frame_width//2, center_y-frame_height//2,
                       center_x+frame_width//2, center_y+frame_height//2),
                       outline=white, width=3)
        
        # Draw horizontal line through center
        draw.line((center_x-frame_width//2, center_y, 
                  center_x+frame_width//2, center_y), 
                  fill=white, width=1)
        
        # Draw S and P letters with modern font
        try:
            font = ImageFont.truetype("Arial.ttf", 60)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        draw.text((center_x-frame_width//2+20, center_y-45), "S", fill=white, font=font)
        draw.text((center_x+10, center_y-45), "P", fill=white, font=font)
        
    elif style_num == 10:
        # Style 10: Wave pattern design
        # Draw wave patterns
        for i in range(5):
            y_offset = 30 + i*30
            for x in range(0, width, 2):
                y = y_offset + math.sin(x/20) * 10
                draw.point((x, y), fill=white)
        
        # Draw diagonal lines
        for i in range(-3, 4):
            draw.line((center_x + i*20, 20, center_x + i*20, height-20), 
                      fill=white, width=1)
        
        # Draw S and P letters
        try:
            font = ImageFont.truetype("Arial.ttf", 80)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw text
        draw.text((center_x-40, center_y-40), "S", fill=white, font=font)
        draw.text((center_x, center_y-40), "P", fill=white, font=font)
    
    # Apply blur to create glow effect
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    
    # Save the image
    img.save(f'static/png_logos/logo_option{style_num}.png')
    print(f"Created logo_option{style_num}.png")

# Create additional logo styles
for i in range(6, 11):
    create_advanced_logo(i)

print("All additional PNG logos created successfully!")