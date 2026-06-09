import http.server
import socketserver

class SilentHandler(http.server.SimpleHTTPRequestHandler):
    # Overriding log_message to do absolutely nothing silences everything
    def log_message(self, format, *args):
        pass 

with socketserver.TCPServer(("", 8000), SilentHandler) as httpd:
    httpd.serve_forever()
