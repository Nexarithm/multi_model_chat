#!/usr/bin/env python3
import json
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class ChatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open('index.html', 'r') as f:
                self.wfile.write(f.read().encode())
        elif self.path == '/style.css':
            self.send_response(200)
            self.send_header('Content-type', 'text/css')
            self.end_headers()
            with open('style.css', 'r') as f:
                self.wfile.write(f.read().encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/chat':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            user_message = data.get('message', '').strip()
            
            if not user_message:
                response = {'error': 'Message cannot be empty'}
                self.send_response(400)
            else:
                random_responses = [
                    "That's interesting! Tell me more.",
                    "I see what you mean.",
                    "Fascinating perspective!",
                    "Can you elaborate on that?",
                    "That reminds me of something similar.",
                    "What do you think about it?",
                    "I hadn't thought of it that way.",
                    "That's a good point.",
                    "How did you come to that conclusion?",
                    "That's quite insightful!"
                ]
                bot_response = random.choice(random_responses)
                response = {'response': bot_response}
                self.send_response(200)
            
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

def run_server():
    server_address = ('localhost', 3000)
    httpd = HTTPServer(server_address, ChatHandler)
    print("Server running on http://localhost:3000")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()