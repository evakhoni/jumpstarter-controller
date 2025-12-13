#!/usr/bin/env python3
"""
Jumpstarter Configuration Web UI

A simple web service for configuring Jumpstarter deployment settings:
- Hostname configuration with smart defaults
- Jumpstarter CR management (baseDomain + image version)
- MicroShift kubeconfig download
"""

import http.server
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class ConfigHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the configuration UI."""

    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            self.serve_main_page()
        elif parsed_path.path == '/kubeconfig':
            self.serve_kubeconfig()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests."""
        parsed_path = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = parse_qs(post_data)
        
        if parsed_path.path == '/configure-hostname':
            self.handle_hostname_config(params)
        elif parsed_path.path == '/configure-jumpstarter':
            self.handle_jumpstarter_config(params)
        else:
            self.send_error(404, "Not Found")

    def serve_main_page(self, messages=None):
        """Serve the main configuration page."""
        if messages is None:
            messages = []
        
        # Get current system info
        current_hostname = get_current_hostname()
        default_ip = get_default_route_ip()
        suggested_hostname = f"jumpstarter.{default_ip}.nip.io" if default_ip else "jumpstarter.local"
        
        # Build HTML page
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jumpstarter Configuration</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 600px;
            width: 100%;
            padding: 40px;
        }}
        h1 {{
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }}
        .section {{
            margin-bottom: 30px;
            padding-bottom: 30px;
            border-bottom: 1px solid #eee;
        }}
        .section:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}
        h2 {{
            color: #444;
            font-size: 20px;
            margin-bottom: 15px;
        }}
        .info {{
            background: #f8f9fa;
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 15px;
            font-size: 14px;
            color: #555;
        }}
        .info strong {{
            color: #333;
        }}
        .form-group {{
            margin-bottom: 15px;
        }}
        label {{
            display: block;
            margin-bottom: 6px;
            color: #555;
            font-size: 14px;
            font-weight: 500;
        }}
        input[type="text"] {{
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.3s;
        }}
        input[type="text"]:focus {{
            outline: none;
            border-color: #667eea;
        }}
        .hint {{
            font-size: 12px;
            color: #888;
            margin-top: 4px;
        }}
        button {{
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.3s;
        }}
        button:hover {{
            background: #5568d3;
        }}
        .download-btn {{
            background: #28a745;
            display: inline-block;
            text-decoration: none;
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            transition: background 0.3s;
        }}
        .download-btn:hover {{
            background: #218838;
        }}
        .message {{
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 14px;
        }}
        .message.success {{
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }}
        .message.error {{
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Jumpstarter Configuration</h1>
        <p class="subtitle">Configure your Jumpstarter deployment settings</p>
        
        {''.join(f'<div class="message {msg["type"]}">{msg["text"]}</div>' for msg in messages)}
        
        <div class="section">
            <h2>Hostname Configuration</h2>
            <div class="info">
                <strong>Current Hostname:</strong> {current_hostname}
            </div>
            <form method="POST" action="/configure-hostname">
                <div class="form-group">
                    <label for="hostname">New Hostname</label>
                    <input type="text" id="hostname" name="hostname" value="{suggested_hostname}" required>
                    <div class="hint">Default: {suggested_hostname}</div>
                </div>
                <button type="submit">Update Hostname</button>
            </form>
        </div>
        
        <div class="section">
            <h2>Jumpstarter Configuration</h2>
            <form method="POST" action="/configure-jumpstarter">
                <div class="form-group">
                    <label for="baseDomain">Base Domain *</label>
                    <input type="text" id="baseDomain" name="baseDomain" placeholder="example.com" required>
                    <div class="hint">Required: The base domain for your Jumpstarter deployment</div>
                </div>
                <div class="form-group">
                    <label for="imageVersion">Image Version</label>
                    <input type="text" id="imageVersion" name="imageVersion" placeholder="latest">
                    <div class="hint">Optional: Specific image version to use</div>
                </div>
                <button type="submit">Apply Configuration</button>
            </form>
        </div>
        
        <div class="section">
            <h2>Download Kubeconfig</h2>
            <p style="color: #666; font-size: 14px; margin-bottom: 15px;">
                Download the MicroShift kubeconfig file to access the Kubernetes cluster.
            </p>
            <a href="/kubeconfig" class="download-btn">Download kubeconfig</a>
        </div>
    </div>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def handle_hostname_config(self, params):
        """Handle hostname configuration request."""
        hostname = params.get('hostname', [''])[0].strip()
        
        if not hostname:
            self.serve_main_page([{'type': 'error', 'text': 'Hostname cannot be empty'}])
            return
        
        success, message = set_hostname(hostname)
        
        if success:
            self.serve_main_page([{'type': 'success', 'text': f'Hostname successfully updated to: {hostname}'}])
        else:
            self.serve_main_page([{'type': 'error', 'text': f'Failed to update hostname: {message}'}])

    def handle_jumpstarter_config(self, params):
        """Handle Jumpstarter CR configuration request."""
        base_domain = params.get('baseDomain', [''])[0].strip()
        image_version = params.get('imageVersion', [''])[0].strip() or None
        
        if not base_domain:
            self.serve_main_page([{'type': 'error', 'text': 'Base domain is required'}])
            return
        
        success, message = apply_jumpstarter_cr(base_domain, image_version)
        
        if success:
            msg = f'Jumpstarter CR applied successfully with baseDomain: {base_domain}'
            if image_version:
                msg += f', imageVersion: {image_version}'
            self.serve_main_page([{'type': 'success', 'text': msg}])
        else:
            self.serve_main_page([{'type': 'error', 'text': f'Failed to apply Jumpstarter CR: {message}'}])

    def serve_kubeconfig(self):
        """Serve the kubeconfig file for download."""
        kubeconfig_path = Path('/var/lib/microshift/resources/kubeadmin/kubeconfig')
        
        if not kubeconfig_path.exists():
            self.send_error(404, "Kubeconfig file not found")
            return
        
        try:
            with open(kubeconfig_path, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', 'attachment; filename="kubeconfig"')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading kubeconfig: {str(e)}")

    def log_message(self, format, *args):
        """Override to customize logging."""
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


def get_default_route_ip():
    """Get the IP address of the default route interface."""
    try:
        # Get default route
        result = subprocess.run(
            ['ip', 'route', 'show', 'default'],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse output: "default via X.X.X.X dev ethX ..."
        lines = result.stdout.strip().split('\n')
        if not lines:
            return None
        
        parts = lines[0].split()
        if len(parts) < 5:
            return None
        
        # Find the device name
        dev_idx = parts.index('dev') if 'dev' in parts else None
        if dev_idx is None or dev_idx + 1 >= len(parts):
            return None
        
        dev_name = parts[dev_idx + 1]
        
        # Get IP address for this device
        result = subprocess.run(
            ['ip', '-4', 'addr', 'show', dev_name],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse: "    inet 192.168.1.10/24 ..."
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('inet '):
                ip_with_mask = line.split()[1]
                ip = ip_with_mask.split('/')[0]
                return ip.replace('.', '-')  # Format for nip.io
        
        return None
    except Exception as e:
        print(f"Error getting default route IP: {e}", file=sys.stderr)
        return None


def get_current_hostname():
    """Get the current system hostname."""
    try:
        return socket.gethostname()
    except Exception as e:
        print(f"Error getting hostname: {e}", file=sys.stderr)
        return "unknown"


def set_hostname(hostname):
    """Set the system hostname using hostnamectl."""
    try:
        subprocess.run(
            ['hostnamectl', 'set-hostname', hostname],
            capture_output=True,
            text=True,
            check=True
        )
        return True, "Success"
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"Error setting hostname: {error_msg}", file=sys.stderr)
        return False, error_msg
    except Exception as e:
        print(f"Error setting hostname: {e}", file=sys.stderr)
        return False, str(e)


def apply_jumpstarter_cr(base_domain, image_version=None):
    """Apply Jumpstarter Custom Resource using kubectl."""
    try:
        # Build the CR YAML
        cr = {
            'apiVersion': 'jumpstarter.dev/v1alpha1',
            'kind': 'Jumpstarter',
            'metadata': {
                'name': 'jumpstarter',
                'namespace': 'default'
            },
            'spec': {
                'baseDomain': base_domain
            }
        }
        
        if image_version:
            cr['spec']['imageVersion'] = image_version
        
        # Write CR to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml_content = json_to_yaml(cr)
            f.write(yaml_content)
            temp_file = f.name
        
        try:
            # Apply using kubectl
            result = subprocess.run(
                ['kubectl', 'apply', '-f', temp_file],
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout.strip()
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file)
            except Exception:
                pass
                
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"Error applying Jumpstarter CR: {error_msg}", file=sys.stderr)
        return False, error_msg
    except Exception as e:
        print(f"Error applying Jumpstarter CR: {e}", file=sys.stderr)
        return False, str(e)


def json_to_yaml(obj, indent=0):
    """Convert a JSON object to YAML format (simple implementation)."""
    lines = []
    indent_str = '  ' * indent
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{indent_str}{key}:")
                lines.append(json_to_yaml(value, indent + 1))
            else:
                lines.append(f"{indent_str}{key}: {yaml_value(value)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                lines.append(f"{indent_str}-")
                lines.append(json_to_yaml(item, indent + 1))
            else:
                lines.append(f"{indent_str}- {yaml_value(item)}")
    
    return '\n'.join(lines)


def yaml_value(value):
    """Format a value for YAML output."""
    if value is None:
        return 'null'
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, str):
        # Quote strings that contain special characters
        if ':' in value or '#' in value or value.startswith('-'):
            return f'"{value}"'
        return value
    else:
        return str(value)


def main():
    """Main entry point."""
    port = int(os.environ.get('PORT', 8080))
    
    print(f"Starting Jumpstarter Configuration UI on port {port}...")
    print(f"Access the UI at http://localhost:{port}/")
    
    server = http.server.HTTPServer(('0.0.0.0', port), ConfigHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


if __name__ == '__main__':
    main()

