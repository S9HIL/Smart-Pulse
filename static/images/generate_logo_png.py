from PIL import Image, ImageDraw, ImageFont
import os

# Create a PNG logo with "SP" text
def create_sp_logo():
    # Create a transparent image
    img_size = 200
    img = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Try to find a suitable font
    font_size = 120
    try:
        # Try system fonts 
        font = ImageFont.truetype("Arial Bold.ttf", font_size)
    except IOError:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except IOError:
            # Fallback to default
            font = ImageFont.load_default()
    
    # Draw "SP" text
    text = "SP"
    # For newer Pillow versions use font.getbbox instead of draw.textsize
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    position = ((img_size - text_width) // 2, (img_size - text_height) // 2 - 10)
    
    # Draw with outline
    outline_color = (0, 0, 0, 180)
    outline_width = 2
    
    # Draw outline
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((position[0] + dx, position[1] + dy), text, font=font, fill=outline_color)
    
    # Draw main text with gradient-like effect
    gradient_colors = [
        (0, 123, 255, 255),    # Blue
        (111, 66, 193, 255),   # Purple
        (40, 167, 69, 255),    # Green
        (253, 126, 20, 255),   # Orange
        (220, 53, 69, 255)     # Red
    ]
    
    # Draw main text
    draw.text(position, text, font=font, fill=gradient_colors[0])
    
    # Save the image
    output_path = "sp-logo.png"  # Save in current directory (static/images)
    img.save(output_path)
    print(f"Logo saved to {output_path}")
    
    return output_path

if __name__ == "__main__":
    create_sp_logo()