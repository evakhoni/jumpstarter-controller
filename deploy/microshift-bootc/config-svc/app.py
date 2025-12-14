#!/usr/bin/env python3
"""
Jumpstarter Configuration Web UI

A simple web service for configuring Jumpstarter deployment settings:
- Hostname configuration with smart defaults
- Jumpstarter CR management (baseDomain + image version)
- MicroShift kubeconfig download
"""

import os
import re
import socket
import subprocess
import sys
import tempfile
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import Flask, request, send_file, render_template_string, Response

app = Flask(__name__)


def check_auth(username, password):
    """Check if a username/password combination is valid using PAM."""
    if username != 'root':
        return False
    
    try:
        # Try using PAM authentication first
        import pam
        p = pam.pam()
        return p.authenticate(username, password)
    except ImportError:
        # Fallback: use subprocess to authenticate via su
        try:
            result = subprocess.run(
                ['su', username, '-c', 'true'],
                input=password.encode(),
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Authentication error: {e}", file=sys.stderr)
            return False


def authenticate():
    """Send a 401 response that enables basic auth."""
    return Response(
        'Authentication required. Please login with root credentials.',
        401,
        {'WWW-Authenticate': 'Basic realm="Jumpstarter Configuration"'}
    )


def requires_auth(f):
    """Decorator to require HTTP Basic Authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# HTML template for the main page
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jumpstarter Configuration</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 600px;
            width: 100%;
            padding: 40px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .section {
            margin-bottom: 30px;
            padding-bottom: 30px;
            border-bottom: 1px solid #eee;
        }
        .section:last-child {
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }
        h2 {
            color: #444;
            font-size: 20px;
            margin-bottom: 15px;
        }
        .info {
            background: #f8f9fa;
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 15px;
            font-size: 14px;
            color: #555;
        }
        .info strong {
            color: #333;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 6px;
            color: #555;
            font-size: 14px;
            font-weight: 500;
        }
        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus,
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .hint {
            font-size: 12px;
            color: #888;
            margin-top: 4px;
        }
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.3s;
        }
        button:hover {
            background: #5568d3;
        }
        .download-btn {
            background: #28a745;
            display: inline-block;
            text-decoration: none;
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            transition: background 0.3s;
        }
        .download-btn:hover {
            background: #218838;
        }
        .message {
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 14px;
        }
        .message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Jumpstarter Configuration</h1>
        <p class="subtitle">Configure your Jumpstarter deployment settings</p>
        
        {% for msg in messages %}
        <div class="message {{ msg.type }}">{{ msg.text }}</div>
        {% endfor %}
        
        <div class="section">
            <h2>System Information</h2>
            <div class="info">
                <strong>Current Hostname:</strong> {{ current_hostname }}
            </div>
        </div>
        
        <div class="section">
            <h2>Jumpstarter Configuration</h2>
            <form method="POST" action="/configure-jumpstarter">
                <div class="form-group">
                    <label for="baseDomain">Base Domain</label>
                    <input type="text" id="baseDomain" name="baseDomain" value="{{ suggested_hostname }}" required>
                    <div class="hint">Will also set the system hostname. Default: {{ suggested_hostname }}</div>
                </div>
                <div class="form-group">
                    <label for="image">Controller Image</label>
                    <input type="text" id="image" name="image" value="quay.io/jumpstarter-dev/jumpstarter-controller:latest" required>
                    <div class="hint">The Jumpstarter controller container image to use</div>
                </div>
                <div class="form-group">
                    <label for="rootPassword">Root Password *</label>
                    <input type="password" id="rootPassword" name="rootPassword" required minlength="8">
                    <div class="hint">Required: Set a secure password for the root user (minimum 8 characters)</div>
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


@app.route('/')
@requires_auth
def index():
    """Serve the main configuration page."""
    current_hostname = get_current_hostname()
    default_ip = get_default_route_ip()
    suggested_hostname = f"jumpstarter.{default_ip}.nip.io" if default_ip else "jumpstarter.local"
    
    return render_template_string(
        HTML_TEMPLATE,
        messages=[],
        current_hostname=current_hostname,
        suggested_hostname=suggested_hostname
    )


@app.route('/configure-jumpstarter', methods=['POST'])
@requires_auth
def configure_jumpstarter():
    """Handle Jumpstarter CR configuration request."""
    base_domain = request.form.get('baseDomain', '').strip()
    image = request.form.get('image', '').strip()
    root_password = request.form.get('rootPassword', '')
    
    current_hostname = get_current_hostname()
    default_ip = get_default_route_ip()
    suggested_hostname = f"jumpstarter.{default_ip}.nip.io" if default_ip else "jumpstarter.local"
    
    messages = []
    
    if not base_domain:
        messages.append({'type': 'error', 'text': 'Base domain is required'})
    elif not image:
        messages.append({'type': 'error', 'text': 'Controller image is required'})
    elif not root_password or len(root_password) < 8:
        messages.append({'type': 'error', 'text': 'Root password is required (minimum 8 characters)'})
    else:
        # First, set the root password
        password_success, password_message = set_root_password(root_password)
        if not password_success:
            messages.append({'type': 'error', 'text': f'Failed to set root password: {password_message}'})
        
        # Then set the hostname to match the base domain
        hostname_success, hostname_message = set_hostname(base_domain)
        if not hostname_success:
            messages.append({'type': 'error', 'text': f'Failed to update hostname: {hostname_message}'})
        else:
            current_hostname = base_domain
            
        # Finally apply the Jumpstarter CR
        cr_success, cr_message = apply_jumpstarter_cr(base_domain, image)
        
        # Show success message only if all operations succeeded
        if password_success and hostname_success and cr_success:
            msg = f'Configuration applied successfully! Hostname: {base_domain}, Image: {image}'
            messages.append({'type': 'success', 'text': msg})
        elif cr_success or hostname_success:
            # Partial success
            if not cr_success:
                messages.append({'type': 'error', 'text': f'Failed to apply Jumpstarter CR: {cr_message}'})
        else:
            if not cr_success:
                messages.append({'type': 'error', 'text': f'Failed to apply Jumpstarter CR: {cr_message}'})
    
    return render_template_string(
        HTML_TEMPLATE,
        messages=messages,
        current_hostname=current_hostname,
        suggested_hostname=suggested_hostname
    )


@app.route('/kubeconfig')
@requires_auth
def download_kubeconfig():
    """Serve the kubeconfig file for download with hostname and insecure TLS."""
    kubeconfig_path = Path('/var/lib/microshift/resources/kubeadmin/kubeconfig')
    
    if not kubeconfig_path.exists():
        return "Kubeconfig file not found", 404
    
    try:
        # Read the original kubeconfig
        with open(kubeconfig_path, 'r') as f:
            kubeconfig_content = f.read()
        
        # Get the current hostname
        current_hostname = get_current_hostname()
        
        # Replace localhost with the configured hostname
        kubeconfig_content = re.sub(
            r'server:\s+https://localhost:(\d+)',
            f'server: https://{current_hostname}:\\1',
            kubeconfig_content
        )
        
        # Add insecure-skip-tls-verify: true to the cluster section
        # We'll add it after the server line in the cluster section
        kubeconfig_content = re.sub(
            r'(server:\s+https://[^\n]+\n)',
            r'\1    insecure-skip-tls-verify: true\n',
            kubeconfig_content
        )
        
        # Create a BytesIO object to send as file
        kubeconfig_bytes = BytesIO(kubeconfig_content.encode('utf-8'))
        kubeconfig_bytes.seek(0)
        
        return send_file(
            kubeconfig_bytes,
            as_attachment=True,
            download_name='kubeconfig',
            mimetype='application/octet-stream'
        )
    except Exception as e:
        return f"Error reading kubeconfig: {str(e)}", 500


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


def set_root_password(password):
    """Set the root user password using chpasswd."""
    try:
        # Use chpasswd to set password (more reliable than passwd for scripting)
        process = subprocess.Popen(
            ['chpasswd'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=f'root:{password}\n')
        
        if process.returncode != 0:
            error_msg = stderr.strip() if stderr else "Unknown error"
            print(f"Error setting root password: {error_msg}", file=sys.stderr)
            return False, error_msg
        
        return True, "Success"
    except Exception as e:
        print(f"Error setting root password: {e}", file=sys.stderr)
        return False, str(e)


def apply_jumpstarter_cr(base_domain, image):
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
                'baseDomain': base_domain,
                'image': image
            }
        }
        
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
    
    print(f"Starting Jumpstarter Configuration UI on port {port}...", file=sys.stderr)
    print(f"Access the UI at http://localhost:{port}/", file=sys.stderr)
    
    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()

