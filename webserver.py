#!/usr/bin/env python3
"""
Web server for MarkItDown file conversion service.
Provides HTTP API for file upload and markdown conversion.
"""

import os
import tempfile
import re
import base64
import io
from flask import Flask, request, jsonify, make_response
from markitdown import MarkItDown
from werkzeug.utils import secure_filename

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

app = Flask(__name__)

# Initialize MarkItDown
md = MarkItDown(enable_plugins=True)

def resize_base64_images(markdown_content, max_size_kb=200):
    """
    Resize base64 images in markdown content to be under max_size_kb.
    
    Args:
        markdown_content (str): Markdown content that may contain base64 images
        max_size_kb (int): Maximum size in KB for images
    
    Returns:
        str: Markdown content with resized images
    """
    if not PIL_AVAILABLE:
        return markdown_content
    
    # Pattern to match base64 images in markdown
    pattern = r'!\[([^\]]*)\]\(data:image/([^;]+);base64,([^)]+)\)'
    
    def resize_image_match(match):
        alt_text = match.group(1)
        image_format = match.group(2)
        base64_data = match.group(3)
        
        try:
            # Decode base64 image
            image_data = base64.b64decode(base64_data)
            
            # Check if image is over the size limit
            size_kb = len(image_data) / 1024
            if size_kb <= max_size_kb:
                return match.group(0)  # Return original if under limit
            
            # Open image with PIL
            image = Image.open(io.BytesIO(image_data))
            
            # Calculate new dimensions to reduce file size
            # Start with 80% of original size and adjust if needed
            scale_factor = 0.8
            max_iterations = 5
            
            for _ in range(max_iterations):
                new_width = int(image.width * scale_factor)
                new_height = int(image.height * scale_factor)
                
                # Resize image
                resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert back to bytes
                output_buffer = io.BytesIO()
                
                # Determine format for saving
                save_format = image_format.upper()
                if save_format == 'JPG':
                    save_format = 'JPEG'
                
                # For JPEG, use quality parameter to further reduce size
                if save_format == 'JPEG':
                    resized_image.save(output_buffer, format=save_format, quality=85, optimize=True)
                else:
                    resized_image.save(output_buffer, format=save_format, optimize=True)
                
                # Check new size
                new_image_data = output_buffer.getvalue()
                new_size_kb = len(new_image_data) / 1024
                
                if new_size_kb <= max_size_kb:
                    # Encode back to base64
                    new_base64_data = base64.b64encode(new_image_data).decode('utf-8')
                    return f'![{alt_text}](data:image/{image_format};base64,{new_base64_data})'
                
                # Reduce scale factor for next iteration
                scale_factor *= 0.8
            
            # If still too large after max iterations, return original
            return match.group(0)
            
        except Exception as e:
            # If any error occurs, return original image
            print(f"Error resizing image: {e}")
            return match.group(0)
    
    # Apply resizing to all base64 images in the markdown
    return re.sub(pattern, resize_image_match, markdown_content)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'markitdown-webserver'})

@app.route('/convert', methods=['POST'])
def convert_file():
    """
    Convert uploaded file to markdown.
    
    Accepts:
    - file: uploaded file (multipart/form-data)
    - keep_data_uris: optional boolean parameter (default: false)
    - max_size_kb: optional integer for max image size in KB (default: 200)
    
    Returns:
    - converted markdown
    """
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get optional parameters
        keep_data_uris = request.form.get('keep_data_uris', 'false').lower() == 'true'
        try:
            max_size_kb = int(request.form.get('max_size_kb', '200'))
        except ValueError:
            return jsonify({'error': 'max_size_kb must be a valid integer'}), 400
        
        # Read file content into memory
        file_content = file.read()
        file_stream = io.BytesIO(file_content)
        
        # Get original filename for extension hint
        original_filename = secure_filename(file.filename)
        
        # Create stream info with file extension
        from markitdown import StreamInfo
        stream_info = None
        if original_filename:
            extension = os.path.splitext(original_filename)[1].lower()
            if extension:
                stream_info = StreamInfo(extension=extension)
        
        # Convert file to markdown
        result = md.convert_stream(
            file_stream, 
            stream_info=stream_info,
            keep_data_uris=keep_data_uris
        )
        
        # Resize base64 images if they exist
        markdown_content = resize_base64_images(result.text_content, max_size_kb)
        
        # Return markdown content
        return markdown_content, 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/convert_text', methods=['POST'])
def convert_text():
    """
    Convert text content to markdown (for plain text processing).
    
    Accepts:
    - text: text content (JSON)
    - content_type: optional content type hint
    - max_size_kb: optional integer for max image size in KB (default: 200)
    
    Returns:
    - JSON response with converted markdown
    """
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'No text content provided'}), 400
        
        text_content = data['text']
        content_type = data.get('content_type', 'text/plain')
        try:
            max_size_kb = int(data.get('max_size_kb', 200))
        except (ValueError, TypeError):
            return jsonify({'error': 'max_size_kb must be a valid integer'}), 400
        
        # Convert text to BytesIO stream
        text_stream = io.BytesIO(text_content.encode('utf-8'))
        
        # Create stream info with content type
        from markitdown import StreamInfo
        stream_info = StreamInfo(mimetype=content_type)
        
        # Convert to markdown
        result = md.convert_stream(text_stream, stream_info=stream_info)
        
        # Resize base64 images if they exist
        markdown_content = resize_base64_images(result.text_content, max_size_kb)
        
        return markdown_content, 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/', methods=['GET'])
def index():
    """
    Simple API documentation endpoint.
    """
    return jsonify({
        'service': 'MarkItDown Web Server',
        'version': '1.0.0',
        'endpoints': {
            'POST /convert': 'Convert uploaded file to markdown',
            'POST /convert_text': 'Convert text content to markdown',
            'GET /health': 'Health check endpoint',
            'GET /': 'This documentation'
        },
        'usage': {
            'file_upload': 'POST /convert with multipart/form-data file. Optional: keep_data_uris=true, max_size_kb=200',
            'text_conversion': 'POST /convert_text with JSON {"text": "content", "max_size_kb": 200}'
        },
        'features': {
            'image_resizing': 'Automatically resizes base64 images over specified max_size_kb (default: 200KB)' + (' (PIL available)' if PIL_AVAILABLE else ' (PIL not available)')
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print(f"Starting MarkItDown web server on {host}:{port}")
    if not PIL_AVAILABLE:
        print("Warning: PIL/Pillow not available. Base64 image resizing disabled.")
    else:
        print("Base64 image resizing enabled (default max 200KB per image, configurable)")
    app.run(host=host, port=port, debug=debug) 