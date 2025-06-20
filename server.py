#!/usr/bin/env python3
import json
import proxai as px
import concurrent.futures
import time
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

chat_history = []
available_models = []

def get_largest_models():
    """Get the largest models from each provider, excluding deepseek-r1"""
    try:
        largest_models = px.models.list_models(model_size='largest')

        selected_models = []
        for model in largest_models:
            provider = model.provider
            model_name = model.model

            # Skip deepseek-r1, prefer deepseek-v3
            if provider == 'deepseek' and model_name == 'deepseek-r1':
                continue

            selected_models.append({
                'provider': provider,
                'model': model_name,
                'display_name': f"{provider.title()} {model_name.replace('-', ' ').title()}"
            })

        # Add deepseek-v3 if deepseek is available but we filtered out r1
        if any(m['provider'] == 'deepseek' for m in selected_models) == False:
            try:
                all_models = px.models.list_models()
                deepseek_v3 = next((m for m in all_models if m.provider == 'deepseek' and m.model == 'deepseek-v3'), None)
                if deepseek_v3:
                    selected_models.append({
                        'provider': 'deepseek',
                        'model': 'deepseek-v3',
                        'display_name': 'Deepseek V3'
                    })
            except:
                pass

        return selected_models

    except Exception as e:
        print(f"Error loading models: {e}")
        return []

def query_single_model(model, user_message, chat_history):
    """Query a single model and return result with timing"""
    try:
        start_time = time.time()

        response = px.generate_text(
            system="You are a helpful AI assistant. Be conversational and engaging.",
            messages=chat_history,
            provider_model=(model['provider'], model['model']),
            max_tokens=500,
            temperature=0.7
        )

        end_time = time.time()
        return {
            'model': model,
            'response': response,
            'time_taken': round(end_time - start_time, 2),
            'success': True
        }
    except Exception as e:
        end_time = time.time()
        return {
            'model': model,
            'response': None,
            'time_taken': round(end_time - start_time, 2),
            'success': False,
            'error': str(e)
        }

def query_all_models_parallel(available_models, user_message, chat_history):
    """Query all models in parallel and return results"""
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(available_models)) as executor:
        # Submit all tasks
        future_to_model = {
            executor.submit(query_single_model, model, user_message, chat_history): model
            for model in available_models
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_model):
            result = future.result()
            results.append(result)

    return results

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
        elif self.path == '/models':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            global available_models
            self.wfile.write(json.dumps({'models': available_models}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/chat':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            user_message = data.get('message', '').strip()
            selected_models = data.get('selected_models', [])

            if not user_message:
                response = {'error': 'Message cannot be empty'}
                self.send_response(400)
            elif not selected_models:
                response = {'error': 'No models selected'}
                self.send_response(400)
            else:
                try:
                    global chat_history
                    chat_history.append({"role": "user", "content": user_message})

                    # Query selected models in parallel
                    start_total_time = time.time()
                    results = query_all_models_parallel(selected_models, user_message, chat_history)
                    total_time = round(time.time() - start_total_time, 2)

                    # Filter successful responses
                    successful_results = [r for r in results if r['success']]
                    failed_results = [r for r in results if not r['success']]

                    if successful_results:
                        # Pick a random successful response
                        chosen_result = random.choice(successful_results)

                        # Create timing summary
                        timing_info = []
                        for result in successful_results:
                            timing_info.append(f"✓ {result['model']['display_name']}: {result['time_taken']}s")
                        for result in failed_results:
                            timing_info.append(f"✗ {result['model']['display_name']}: failed ({result['time_taken']}s)")

                        timing_summary = f"Queried {len(results)} models in {total_time}s:\n" + "\n".join(timing_info)
                        chosen_response = chosen_result['response']

                        chat_history.append({"role": "assistant", "content": chosen_response})

                        response = {
                            'response': chosen_response,
                            'timing_info': timing_summary,
                            'chosen_model': chosen_result['model']['display_name'],
                            'successful_count': len(successful_results),
                            'total_count': len(results)
                        }
                        self.send_response(200)
                    else:
                        response = {'error': 'All models failed to respond'}
                        self.send_response(500)

                except Exception as e:
                    print(f"Error calling ProxAI: {e}")
                    response = {'error': 'Failed to get AI response'}
                    self.send_response(500)

            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

def run_server():
    global available_models
    print("Loading available models...")
    available_models = get_largest_models()
    print(f"Loaded {len(available_models)} models")

    server_address = ('localhost', 3000)
    httpd = HTTPServer(server_address, ChatHandler)
    print("Server running on http://localhost:3000")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
