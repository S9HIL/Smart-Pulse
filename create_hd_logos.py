from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance
import io
import os
import math
import random

# Create directory for PNG logos if it doesn't exist
if not os.path.exists('static/png_logos'):
    os.makedirs('static/png_logos')

# Function to create high-definition SP logos with attractive designs
def create_hd_logo(style_num, size=(500, 500)):
    # Create a new image with black background
    img = Image.new('RGBA', size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    
    # Get center coordinates
    width, height = size
    center_x, center_y = width // 2, height // 2
    
    # Default colors
    white = (255, 255, 255, 255)
    grey = (180, 180, 180, 255)
    light_blue = (100, 200, 255, 255)
    purple = (180, 100, 255, 255)
    cyan = (0, 220, 255, 255)
    
    if style_num == 1:
        # Style 1: Elegant circle with gradient effect
        # Draw outer circle
        for i in range(10):
            radius = width//2 - 20 - i
            opacity = int(255 * (1 - i/10))
            circle_color = (255, 255, 255, opacity)
            draw.ellipse((center_x - radius, center_y - radius, 
                         center_x + radius, center_y + radius), 
                         outline=circle_color, width=2)
        
        # Draw inner circle with gradient effect
        for i in range(20):
            radius = width//3 - i*2
            if radius <= 0:
                break
            opacity = int(255 * (1 - i/20))
            circle_color = (100, 200, 255, opacity)
            draw.ellipse((center_x - radius, center_y - radius, 
                         center_x + radius, center_y + radius), 
                         outline=circle_color, width=1)
        
        # Create a large "SP" text
        try:
            # Use a bold, modern font
            font = ImageFont.truetype("Arial.ttf", size=width//3)
        except:
            font = ImageFont.load_default()
        
        # Draw a shadow for depth
        shadow_offset = 3
        draw.text((center_x - width//6 + shadow_offset, center_y - height//6 + shadow_offset), 
                 "SP", fill=(50, 50, 50, 150), font=font)
        
        # Draw the main text
        draw.text((center_x - width//6, center_y - height//6), 
                 "SP", fill=white, font=font)
        
    elif style_num == 2:
        # Style 2: Modern tech square design with glow
        # Draw main square
        square_size = width * 0.7
        draw.rectangle((center_x - square_size/2, center_y - square_size/2,
                       center_x + square_size/2, center_y + square_size/2),
                       outline=white, width=3)
        
        # Draw diagonal glowing lines
        for i in range(10):
            opacity = int(255 * (1 - i/10))
            line_color = (255, 255, 255, opacity)
            offset = i * 3
            
            # Top-left to bottom-right
            draw.line((center_x - square_size/2 - offset, center_y - square_size/2 - offset,
                      center_x + square_size/2 + offset, center_y + square_size/2 + offset),
                      fill=line_color, width=1)
            
            # Top-right to bottom-left
            draw.line((center_x + square_size/2 + offset, center_y - square_size/2 - offset,
                      center_x - square_size/2 - offset, center_y + square_size/2 + offset),
                      fill=line_color, width=1)
        
        # Draw S and P with a tech font style
        try:
            font = ImageFont.truetype("Arial.ttf", size=width//3)
        except:
            font = ImageFont.load_default()
        
        # Draw text with blue glow
        for i in range(5):
            opacity = int(150 * (1 - i/5)) + 100
            text_color = (200, 220, 255, opacity)
            draw.text((center_x - width//6 + i, center_y - height//6 + i), 
                     "S", fill=text_color, font=font)
            draw.text((center_x + width//12 + i, center_y - height//6 + i), 
                     "P", fill=text_color, font=font)
        
        # Draw main text
        draw.text((center_x - width//6, center_y - height//6), 
                 "S", fill=white, font=font)
        draw.text((center_x + width//12, center_y - height//6), 
                 "P", fill=white, font=font)
        
    elif style_num == 3:
        # Style 3: Hexagonal futuristic design
        # Draw hexagon with multiple layers
        for i in range(5):
            hex_radius = width//2 - 20 - i*10
            hex_points = []
            for j in range(6):
                angle_deg = 60 * j
                angle_rad = math.pi / 180 * angle_deg
                x = center_x + hex_radius * math.cos(angle_rad)
                y = center_y + hex_radius * math.sin(angle_rad)
                hex_points.append((x, y))
            
            # Connect the points to form a hexagon
            for j in range(6):
                start_point = hex_points[j]
                end_point = hex_points[(j+1) % 6]
                draw.line([start_point, end_point], 
                          fill=(255, 255, 255, 200 - i*40), width=2)
        
        # Add tech-inspired circuit lines
        for i in range(6):
            start_x = center_x + (width//2 - 10) * math.cos(math.pi/3 * i)
            start_y = center_y + (width//2 - 10) * math.sin(math.pi/3 * i)
            
            # Draw lines from corners to center
            draw.line([(start_x, start_y), (center_x, center_y)], 
                      fill=(100, 200, 255, 150), width=1)
        
        # Draw SP text with a bold, tech font
        try:
            font = ImageFont.truetype("Arial.ttf", size=width//3)
        except:
            font = ImageFont.load_default()
        
        # Draw glowing text effect
        for i in range(5):
            offset = i * 1.5
            opacity = int(200 * (1 - i/5)) + 50
            glow_color = (150, 220, 255, opacity)
            
            draw.text((center_x - width//6 + offset, center_y - height//6), 
                     "S", fill=glow_color, font=font)
            draw.text((center_x + width//12 + offset, center_y - height//6), 
                     "P", fill=glow_color, font=font)
        
        # Main text
        draw.text((center_x - width//6, center_y - height//6), 
                 "S", fill=white, font=font)
        draw.text((center_x + width//12, center_y - height//6), 
                 "P", fill=white, font=font)
        
    elif style_num == 4:
        # Style 4: Neon light effect with glossy finish
        # Draw outer glowing ring
        for i in range(15):
            radius = width//2 - 20 - i*1.5
            opacity = int(200 * (1 - i/15)) + 50
            glow_color = (255, 120, 255, opacity)
            draw.ellipse((center_x - radius, center_y - radius, 
                         center_x + radius, center_y + radius), 
                         outline=glow_color, width=1)
        
        # Inner glowing ring
        for i in range(10):
            radius = width//3 - i*1.5
            opacity = int(200 * (1 - i/10)) + 50
            glow_color = (120, 200, 255, opacity)
            draw.ellipse((center_x - radius, center_y - radius, 
                         center_x + radius, center_y + radius), 
                         outline=glow_color, width=1)
        
        # Create neon-like SP text
        try:
            font = ImageFont.truetype("Arial.ttf", size=width//3)
        except:
            font = ImageFont.load_default()
        
        # Draw pink glow for neon effect
        for i in range(7):
            offset = i * 1.2
            opacity = int(150 * (1 - i/7)) + 100
            if i % 2 == 0:
                glow_color = (255, 150, 255, opacity)
            else:
                glow_color = (150, 220, 255, opacity)
            
            draw.text((center_x - width//6 + offset/2, center_y - height//6 + offset/2), 
                     "S", fill=glow_color, font=font)
            draw.text((center_x + width//12 + offset/2, center_y - height//6 + offset/2), 
                     "P", fill=glow_color, font=font)
        
        # Main text with bright white
        draw.text((center_x - width//6, center_y - height//6), 
                 "S", fill=(255, 255, 255, 255), font=font)
        draw.text((center_x + width//12, center_y - height//6), 
                 "P", fill=(255, 255, 255, 255), font=font)
        
    elif style_num == 5:
        # Style 5: Minimal elegant design with subtle glow
        # Draw thin border
        border_padding = width//12
        draw.rectangle((border_padding, border_padding, 
                        width - border_padding, height - border_padding),
                        outline=white, width=1)
        
        # Draw corner accents
        corner_size = width//10
        # Top-left
        draw.line((border_padding, border_padding + corner_size,
                  border_padding, border_padding), fill=white, width=2)
        draw.line((border_padding, border_padding,
                  border_padding + corner_size, border_padding), fill=white, width=2)
        
        # Top-right
        draw.line((width - border_padding - corner_size, border_padding,
                  width - border_padding, border_padding), fill=white, width=2)
        draw.line((width - border_padding, border_padding,
                  width - border_padding, border_padding + corner_size), fill=white, width=2)
        
        # Bottom-left
        draw.line((border_padding, height - border_padding - corner_size,
                  border_padding, height - border_padding), fill=white, width=2)
        draw.line((border_padding, height - border_padding,
                  border_padding + corner_size, height - border_padding), fill=white, width=2)
        
        # Bottom-right
        draw.line((width - border_padding - corner_size, height - border_padding,
                  width - border_padding, height - border_padding), fill=white, width=2)
        draw.line((width - border_padding, height - border_padding - corner_size,
                  width - border_padding, height - border_padding), fill=white, width=2)
        
        # Create elegant SP text
        try:
            font = ImageFont.truetype("Arial.ttf", size=width//2)
        except:
            font = ImageFont.load_default()
        
        # Draw subtle shadow for depth
        shadow_offset = 4
        shadow_color = (70, 70, 70, 180)
        draw.text((center_x - width//4 + shadow_offset, center_y - height//4 + shadow_offset), 
                 "SP", fill=shadow_color, font=font)
        
        # Main text with clean white
        draw.text((center_x - width//4, center_y - height//4), 
                 "SP", fill=white, font=font)
    
    # Apply final touch-ups and effects
    # Slight blur for more realistic glow
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    
    # Enhance contrast slightly
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.1)
    
    # Enhance brightness slightly
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.05)
    
    # Save the high-definition image
    img.save(f'static/png_logos/hd_logo_{style_num}.png')
    print(f"Created hd_logo_{style_num}.png")

# Create high-definition logo styles
for i in range(1, 6):
    create_hd_logo(i)

print("All HD logos created successfully!")