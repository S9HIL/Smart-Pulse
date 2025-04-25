from PIL import Image, ImageDraw, ImageFont
import os
import math

# Create a high-quality PNG logo with "SP" text
def create_sp_logo():
    # Create a higher resolution transparent image for HD quality
    img_size = 500  # Increased for HD quality
    img = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Try to find a suitable font with larger size
    font_size = 280  # Increased for better quality
    try:
        # Try system fonts with preference for bold fonts
        font = ImageFont.truetype("Arial Bold.ttf", font_size)
    except IOError:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except IOError:
            try:
                # Try more system fonts
                font = ImageFont.truetype("Roboto-Bold.ttf", font_size)
            except IOError:
                # Fallback to default
                font = ImageFont.load_default()
    
    # Draw "SP" text
    text = "SP"
    # For newer Pillow versions use font.getbbox instead of draw.textsize
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    position = ((img_size - text_width) // 2, (img_size - text_height) // 2 - 20)
    
    # Draw with enhanced outline for better visual appeal
    outline_color = (0, 0, 0, 200)  # Darker outline for HD
    outline_width = 4  # Thicker outline for HD
    
    # Draw outline
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((position[0] + dx, position[1] + dy), text, font=font, fill=outline_color)
    
    # Draw main text with metallic gradient-like effect
    gradient_colors = [
        (0, 120, 255, 255),    # Blue
        (70, 140, 240, 255),   # Light Blue
        (100, 180, 240, 255),  # Lighter Blue
        (120, 200, 255, 255),  # Sky Blue
        (50, 100, 220, 255)    # Deep Blue
    ]
    
    # Draw main text with metal-like gradient
    draw.text(position, text, font=font, fill=gradient_colors[0])
    
    # Add a subtle shine effect
    shine_position = (position[0] + 10, position[1] + 10)
    shine_color = (255, 255, 255, 80)  # Transparent white for shine
    draw.text(shine_position, text, font=font, fill=shine_color)
    
    # Add a bottom shadow for 3D effect
    shadow_position = (position[0] + 5, position[1] + 5)
    shadow_color = (0, 0, 0, 70)  # Transparent black for shadow
    draw.text(shadow_position, text, font=font, fill=shadow_color)
    
    # Save the high-resolution image
    output_path = "static/images/sp-logo-hd.png"
    img.save(output_path, quality=95)  # High quality save
    print(f"HD Logo saved to {output_path}")
    
    # Also create smaller version for favicon/icon
    small_size = 200
    small_img = img.resize((small_size, small_size), Image.LANCZOS)  # Best quality downsampling
    small_output_path = "static/images/sp-logo-small.png"
    small_img.save(small_output_path)
    print(f"Small logo saved to {small_output_path}")
    
    # Create animated version (save frames for web animation)
    frames_path = "static/images/sp-logo-frames"
    os.makedirs(frames_path, exist_ok=True)
    
    # Create 10 frames with subtle movement
    num_frames = 10
    for i in range(num_frames):
        frame = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
        frame_draw = ImageDraw.Draw(frame)
        
        # Calculate offset based on frame number for subtle motion
        offset_x = int(3 * math.sin(2 * math.pi * i / num_frames))
        offset_y = int(2 * math.cos(2 * math.pi * i / num_frames))
        
        # Draw outline with motion
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    frame_draw.text(
                        (position[0] + dx + offset_x, position[1] + dy + offset_y), 
                        text, font=font, fill=outline_color
                    )
        
        # Draw main text with motion
        frame_draw.text(
            (position[0] + offset_x, position[1] + offset_y), 
            text, font=font, fill=gradient_colors[i % len(gradient_colors)]
        )
        
        # Add shine with motion
        frame_draw.text(
            (shine_position[0] + offset_x, shine_position[1] + offset_y), 
            text, font=font, fill=shine_color
        )
        
        # Save frame
        frame_path = os.path.join(frames_path, f"frame_{i:02d}.png")
        frame.save(frame_path)
    
    print(f"Created {num_frames} animation frames in {frames_path}")
    
    return output_path

if __name__ == "__main__":
    create_sp_logo()